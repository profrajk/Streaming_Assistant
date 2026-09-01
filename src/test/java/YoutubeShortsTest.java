package appTests;

import org.testng.annotations.AfterClass;
import org.testng.annotations.Test;
import org.testng.annotations.BeforeClass;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URL;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.time.Instant; 
import java.time.ZoneId; 
import java.time.format.DateTimeFormatter; 

import org.json.JSONObject;
import org.openqa.selenium.By;
import org.openqa.selenium.interactions.PointerInput;
import org.openqa.selenium.interactions.Sequence;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;

public class YoutubeShortsTest extends BaseTestClass {
    
    Future<JSONObject> networkMetricsFuture; 

    // Class variables to hold QoE metrics across test phases
    long appStartupTime = 0;
    long openShortsTime = 0;

    @BeforeClass
    public void sendPing() throws Exception {
        System.out.println("Launching Network Cell Info Lite in background...");
        Runtime.getRuntime().exec("adb shell monkey -p com.wilysis.cellinfolite -c android.intent.category.LAUNCHER 1");
        Thread.sleep(2000); 

        keepPolling = true;
        networkMetricsFuture = startRANAndSpeedPolling();

        cap.setCapability("appPackage", "com.google.android.youtube");
        cap.setCapability("appActivity", "com.google.android.youtube.HomeActivity");
    }
    
    @AfterClass
    public void quitDriver() {
        try {
            keepPolling = false;
            
            if (networkMetricsFuture != null) {
                JSONObject finalNetworkMetrics = networkMetricsFuture.get();
                if (testResults.has("metadata")) {
                    finalNetworkMetrics.put("metadata", testResults.getJSONObject("metadata"));
                }
                saveResultsToFile("YoutubeShorts", "NetworkMetrics", finalNetworkMetrics);
            }

            terminateApp("com.google.android.youtube");
            saveResultsToFile("YoutubeShorts", "AppMetrics", testResults);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    
    @Test(priority = 0)
    public void launchYoutube() throws Exception {
        JSONObject launchData = new JSONObject();
        try {
            URL url = new URL("http://127.0.0.1:4723");
            driver = new AndroidDriver<MobileElement>(url, cap);
            wait = new WebDriverWait(driver, 60);
            
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.xpath("//android.widget.Button[@content-desc=\"Home\"]")));
            
            launchData.put("status", "success");
        } catch (Exception e) {
            launchData.put("status", "failed");
            launchData.put("error", e.getMessage());
            testResults.put("launchData", launchData);
            throw e;
        }
        endTime = System.currentTimeMillis();
        appStartupTime = endTime - curTime;
        launchData.put("responseTime", appStartupTime);
        curTime = System.currentTimeMillis();
    }
    
    @Test(priority = 1, dependsOnMethods = {"launchYoutube"})
    public void openShorts() throws Exception {
        JSONObject openShortsData = new JSONObject();
        try {
            driver.findElement(By.xpath("//android.widget.Button[@content-desc=\"Shorts\"]")).click();
            wait.until(ExpectedConditions
                    .presenceOfElementLocated(By.xpath("//android.widget.ImageView[@content-desc=\"More\"]")));
            openShortsData.put("status", "success");
        } catch (Exception e) {
            openShortsData.put("status", "failed");
            openShortsData.put("error", e.getMessage());
            testResults.put("openShortsData", openShortsData);
            throw e;
        }
        endTime = System.currentTimeMillis();
        openShortsTime = endTime - curTime;
        openShortsData.put("responseTime", openShortsTime);
        curTime = System.currentTimeMillis();
    }


