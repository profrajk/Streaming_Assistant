package appTests;

import io.appium.java_client.MobileBy;
import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;

import org.openqa.selenium.By;
import org.openqa.selenium.remote.DesiredCapabilities;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import org.testng.annotations.AfterClass;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.Test;

import java.net.URL;

public class ClearCacheTest {

    private AndroidDriver<MobileElement> driver;
    private WebDriverWait wait;

    @BeforeClass
    public void setup() throws Exception {

        DesiredCapabilities cap = new DesiredCapabilities();

        cap.setCapability("deviceName", "OnePlus 11R");
        cap.setCapability("udid", "d335e940");
        cap.setCapability("platformName", "Android");
        cap.setCapability("platformVersion", "14");
        cap.setCapability("automationName", "UiAutomator2");

        cap.setCapability("noReset", true);
        cap.setCapability("dontStopAppOnReset", true);
        cap.setCapability("newCommandTimeout", 600);

        URL url = new URL("http://127.0.0.1:4723");

        driver = new AndroidDriver<>(url, cap);
        wait = new WebDriverWait(driver, 20);
    }

    @Test
    public void clearAppsCache() throws Exception {

        ensureSettingsForeground();

        openAppManagement();

        clearCacheForApp("Amazon");

        returnToAppList();

        clearCacheForApp("YouTube");

        System.out.println("✅ Cache clearing completed.");
        
        // Call the new method to exit settings
        exitSettings(); 
    }

    private void ensureSettingsForeground() throws Exception {

        driver.pressKey(new KeyEvent(AndroidKey.HOME));
        Thread.sleep(1000);

        for (int i = 1; i <= 3; i++) {

            System.out.println("Opening Settings Attempt " + i);

            driver.activateApp("com.android.settings");

            Thread.sleep(2000);

            String currentPackage = driver.getCurrentPackage();

            System.out.println("Current package : " + currentPackage);

            if (currentPackage.equals("com.android.settings")) {

                try {

                    wait.until(ExpectedConditions.presenceOfElementLocated(
                            By.xpath(
                                    "//*[@content-desc='Search' or contains(@text,'Settings')]")));

                    System.out.println("Settings opened.");

                    return;

                } catch (Exception e) {
                }
            }

            driver.pressKey(new KeyEvent(AndroidKey.BACK));

            Thread.sleep(1000);
        }

        throw new Exception("Unable to open Settings.");
    }

    private void openAppManagement() {

        String appsScroll =
                "new UiScrollable(new UiSelector().scrollable(true))" +
                        ".scrollIntoView(new UiSelector().text(\"Apps\"))";

        driver.findElement(MobileBy.AndroidUIAutomator(appsScroll)).click();

        wait.until(ExpectedConditions.visibilityOfElementLocated(
                By.xpath("//*[contains(@text,'App management')]")))
                .click();

        System.out.println("App Management opened.");
    }

    private void clearCacheForApp(String appName) throws Exception {

        System.out.println("Opening " + appName);

        String scrollToApp =
                "new UiScrollable(new UiSelector().scrollable(true))" +
                        ".scrollIntoView(new UiSelector().textContains(\""
                        + appName + "\"))";

        driver.findElement(MobileBy.AndroidUIAutomator(scrollToApp)).click();

        wait.until(ExpectedConditions.visibilityOfElementLocated(
                By.xpath("//*[contains(@text,'Storage usage') or contains(@text,'Storage')]")))
                .click();

        String clearCacheXpath =
                "//*[contains(translate(@text,'CLEAR CACHE','clear cache'),'clear cache')]";

        MobileElement clearCacheButton =
                (MobileElement) wait.until(
                        ExpectedConditions.visibilityOfElementLocated(
                                By.xpath(clearCacheXpath)));

        if (clearCacheButton.isEnabled()) {

            clearCacheButton.click();

            System.out.println(appName + " cache cleared.");

            Thread.sleep(1500);

        } else {

            System.out.println(appName + " cache already 0 B.");
        }
    }

    private void returnToAppList() throws Exception {

        driver.navigate().back();

        Thread.sleep(500);

        driver.navigate().back();

        Thread.sleep(1000);
    }

    // --- NEW METHOD ADDED HERE ---
    private void exitSettings() throws Exception {
        
        System.out.println("Exiting Settings and returning to Home Screen...");
        
        // Simulates pressing the physical/virtual Home button
        driver.pressKey(new KeyEvent(AndroidKey.HOME));
        
        // Alternatively, if you want to completely kill the settings app process in the background, 
        // you could uncomment the line below:
        // driver.terminateApp("com.android.settings");
        
        Thread.sleep(1000);
    }

    @AfterClass
    public void tearDown() {

        if (driver != null) {

            driver.quit();
        }
    }
}
