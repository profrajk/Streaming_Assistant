package appTests;

import org.testng.annotations.AfterClass;
import org.testng.annotations.Test;
import java.net.URL;
import java.time.Duration;
import java.util.Collections;
import java.util.concurrent.Future;
import java.util.List;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

import org.json.JSONObject;
import org.openqa.selenium.By;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.testng.annotations.BeforeClass;
import org.openqa.selenium.interactions.PointerInput;
import org.openqa.selenium.interactions.Sequence;

import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;

public class AmazonTest extends BaseTestClass {

    Future<JSONObject> networkMetricsFuture;

    @BeforeClass
	public void setupAndStartPolling() throws Exception {
	    System.out.println("Launching Network Cell Info Lite in background...");
	    Runtime.getRuntime().exec("adb shell monkey -p com.wilysis.cellinfolite -c android.intent.category.LAUNCHER 1");
	    Thread.sleep(2000);
	    syncDeviceTime(); 

	    keepPolling = true;
	    networkMetricsFuture = startRANAndSpeedPolling();

	    cap.setCapability("appPackage", "in.amazon.mShop.android.shopping");
	    cap.setCapability("appActivity", "com.amazon.mShop.android.home.HomeActivity");
	}

    @AfterClass
    public void quitDriverAndSaveMetrics() {
        try {
            keepPolling = false;

            if (networkMetricsFuture != null) {
                JSONObject finalNetworkMetrics = networkMetricsFuture.get();
                if (testResults.has("metadata")) {
                    finalNetworkMetrics.put("metadata", testResults.getJSONObject("metadata"));
                }
                saveResultsToFile("Amazon", "NetworkMetrics", finalNetworkMetrics);
            }

            terminateApp("in.amazon.mShop.android.shopping");

            JSONObject pingData = capturePingData("www.google.com");
            testResults.put("pingData", pingData);

		DateTimeFormatter endFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS").withZone(ZoneId.of("Asia/Kolkata"));
		testResults.put("Test_End_Timestamp", endFormatter.format(Instant.ofEpochMilli(System.currentTimeMillis() + deviceTimeOffset)));

		saveResultsToFile("Amazon", "AppMetrics", testResults);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

     @Test(priority = 0)
    public void launchAmazon() throws Exception {
        JSONObject launchData = new JSONObject();
        long startTime = 0;
        try {
            URL url = new URL("http://127.0.0.1:4723");
            startTime = System.currentTimeMillis();
            driver = new AndroidDriver<MobileElement>(url, cap);
            

            try {
                System.out.println("Checking for Login/Signup splash screen...");
                WebDriverWait shortWait = new WebDriverWait(driver, 5);
                

                String skipXpath = "//*[contains(translate(@text, 'SKIP SIGN IN', 'skip sign in'), 'skip sign in') " +
                                   "or contains(translate(@text, 'NOT NOW', 'not now'), 'not now') " +
                                   "or @content-desc='Skip sign in']";
                                   
                MobileElement skipSignInBtn = (MobileElement) shortWait.until(
                    ExpectedConditions.visibilityOfElementLocated(By.xpath(skipXpath))
                );
                skipSignInBtn.click();
                System.out.println("Dismissed login screen.");
            } catch (Exception e) {
                System.out.println("No login screen detected, continuing...");
            }
            // --------------------------------------------------------

            wait = new WebDriverWait(driver, 90);
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id("in.amazon.mShop.android.shopping:id/chrome_search_hint_view")));
            launchData.put("status", "success");
        } catch (Exception e) {
            launchData.put("status", "failed");
            launchData.put("error", e.getMessage());
            testResults.put("Step_1_Launch_Data", launchData);
            throw e;
        }
        long totalTime = System.currentTimeMillis() - startTime;
        launchData.put("responseTime", totalTime);
        testResults.put("Step_1_Launch_Data", launchData);
    }


    @Test(priority = 1, dependsOnMethods = { "launchAmazon" })
    public void searchProduct() throws Exception {
        JSONObject searchData = new JSONObject();
        long startTime = 0;
        try {
            wait.until(ExpectedConditions.visibilityOfElementLocated(
                By.id("in.amazon.mShop.android.shopping:id/chrome_search_hint_view"))).click();

            String ui = "in.amazon.mShop.android.shopping:id/rs_search_src_text";
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id(ui)))
               .sendKeys("sony wh 1000xm5");