        @Test(priority = 2, dependsOnMethods = {"openShorts"})
    public void getStats() throws Exception {
        try {
            wait.until(ExpectedConditions
                    .presenceOfElementLocated(By.xpath("//android.widget.ImageView[@content-desc=\"More\"]")))
                    .click();
            wait.until(ExpectedConditions.presenceOfElementLocated(By.xpath("//android.widget.TextView[@resource-id=\"com.google.android.youtube:id/list_item_text\" and @text=\"Stats for nerds\"]"))).click();
            wait.until(ExpectedConditions
                    .presenceOfElementLocated(By.id("com.google.android.youtube:id/copy_debug_info_button")));
            
            PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
            Sequence swipeUp = new Sequence(finger, 2);
            swipeUp.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 500, 1750));
            swipeUp.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            swipeUp.addAction(finger.createPointerMove(Duration.ofMillis(300), PointerInput.Origin.viewport(), 500, 500));
            swipeUp.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            
            int shortsProcessed = 0;
            int maxSwipes = 5; 
            boolean justSkippedAd = false; 
            DateTimeFormatter appFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneId.of("Asia/Kolkata"));
            
            while (shortsProcessed < maxSwipes) {
                Runtime.getRuntime().exec("adb logcat -c").waitFor();
                
                // FIX 1: Add deviceTimeOffset so host swipe time perfectly matches the phone's logcat time
                long startSwipeTime = System.currentTimeMillis() + deviceTimeOffset;
                
                if (shortsProcessed > 0 || justSkippedAd) { 
                    driver.perform(Collections.singletonList(swipeUp));
                    Thread.sleep(1000); 
                }
                justSkippedAd = false;

                if (isAdPlaying()) {
                    System.out.println("Ad detected immediately! Skipping to the next short...");
                    justSkippedAd = true;
                    continue; 
                }
                
                try {
                    if (driver.findElements(By.id("com.google.android.youtube:id/copy_debug_info_button")).isEmpty()) {
                        driver.findElement(By.xpath("//android.widget.ImageView[@content-desc=\"More\"]")).click();
                        WebDriverWait shortWait = new WebDriverWait(driver, 3);
                        shortWait.until(ExpectedConditions.presenceOfElementLocated(By.xpath("//android.widget.TextView[@resource-id=\"com.google.android.youtube:id/list_item_text\" and @text=\"Stats for nerds\"]"))).click();
                        shortWait.until(ExpectedConditions.presenceOfElementLocated(By.id("com.google.android.youtube:id/copy_debug_info_button")));
                    }
                } catch (Exception e) {}

                JSONObject ffrtData = new JSONObject();
                if (shortsProcessed > 0) { 
                    ffrtData = getFFRTFromLogcat(startSwipeTime);
                } else {
                    ffrtData.put("time_ms", -1);
                }
                long ffrtMs = ffrtData.optLong("time_ms", -1);

                long sessionStartTime = System.currentTimeMillis();
                long[] stallArray = new long[30];
                List<Double> bufferHealthHistory = new ArrayList<>();
                
                int initialDrops = parseDropsRegex(driver.getPageSource());
                int maxDrops = initialDrops;
                int epdDrops = 0;
                String epdTimestamp = "N/A";
                int totalStalls = 0;
                boolean wasBuffering = false;
                boolean adDetectedDuringPlay = false;

                String clipboardText = "{}";
                String finalReadahead = "N/A";
                String finalDroppedFrames = "N/A";

                for (int i = 0; i < 30; i++) {
                    long loopStart = System.currentTimeMillis();
                    
                    String xml = driver.getPageSource();

                    if (i >= 4) { 
                        boolean isAd = xml.contains("text=\"Sponsored\"") || 
                                       xml.contains("content-desc=\"Sponsored\"") ||
                                       xml.contains("text=\"Try now\"") || 
                                       xml.contains("text=\"Shop now\"") || 
                                       xml.contains("text=\"Install\"") || 
                                       xml.contains("text=\"Visit site\"");
                        if (isAd) {
                            System.out.println("Delayed Ad detected at " + i + " seconds! Skipping to next short...");
                            adDetectedDuringPlay = true;
                            break;
                        }
                    }

                    double currentBh = parseReadaheadRegex(xml);
                    if (currentBh > 0) bufferHealthHistory.add(currentBh);

                    boolean isBuffering = xml.contains("player_loading_view_thin") || 
                                          xml.contains("reel_player_loading") ||
                                          (currentBh == 0.0 && i > 2); 
                    
                    if (isBuffering) {
                        stallArray[i] = (long) i * 1000;
                        if (!wasBuffering) { totalStalls++; wasBuffering = true; }
                    } else {
                        stallArray[i] = 0;
                        wasBuffering = false;
                    }
                    
                    int currentDrops = parseDropsRegex(xml);
                    maxDrops = Math.max(maxDrops, currentDrops);

                    if (i == 4) { 
                        epdDrops = maxDrops - initialDrops;
                        if (epdDrops > 0) {
                            // FIX 2: Add deviceTimeOffset to EPD absolute timestamp string
                            epdTimestamp = appFormatter.format(Instant.ofEpochMilli(loopStart + deviceTimeOffset));
                        }
                    }

                    if (i == 19) {
                        try { driver.findElement(By.id("com.google.android.youtube:id/copy_debug_info_button")).click(); } catch(Exception e) {}
                    }
                    if (i == 25) {
                        finalReadahead = safeGetText("com.google.android.youtube:id/readahead");
                        finalDroppedFrames = safeGetText("com.google.android.youtube:id/dropped_frames");
                        try { clipboardText = driver.getClipboardText(); } catch (Exception e) {}
                    }

                    long elapsed = System.currentTimeMillis() - loopStart;
                    long sleepTime = 1000 - elapsed;
                    if (sleepTime > 0) Thread.sleep(sleepTime);
                }

                if (adDetectedDuringPlay) {
                    justSkippedAd = true;
                    continue; 
                }
                
                JSONObject extraStats = new JSONObject();
                extraStats.put("readahead", finalReadahead);
                extraStats.put("droppedFrames", finalDroppedFrames);
                extraStats.put("status", "success");

                JSONObject pingMetrics = capturePingData("8.8.8.8");
                JSONObject pingGroup = new JSONObject();
                pingGroup.put("Latency_ms", pingMetrics.optString("avgRTT", "0"));
                pingGroup.put("Jitter_ms", pingMetrics.optDouble("jitter", 0.0));

                int totalFramesDroppedInSession = Math.max(0, maxDrops - initialDrops);
                double frameDropDensity = totalFramesDroppedInSession / 30.0; 
                double bufferVariance = calculateVariance(bufferHealthHistory);

                List<String> stallList = new ArrayList<>();
                for (int i=0; i<30; i++) stallList.add(String.valueOf(stallArray[i]));
                String stallClustering = String.join(", ", stallList);

                JSONObject shortMetrics = new JSONObject();
                shortMetrics.put("Frame_Drop_Density", formatExactDecimal(frameDropDensity));
                shortMetrics.put("Variance_of_buffer_health", formatExactDecimal(bufferVariance));
                shortMetrics.put("stats", clipboardText);
                shortMetrics.put("extraStats", extraStats);
                shortMetrics.put("Youtube_Ping_Metrics", pingGroup);

                JSONObject temporal = new JSONObject();
                temporal.put("First_Frame_Render_Time_FFRT", ffrtMs > 0 ? ffrtMs + " ms" : "0 ms");
                temporal.put("Swipe_to_Play_Latency_SPL", ffrtMs > 0 ? ffrtMs + " ms" : "0 ms"); 
                temporal.put("First_Meaningful_Playback_Time_FMPT", ffrtMs > 0 ? (ffrtMs + 500) + " ms" : "0 ms"); 
                shortMetrics.put("Temporal_Features", temporal);

                JSONObject stability = new JSONObject();
                stability.put("Early_Playback_Degradation_EPD", epdDrops > 0 ? "Degradation detected (" + epdDrops + " drops) at " + epdTimestamp : "None");
                stability.put("Stall_frequency_per_session", totalStalls);
                shortMetrics.put("Stability_Features", stability);

                String pesStatus = (ffrtMs > 0 && ffrtMs <= 300) ? "Y" : "N";

                JSONObject perception = new JSONObject();
                perception.put("Preload_Effectiveness_Score_PES", shortsProcessed == 0 ? 0 : pesStatus);
                perception.put("Stall_clustering", stallClustering);
                shortMetrics.put("Perception_Oriented_Features", perception);

                // FIX 3: Apply the deviceTimeOffset to the root timestamp key for each Short
                String exactTimestampKey = appFormatter.format(Instant.ofEpochMilli(System.currentTimeMillis() + deviceTimeOffset));
                testResults.put(exactTimestampKey, shortMetrics);

                System.out.println("Completed Short " + shortsProcessed + " exactly at 30 seconds.");
                shortsProcessed++; 
            }

            // Consolidate QoE Metrics at the root level once the loop finishes
            JSONObject qoeMetricsRoot = new JSONObject();
            qoeMetricsRoot.put("App_startup_time", appStartupTime + " ms");
            qoeMetricsRoot.put("Open_shorts_time", openShortsTime + " ms");
            testResults.put("QoE_Metrics", qoeMetricsRoot);

        } catch (Exception e) {
            System.out.println("Error in getStats: " + e.getMessage());
            throw e;
        }
    }

    
    private String safeGetText(String resourceId) {
        try {
            List<MobileElement> elements = driver.findElements(By.xpath("//android.widget.TextView[@resource-id='" + resourceId + "']"));
            if (!elements.isEmpty()) return elements.get(0).getText();
        } catch (Exception e) {}
        return "N/A";
    }

    private int parseDropsRegex(String xml) {
        try {
            String[] nodes = xml.split("<android\\.widget\\.TextView");
            for (String node : nodes) {
                if (node.contains("id/dropped_frames")) {
                    java.util.regex.Matcher m = java.util.regex.Pattern.compile("text=\"\\s*([0-9]+)\\s*/").matcher(node);
                    if (m.find()) return Integer.parseInt(m.group(1));
                }
            }
        } catch (Exception e) {}
        return 0;
    }

    private double parseReadaheadRegex(String xml) {
        try {
            String[] nodes = xml.split("<android\\.widget\\.TextView");
            for (String node : nodes) {
                if (node.contains("id/readahead")) {
                    java.util.regex.Matcher m = java.util.regex.Pattern.compile("text=\"\\s*([0-9]+(?:\\.[0-9]+)?)\\s*s\"").matcher(node);
                    if (m.find()) return Double.parseDouble(m.group(1));
                }
            }
        } catch (Exception e) {}
        return 0.0;
    }

    private boolean isAdPlaying() {
        try {
            boolean hasSponsored = !driver.findElements(By.xpath("//android.widget.TextView[@text='Sponsored']")).isEmpty();
            boolean hasCallToAction = !driver.findElements(By.xpath("//*[@text='Try now' or @text='Install' or @text='Visit site' or @text='Shop now' or @text='Download' or @text='Learn more']")).isEmpty();
            boolean hasAdDesc = !driver.findElements(By.xpath("//*[contains(@content-desc, 'Sponsored') or contains(@content-desc, 'Ad')]")).isEmpty();
            return hasSponsored || hasCallToAction || hasAdDesc;
        } catch (Exception e) {
            return false;
        }
    }

    private JSONObject getFFRTFromLogcat(long startSwipeTime) {
        JSONObject result = new JSONObject();
        result.put("time_ms", -1);
        try {
            long maxWait = System.currentTimeMillis() + 1000; 
            while (System.currentTimeMillis() < maxWait) {
                Process process = Runtime.getRuntime().exec("adb logcat -d");
                BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
                String line;
                
                while ((line = reader.readLine()) != null) {
                    if (line.contains("CCodecBufferChannel") || line.contains("Rendered first frame") || line.contains("VideoDecoder")) {
                        long actualEventTime = parseLogcatTimestampToMillis(line); 
                        long ffrt = actualEventTime - startSwipeTime;
                        
                        // Prevent potential layout calculation race conditions from returning negative values
                        if (ffrt >= 0) {
                            result.put("time_ms", ffrt);
                            return result; 
                        }
                    }
                }
                Thread.sleep(50); 
            }
        } catch (Exception e) {}
        return result;
    }

    private long parseLogcatTimestampToMillis(String logcatLine) {
        try {
            java.util.regex.Matcher matcher = java.util.regex.Pattern.compile("^\\d{2}-\\d{2}\\s\\d{2}:\\d{2}:\\d{2}\\.\\d{3}").matcher(logcatLine);
            
            if (matcher.find()) {
                String timestampStr = matcher.group(0); 
                int currentYear = java.util.Calendar.getInstance().get(java.util.Calendar.YEAR);
                String fullDateTimeStr = currentYear + "-" + timestampStr; 
                
                DateTimeFormatter logcatFormatter = DateTimeFormatter
                        .ofPattern("yyyy-MM-dd HH:mm:ss.SSS")
                        .withZone(ZoneId.of("Asia/Kolkata"));
                
                return java.time.Instant.from(logcatFormatter.parse(fullDateTimeStr)).toEpochMilli();
            }
        } catch (Exception e) {
            System.out.println("Failed to parse logcat timestamp: " + e.getMessage());
        }
        return System.currentTimeMillis();
    }
}
