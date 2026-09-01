package appTests;

import java.net.URL;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.json.JSONObject;
import org.openqa.selenium.By;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.testng.annotations.AfterClass;
import org.testng.annotations.BeforeClass;
import org.testng.annotations.Test;

import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;

public class NetworkCellInfoTest extends BaseTestClass {

    Future<JSONObject> networkMetricsFuture;

    @BeforeClass
    public void setupAndStartPolling() throws Exception {
        System.out.println("Starting background ADB polling...");
        keepPolling = true;
        networkMetricsFuture = startRANAndSpeedPolling();
    }
    
    @AfterClass
    public void quitDriverAndSaveMetrics() {

        try {

            keepPolling = false;

            if (networkMetricsFuture != null) {

                try {

                    JSONObject finalNetworkMetrics =
                            networkMetricsFuture.get(10, TimeUnit.SECONDS);

                    if (testResults.has("metadata")) {

                        finalNetworkMetrics.put(
                                "metadata",
                                testResults.getJSONObject("metadata"));
                    }

                    saveResultsToFile(
                            "NetworkCellInfo",
                            "BackgroundMetrics",
                            finalNetworkMetrics);

                }
                catch (TimeoutException e) {

                    System.out.println("Polling timeout.");

                }
                catch (Exception e) {

                    e.printStackTrace();
                }
            }

            saveResultsToFile(
                    "NetworkCellInfo",
                    "AppMetrics",
                    testResults);

            if (driver != null) {

                try {

                    System.out.println("Going to HOME");

                    driver.pressKey(new KeyEvent(AndroidKey.HOME));

                    Thread.sleep(1000);

                }
                catch (Exception ignored) {
                }

                try {

                    System.out.println("Stopping Network Cell Info Lite");

                    terminateApp("com.wilysis.cellinfolite");

                    Thread.sleep(1000);

                }
                catch (Exception ignored) {
                }

                try {

                    System.out.println("Closing Appium session");

                    driver.quit();

                    driver = null;

                }
                catch (Exception ignored) {
                }

            }
            else {

                Runtime.getRuntime().exec(
                        "adb shell am force-stop com.wilysis.cellinfolite");
            }

        }
        catch (Exception e) {

            e.printStackTrace();
        }
    }
    
    @Test(priority = 0)
    public void launchNetworkCellInfoLite() throws Exception {
        JSONObject launchData = new JSONObject();
        try {
            URL url = new URL("http://127.0.0.1:4723");
            driver = new AndroidDriver<MobileElement>(url, cap);
            // 120 second wait gives plenty of time for the speed test to finish later
            wait = new WebDriverWait(driver, 120); 

            System.out.println("Launching Network Cell Info Lite...");

            // Launch the app using Appium's built-in command instead of ADB
            driver.activateApp("com.wilysis.cellinfolite");

            Thread.sleep(2000); // Give the UI a moment to render

            wait.until(ExpectedConditions.visibilityOfElementLocated(By.xpath("//android.widget.TextView[@text=\"GAUGE\" or @text=\"RAW\"]")));
            launchData.put("status", "success");
            
        } catch (Exception e) {
            launchData.put("status", "failed");
            launchData.put("error", e.getMessage());
            testResults.put("launchData", launchData);
            System.out.println("Error in launching Network Cell Info Lite: " + e.getMessage());
            throw e;
        }
        endTime = System.currentTimeMillis();
        long totalTime = endTime - curTime;
        launchData.put("responseTime", totalTime);
        testResults.put("launchData", launchData);
        System.out.println("Time taken to launch the Network Cell Info Lite: " + totalTime + " milliseconds");
        curTime = System.currentTimeMillis();
    }
    