            startTime = System.currentTimeMillis();
            driver.pressKey(new KeyEvent(AndroidKey.ENTER));

            WebDriverWait shortWait = new WebDriverWait(driver, 10);
            shortWait.until(ExpectedConditions.presenceOfElementLocated(
                By.xpath("//*[contains(@text, 'Sony') or contains(@text, 'sony')]")));

            searchData.put("status", "success");
        } catch (Exception e) {
            searchData.put("status", "failed");
            searchData.put("error", e.getMessage());
            testResults.put("Step_2_Search_Data", searchData);
            throw e;
        }
        long totalTime = System.currentTimeMillis() - startTime;
        searchData.put("responseTime", totalTime);
        testResults.put("Step_2_Search_Data", searchData);
    }

    @Test(priority = 2, dependsOnMethods = { "searchProduct" })
    public void addToCart() throws Exception {
        JSONObject addToCartData = new JSONObject();
        long startTime = 0;
        try {
            dismissBlockingPopups();

            String xpathButton = "//*[contains(translate(@text, 'ADD TO CART', 'add to cart'), 'add to cart') " +
                                 "or contains(translate(@text, 'ADD TO BASKET', 'add to basket'), 'add to basket') " +
                                 "or @content-desc='Add to Cart' or @content-desc='Add to cart']";
            
            boolean buttonClicked = false;

            for (int i = 0; i < 10; i++) {
                try {
                    List<MobileElement> buttons = driver.findElements(By.xpath(xpathButton));
                    for (MobileElement btn : buttons) {
                        if (btn.isDisplayed() && btn.isEnabled()) {
                            startTime = System.currentTimeMillis();
                            btn.click();
                            buttonClicked = true;
                            System.out.println("Clicked the first 'Add to Cart' button found!");
                            break;
                        }
                    }
                    if (buttonClicked) break;
                } catch (Exception e) {}

                PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
                Sequence swipeDown = new Sequence(finger, 1);
                swipeDown.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 500, 1400));
                swipeDown.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
                swipeDown.addAction(finger.createPointerMove(Duration.ofMillis(300), PointerInput.Origin.viewport(), 500, 600));
                swipeDown.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
                driver.perform(Collections.singletonList(swipeDown));
                Thread.sleep(1200);
            }

            if (!buttonClicked) {
                throw new Exception("Could not find any 'Add to Cart' button on the results page after 10 scrolls.");
            }

            try {
                WebDriverWait validationWait = new WebDriverWait(driver, 4);
                validationWait.until(ExpectedConditions.visibilityOfElementLocated(
                    By.xpath("//*[contains(@text, 'Added to Cart') or contains(@text, 'Done') or contains(translate(@text, 'IN CART', 'in cart'), 'in cart') or contains(translate(@text, 'GO TO CART', 'go to cart'), 'go to cart')]")));
            } catch (Exception e) {
                Thread.sleep(500); 
            }

            addToCartData.put("status", "success");
        } catch (Exception e) {
            addToCartData.put("status", "failed");
            addToCartData.put("error", e.getMessage());
            testResults.put("Step_3_Add_To_Cart_Data", addToCartData);
            throw e;
        }
        long totalTime = System.currentTimeMillis() - startTime;
        addToCartData.put("responseTime", totalTime);
        testResults.put("Step_3_Add_To_Cart_Data", addToCartData);
    }

    private void dismissBlockingPopups() {
        try {
            Thread.sleep(1000);
            MobileElement doneBtn = (MobileElement) driver.findElement(
                By.xpath("//*[contains(@text, 'DONE') or contains(@text, 'Done')]"));
            if (doneBtn.isDisplayed()) {
                doneBtn.click();
                Thread.sleep(1000);
            }
        } catch (Exception ignored) {}
        
        try {
            MobileElement closeBtn = (MobileElement) driver.findElement(
                By.xpath("//*[@content-desc='Close' or @text='✕' or @text='X']"));
            if (closeBtn.isDisplayed()) {
                closeBtn.click();
                Thread.sleep(500);
            }
        } catch (Exception ignored) {}
    }

    @Test(priority = 3, dependsOnMethods = { "addToCart" })
    public void openCart() throws Exception {
        JSONObject openCartData = new JSONObject();
        long startTime = 0;
        try {
            boolean clickedCart = false;

            try {
                WebDriverWait shortWait = new WebDriverWait(driver, 4);
                String overlayCartXpath = "//*[@text='Cart' or @text='cart' or contains(@text, 'Go to cart')]";
                MobileElement overlayCartBtn = (MobileElement) shortWait.until(ExpectedConditions.elementToBeClickable(By.xpath(overlayCartXpath)));
                startTime = System.currentTimeMillis();
                overlayCartBtn.click();
                clickedCart = true;
                System.out.println("Opened cart via overlay/inline button.");
            } catch (Exception e) {
                System.out.println("Overlay button not present. Attempting to click top navigation bar icon.");
            }

            if (!clickedCart) {
                try {
                    String doneXpath = "//*[contains(@text, 'DONE') or contains(@text, 'Done')]";
                    driver.findElement(By.xpath(doneXpath)).click();
                    Thread.sleep(1000);
                } catch (Exception e) {}

                String topCartId = "in.amazon.mShop.android.shopping:id/cart_count";
                MobileElement topCartBtn = driver.findElement(By.id(topCartId));
                startTime = System.currentTimeMillis();
                topCartBtn.click();
                System.out.println("Opened cart via top header bar icon.");
            }

            String proceedXpath = "//*[contains(@text, 'Proceed to Buy') or contains(@text, 'Proceed to checkout') or contains(@text, 'Subtotal')]";
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.xpath(proceedXpath)));

            openCartData.put("status", "success");
        } catch (Exception e) {
            openCartData.put("status", "failed");
            openCartData.put("error", e.getMessage());
            testResults.put("Step_4_Open_Cart_Data", openCartData);
            throw e;
        }
        long totalTime = System.currentTimeMillis() - startTime;
        openCartData.put("responseTime", totalTime);
        testResults.put("Step_4_Open_Cart_Data", openCartData);
    }

    @Test(priority = 4, dependsOnMethods = { "openCart" })
    public void removeProduct() throws Exception {
        JSONObject removeProductData = new JSONObject();
        long startTime = 0;
        try {
            PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
            Sequence swipeUp = new Sequence(finger, 1);
            swipeUp.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 500, 1500));
            swipeUp.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            swipeUp.addAction(finger.createPointerMove(Duration.ofMillis(300), PointerInput.Origin.viewport(), 500, 500));
            swipeUp.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));

            boolean deleteFound = false;
            for (int i = 0; i < 6; i++) {
                try {
                    String xpath = "//*["
                            + "contains(translate(@text, 'DELETE', 'delete'), 'delete') or "
                            + "contains(translate(@content-desc, 'DELETE', 'delete'), 'delete') or "
                            + "contains(translate(@resource-id, 'DELETE', 'delete'), 'delete') or "
                            + "contains(translate(@text, 'REMOVE', 'remove'), 'remove')"
                            + "]";
                    MobileElement deleteBtn = driver.findElement(By.xpath(xpath));
                    if (deleteBtn.isDisplayed() && deleteBtn.isEnabled()) {
                        startTime = System.currentTimeMillis();
                        deleteBtn.click();
                        deleteFound = true;
                        break;
                    }
                } catch (Exception e) {
                    driver.perform(Collections.singletonList(swipeUp));
                    Thread.sleep(1500);
                }
            }

            if (!deleteFound) {
                throw new Exception("Delete/Remove option not found in cart after scrolling.");
            }

            String confirmXpath = "//*["
                    + "contains(translate(@text, 'REMOVEDEMPTY', 'removedempty'), 'removed') or "
                    + "contains(translate(@text, 'REMOVEDEMPTY', 'removedempty'), 'empty')"
                    + "]";
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.xpath(confirmXpath)));

            removeProductData.put("status", "success");
        } catch (Exception e) {
            removeProductData.put("status", "failed");
            removeProductData.put("error", e.getMessage());
            testResults.put("Step_5_Remove_Product_Data", removeProductData);
            throw e;
        }
        long totalTime = System.currentTimeMillis() - startTime;
        removeProductData.put("responseTime", totalTime);
        testResults.put("Step_5_Remove_Product_Data", removeProductData);
    }
}