    @Test(priority = 1, dependsOnMethods = { "launchNetworkCellInfoLite" })
    public void getPhysicalParameters() throws Exception {
        JSONObject testset = new JSONObject();
        try {
            driver.findElement(By.xpath("//android.widget.TextView[@text=\"RAW\"]")).click();
            Thread.sleep(1000);
            
            try {
                MobileElement networkOperator = driver.findElement(By.id("com.wilysis.cellinfolite:id/nw_operator"));
                String operatorValue = networkOperator.getText();
                System.out.println("Operator name: " + operatorValue);
                testset.put("OperatorName", operatorValue);
            } catch (Exception e) {}

            for(int i = 0; i < 5; i++) {
                String test = "test_" + i;
                JSONObject physicalParamsData = new JSONObject();
                
                // RSRP
                try {
                    MobileElement rsrp = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_dbm"));
                    physicalParamsData.put("RSRP", rsrp.getText());
                } catch (Exception e) {}
                
                // ASU
                try {
                    MobileElement asu = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_asu"));
                    physicalParamsData.put("ASU", asu.getText());
                } catch (Exception e) {}
                
                // Power
                try {
                    MobileElement power = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_power"));
                    physicalParamsData.put("Power", power.getText());
                } catch (Exception e) {}
                
                // RSRQ
                try {
                    MobileElement rsrq = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_rsrq"));
                    physicalParamsData.put("RSRQ", rsrq.getText());
                } catch (Exception e) {}
                
                // RSSNR
                try {
                    MobileElement rssnr = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_snr"));
                    physicalParamsData.put("RSSNR", rssnr.getText());
                } catch (Exception e) {}
                
                // Band
                try {
                    MobileElement band = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_band"));
                    physicalParamsData.put("Band", band.getText());
                } catch (Exception e) {}
                
                // SS_RSRP
                try {
                    MobileElement ss_rsrp = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_ss_rsrp"));
                    physicalParamsData.put("SS_RSRP", ss_rsrp.getText());
                } catch (Exception e) {}
                
                // SS_RSRQ
                try {
                    MobileElement ss_rsrq = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_ss_rsrq"));
                    physicalParamsData.put("SS_RSRQ", ss_rsrq.getText());
                } catch (Exception e) {}
                
                // SS_SINR
                try {
                    MobileElement ss_sinr = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_ss_sinr"));
                    physicalParamsData.put("SS_SINR", ss_sinr.getText());
                } catch (Exception e) {}
                
                // TA (Timing Advance)
                try {
                    MobileElement ta = driver.findElement(By.id("com.wilysis.cellinfolite:id/tv_ta"));
                    physicalParamsData.put("TA", ta.getText());
                } catch (Exception e) {}
                
                testset.put(test, physicalParamsData);
                System.out.println("Captured Physical Parameters Loop: " + i);
                Thread.sleep(1000);
            }
            
            testset.put("status", "success");
        } catch (Exception e) {
            testset.put("status", "failed");
            testset.put("error", e.getMessage());
            testResults.put("physicalParamsData", testset);
            System.out.println("Error in getting physical parameters: " + e.getMessage());
            throw e;
        }
        testResults.put("physicalParamsData", testset);
    }

    @Test(priority = 2, dependsOnMethods = { "getPhysicalParameters" })
    public void getNetworkParameters() throws Exception {
        JSONObject networkParamsData = new JSONObject();
        try {
            driver.findElement(By.xpath("//android.widget.TextView[@text=\"SPEED\"]")).click();
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id("com.wilysis.cellinfolite:id/startTestButton"))).click();
            
            System.out.println("Speed test started, waiting for completion...");
            // Using the 120s wait to handle network test delay
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id("com.wilysis.cellinfolite:id/done_button")));
            
            MobileElement downloadSpeed = driver.findElement(By.id("com.wilysis.cellinfolite:id/download_tv"));
            String speed_val = downloadSpeed.getText();
            System.out.println("Download Speed value: " + speed_val);
            networkParamsData.put("Download_Speed", speed_val);
            
            MobileElement uploadSpeed = driver.findElement(By.id("com.wilysis.cellinfolite:id/upload_tv"));
            String uploadSpeed_val = uploadSpeed.getText();
            System.out.println("Upload Speed value: " + uploadSpeed_val);
            networkParamsData.put("Upload_Speed", uploadSpeed_val);
            
            MobileElement ping = driver.findElement(By.id("com.wilysis.cellinfolite:id/ping_tv"));
            String ping_val = ping.getText();
            System.out.println("Ping value: " + ping_val);
            networkParamsData.put("Ping", ping_val);
            
            MobileElement jitter = driver.findElement(By.id("com.wilysis.cellinfolite:id/jitter_tv"));
            String jitter_val = jitter.getText();
            System.out.println("Jitter value: " + jitter_val);
            networkParamsData.put("Jitter", jitter_val);
            
            MobileElement type = driver.findElement(By.id("com.wilysis.cellinfolite:id/network_tv"));
            String type_val = type.getText();
            System.out.println("Network Type value: " + type_val);
            networkParamsData.put("Network_Type", type_val);
            
            networkParamsData.put("status", "success");
            
            try {
                driver.findElement(By.id("com.wilysis.cellinfolite:id/done_button")).click();
            } catch (Exception ignored) {
                // Done button might not always appear or be clickable immediately; safely ignore
            }
            
        } catch (Exception e) {
            networkParamsData.put("status", "failed");
            networkParamsData.put("error", e.getMessage());
            testResults.put("networkParamsData", networkParamsData);
            System.out.println("Error in getting network parameters: " + e.getMessage());
            throw e;
        }
        
        endTime = System.currentTimeMillis();
        long totalTime = endTime - curTime;
        networkParamsData.put("responseTime", totalTime);
        testResults.put("networkParamsData", networkParamsData);
        System.out.println("Time taken to get network parameters: " + totalTime + " milliseconds");
    }
}
