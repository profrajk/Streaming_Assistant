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
import java.util.Set;
import java.util.LinkedHashSet;
import java.util.concurrent.Future;
import java.util.concurrent.CompletableFuture;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

import org.json.JSONObject;
import org.openqa.selenium.By;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.openqa.selenium.interactions.PointerInput;
import org.openqa.selenium.interactions.Sequence;

import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;

public class YoutubeTest extends BaseTestClass {

    Future<JSONObject> networkMetricsFuture;
    long videoStartTime = 0;
    
    // Class variables to capture our QoE response timings
    long appStartupTime = 0;
    long searchVideoTime = 0;
    long firstFrameRenderTimeMs = 0;

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
                saveResultsToFile("YoutubeLongForm", "NetworkMetrics", finalNetworkMetrics);
            }

            terminateApp("com.google.android.youtube");
            saveResultsToFile("YoutubeLongForm", "AppMetrics", testResults);
            
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    @Test(priority = 0)
    public void launchYoutube() throws Exception {
        try {
            URL url = new URL("http://127.0.0.1:4723");
            
            long startTime = System.currentTimeMillis();
            driver = new AndroidDriver<MobileElement>(url, cap);
            wait = new WebDriverWait(driver, 60);
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.xpath("//android.widget.Button[@content-desc=\"Home\"]"))).click();
            
            appStartupTime = System.currentTimeMillis() - startTime;
            System.out.println("App startup time captured: " + appStartupTime + " ms");
        } catch (Exception e) {
            System.out.println("Error in launching Youtube: " + e.getMessage());
            throw e;
        }
    }

    @Test(priority = 1, dependsOnMethods = { "launchYoutube" })
    public void searchVideo() throws Exception {
        try {
            System.out.println("Waiting for YouTube home screen UI to settle...");
            Thread.sleep(3500); 

            boolean clickedSearch = false;
            
            for (int i = 0; i < 3; i++) {
                try {
                    driver.findElement(By.xpath("//android.widget.ImageView[@content-desc=\"Search\"]")).click();
                    clickedSearch = true;
                    break; 
                } catch (org.openqa.selenium.StaleElementReferenceException e) {
                    System.out.println("Caught a Stale Element (UI refreshed). Retrying search click...");
                    Thread.sleep(1000); 
                }
            }

            if (!clickedSearch) {
                throw new Exception("Failed to click the Search button after 3 attempts.");
            }

            String searchBoxId = "com.google.android.youtube:id/search_edit_text";
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id(searchBoxId))).sendKeys("Big Buck Bunny"); 
            
            long startTime = System.currentTimeMillis();
            driver.pressKey(new KeyEvent(AndroidKey.ENTER));
            
            wait.until(ExpectedConditions.invisibilityOfElementLocated(By.xpath("//android.widget.ProgressBar[@resource-id=\"com.google.android.youtube:id/load_progress\"]")));
            
            searchVideoTime = System.currentTimeMillis() - startTime;
            System.out.println("Search video time captured: " + searchVideoTime + " ms");
        } catch (Exception e) {
            System.out.println("Error in searching a video: " + e.getMessage());
            throw e;
        }
    }

    @Test(priority = 2, dependsOnMethods = {"searchVideo"})
    public void playVideo() throws Exception {
        try {
            System.out.println("Search results loaded. Scanning layout for 'Big Buck Bunny 60fps' target elements...");
            Thread.sleep(3000);

            String targetTitleXpath = "//*[" +
                    "(contains(translate(@text, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'big buck bunny') or " +
                    "contains(translate(@content-desc, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'big buck bunny')) " +
                    "and not(contains(@resource-id, 'search')) " +
                    "and not(contains(@resource-id, 'edit_text'))" +
                    "]";

            MobileElement targetVideoElement = null;
            boolean titleFound = false;

            for (int i = 0; i < 4; i++) {
                try {
                    List<MobileElement> visibleElements = driver.findElements(By.xpath(targetTitleXpath));
                    for (MobileElement el : visibleElements) {
                        if (el.isDisplayed()) {
                            String elementText = el.getText();
                            String elementDesc = el.getAttribute("content-desc");
                            
                            String combinedString = ((elementText != null ? elementText : "") + " " + 
                                                     (elementDesc != null ? elementDesc : "")).toLowerCase();
                            
                            if (combinedString.contains("big buck bunny") && combinedString.contains("60fps")) {
                                targetVideoElement = el;
                                titleFound = true;
                                break;
                            }
                        }
                    }
                    if (titleFound) break;
                } catch (Exception e) {}

                System.out.println("Target 60fps item missed. Nudging... (Scroll " + (i + 1) + ")");
                PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
                Sequence minorScroll = new Sequence(finger, 1);
                minorScroll.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 500, 1400));
                minorScroll.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
                minorScroll.addAction(finger.createPointerMove(Duration.ofMillis(300), PointerInput.Origin.viewport(), 500, 600));
                minorScroll.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
                driver.perform(Collections.singletonList(minorScroll));
                Thread.sleep(1500);
            }

            if (targetVideoElement == null) {
                throw new Exception("Could not locate the genuine video title component 'Big Buck Bunny 60fps' on screen.");
            }
            
            // Prepare for Logcat read
            Runtime.getRuntime().exec("adb logcat -c").waitFor();

            videoStartTime = System.currentTimeMillis();
            targetVideoElement.click();
            System.out.println("Successfully located and executed click on the target video!");
            
            JSONObject ffrtData = getFFRTFromLogcat(videoStartTime);
            firstFrameRenderTimeMs = ffrtData.optLong("time_ms", 0);
            System.out.println("First Frame Render Time captured: " + firstFrameRenderTimeMs + " ms");

            wait.until(ExpectedConditions.invisibilityOfElementLocated(
                By.xpath("//android.widget.ProgressBar[@resource-id='com.google.android.youtube:id/player_loading_view_thin']")
            ));

        } catch(Exception e){
            System.out.println("Failed to click target video by title: " + e.getMessage());
            throw e;
        }
    }
    
    @Test(priority = 3, dependsOnMethods = { "playVideo" })
    public void getStats() throws Exception {
        try {
            Thread.sleep(2000);
            PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");

            Sequence tapScreen = new Sequence(finger,0);
            tapScreen.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 500, 500));
            tapScreen.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            tapScreen.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(tapScreen));
            Thread.sleep(700);

            Sequence tapGear = new Sequence(finger,1);
            tapGear.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 1160, 225));
            tapGear.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            tapGear.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(tapGear));
            Thread.sleep(1200);

            Sequence tapMore = new Sequence(finger,2);
            tapMore.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 610, 2500));
            tapMore.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            tapMore.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(tapMore));
            Thread.sleep(1200);

            Sequence tapStats = new Sequence(finger,3);
            tapStats.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), 610, 2500));
            tapStats.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            tapStats.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(tapStats));
            
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.id("com.google.android.youtube:id/copy_debug_info_button")));
            System.out.println("Starting absolute scheduled QoS polling (Stats captured every 5 seconds)...");

            DateTimeFormatter timeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneId.of("Asia/Kolkata"));

            boolean wasBuffering = false;
            long currentStallStart = 0;
            int maxResIndexSoFar = -1;
            long firstStallGlobal = -1;
            int lastHeight = -1;
            int totalStallsOverall = 0;
            int maxDropGlobal = 0;
            String finalDroppedFramesStr = "0/0";

            List<String> globalBufferHealthList = new ArrayList<>();
            List<String> globalBitrateList = new ArrayList<>();
            List<String> recoveryTimes = new ArrayList<>();
            Set<String> earlyDegradationTimes = new LinkedHashSet<>(); 
            String timeToFirstStallStr = "0";
            
            int[] stallsPerMinuteArray = new int[5];
            long[] stallClusteringArray = new long[300]; 
            
            MobileElement copyButton = driver.findElement(By.id("com.google.android.youtube:id/copy_debug_info_button"));
            
            JSONObject latestPingData = new JSONObject();
            latestPingData.put("Latency_ms", "0");
            latestPingData.put("Jitter_ms", 0.0);

            long testStart = System.currentTimeMillis();

            for (int interval = 1; interval <= 60; interval++) {
                
                long targetTime = testStart + (interval * 5000); 
                int stallsThisInterval = 0;

                while(System.currentTimeMillis() < targetTime) {
                    boolean isBuffering = checkBuffering();
                    long now = System.currentTimeMillis();
                    long relativeTimeMs = now - videoStartTime; 
                    
                    if (isBuffering && !wasBuffering) {
                        wasBuffering = true;
                        currentStallStart = now;
                        totalStallsOverall++;
                        stallsThisInterval++;
                        
                        if (firstStallGlobal == -1) {
                            firstStallGlobal = relativeTimeMs;
                            timeToFirstStallStr = String.valueOf(relativeTimeMs);
                        }
                        if (relativeTimeMs <= 20000) { 
                            earlyDegradationTimes.add(String.valueOf(relativeTimeMs));
                        }
                    } else if (!isBuffering && wasBuffering) {
                        wasBuffering = false;
                        long recoveryDuration = now - currentStallStart; 
                        recoveryTimes.add(String.valueOf(recoveryDuration));
                    }
                    
                    if (isBuffering) {
                        int secondIndex = (int) (relativeTimeMs / 1000);
                        if (secondIndex >= 0 && secondIndex < 300) {
                            stallClusteringArray[secondIndex] = relativeTimeMs;
                        }
                    }
                    
                    Thread.sleep(150); 
                }
                
                int minuteBucketIndex = (interval - 1) / 12;
                if (minuteBucketIndex < 5) {
                    stallsPerMinuteArray[minuteBucketIndex] += stallsThisInterval;
                }

                copyButton.click();
                
                CompletableFuture.runAsync(() -> {
                    try {
                        JSONObject newPing = capturePingData("youtube.com");
                        latestPingData.put("Latency_ms", newPing.optString("avgRTT", "0"));
                        latestPingData.put("Jitter_ms", newPing.optDouble("jitter", 0.0));
                    } catch (Exception e) {}
                });

                String clipboardText = "{}";
                double currentBh = 0.0;
                String trueFormatText = "N/A";
                String currentDroppedFrames = "N/A";
                
                try {
                    clipboardText = driver.getClipboardText();
                    JSONObject clipObj = new JSONObject(clipboardText);
                    
                    if (clipObj.has("bh")) currentBh = clipObj.optDouble("bh", 0.0) / 1000.0; 
                    if (clipObj.has("vfmt")) {
                        trueFormatText = clipObj.getString("vfmt");
                    } else if (clipObj.has("optimal_res")) {
                        trueFormatText = clipObj.getString("optimal_res");
                    } else if (clipObj.has("fmt")) {
                        trueFormatText = clipObj.getString("fmt");
                    }
                    if (clipObj.has("df")) currentDroppedFrames = clipObj.getString("df");
                    
                } catch (Exception e) {}
                
                finalDroppedFramesStr = currentDroppedFrames;
                double calculatedBitrateKbps = calculateTheoreticalBitrate(trueFormatText);
                
                globalBufferHealthList.add(String.valueOf(currentBh));
                globalBitrateList.add(String.valueOf(calculatedBitrateKbps));

                int height = extractHeight(trueFormatText);
                if (height > 0) {
                    int currentResIdx = getResIndex(height);
                    if (currentResIdx > maxResIndexSoFar) {
                        maxResIndexSoFar = currentResIdx;
                    } else if (currentResIdx < maxResIndexSoFar) {
                        int drop = maxResIndexSoFar - currentResIdx;
                        if (drop > maxDropGlobal) maxDropGlobal = drop;
                    }
                    lastHeight = height;
                }

                String exactTimestampKey = timeFormatter.format(Instant.ofEpochMilli(System.currentTimeMillis() + deviceTimeOffset));
                
                JSONObject intervalData = new JSONObject();
                intervalData.put("stats", clipboardText);
                
                JSONObject appPingMetrics = new JSONObject();
                appPingMetrics.put("Latency_ms", latestPingData.optString("Latency_ms", "0"));
                appPingMetrics.put("Jitter_ms", latestPingData.optDouble("Jitter_ms", 0.0));
                intervalData.put("Youtube_Ping_Metrics", appPingMetrics);

                JSONObject extraStats = new JSONObject();
                extraStats.put("readahead", currentBh + " s");
                extraStats.put("droppedFrames", currentDroppedFrames);
                extraStats.put("status", "success");
                intervalData.put("extraStats", extraStats);
                
                testResults.put(exactTimestampKey, intervalData);
                System.out.println("Captured stats precisely at: " + exactTimestampKey);
            }

            // ==========================================
            // JSON BUILDING: MATCHING THE IMAGE EXACTLY
            // ==========================================

            List<String> stallsPerMinuteFormattedList = new ArrayList<>();
            for (int i = 0; i < 5; i++) {
                stallsPerMinuteFormattedList.add(String.valueOf(stallsPerMinuteArray[i]));
            }
            
            JSONObject qoeMetrics = new JSONObject();
            qoeMetrics.put("App_startup_time", appStartupTime + " ms");
            qoeMetrics.put("Search_video_time", searchVideoTime + " ms");
            testResults.put("QoE_Metrics", qoeMetrics);

            // CATEGORY 1: Stability Features
            JSONObject stabilityFeatures = new JSONObject();
            stabilityFeatures.put("Stall_frequency_per_minute", String.join(", ", stallsPerMinuteFormattedList));
            stabilityFeatures.put("Variance_of_buffer_health", globalBufferHealthList.isEmpty() ? "0" : String.join(", ", globalBufferHealthList));
            stabilityFeatures.put("Bitrate_fluctuation_index", globalBitrateList.isEmpty() ? "0" : String.join(", ", globalBitrateList));
            testResults.put("Stability_Features", stabilityFeatures);
            
            // CATEGORY 2: Temporal Features
            JSONObject temporalFeatures = new JSONObject();
            temporalFeatures.put("Time_to_first_stall", timeToFirstStallStr);
            temporalFeatures.put("Early_session_degradation", earlyDegradationTimes.isEmpty() ? "None" : String.join(", ", earlyDegradationTimes));
            temporalFeatures.put("Recovery_time_after_stall", recoveryTimes.isEmpty() ? "0" : String.join(", ", recoveryTimes));
            temporalFeatures.put("First_Frame_Render_Time_FFRT", firstFrameRenderTimeMs > 0 ? firstFrameRenderTimeMs + " ms" : "0 ms"); 
            testResults.put("Temporal_Features", temporalFeatures);
            
            // CATEGORY 3: Perception-Oriented Features
            JSONObject perceptionFeatures = new JSONObject();
            List<String> stallClustList = new ArrayList<>();
            for (int i = 0; i < 300; i++) {
                stallClustList.add(String.valueOf(stallClusteringArray[i]));
            }
            perceptionFeatures.put("Stall_clustering", String.join(", ", stallClustList));
            
            String resolutionSeverity = "None";
            if (maxDropGlobal == 1) resolutionSeverity = "Mild";
            else if (maxDropGlobal >= 2) resolutionSeverity = "Severe";
            perceptionFeatures.put("Resolution_drop_severity", resolutionSeverity);
            
            double frameDropDensity = calculateFrameDropDensity(finalDroppedFramesStr);
            perceptionFeatures.put("Smoothness_score", formatExactDecimal(calculateSmoothnessScore(totalStallsOverall, frameDropDensity)));
            testResults.put("Perception_Oriented_Features", perceptionFeatures);

            System.out.println("5-minute long-form test completed successfully!");

        } catch(Exception e){
            System.out.println("Error in getStats: " + e.getMessage());
            throw e;
        }
    }

    // ==========================================
    // HELPER METHODS (Fully restored)
    // ==========================================

    public double calculateTheoreticalBitrate(String resolutionText) {
        if (resolutionText == null || resolutionText.equals("N/A")) return 0.0;
        try {
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("([0-9]+)x([0-9]+)(?:@([0-9]+))?").matcher(resolutionText);
            if (m.find()) {
                long width = Long.parseLong(m.group(1));
                long height = Long.parseLong(m.group(2));
                long fps = m.group(3) != null ? Long.parseLong(m.group(3)) : 30; 
                
                double compressionBPP = 0.1;
                return (width * height * fps * compressionBPP) / 1000.0;
            }
        } catch(Exception e) {}
        return 0.0;
    }

    public boolean checkBuffering() {
        try {
            List<MobileElement> elements = driver.findElements(By.xpath("//android.widget.ProgressBar[@resource-id='com.google.android.youtube:id/player_loading_view_thin']"));
            return !elements.isEmpty() && elements.get(0).isDisplayed();
        } catch (Exception e) {
            return false;
        }
    }
    
    public int extractHeight(String optimalRes) {
        if (optimalRes == null || optimalRes.equals("N/A")) return 0;
        try {
            java.util.regex.Matcher m = java.util.regex.Pattern.compile("x(\\d+)").matcher(optimalRes);
            if(m.find()) return Integer.parseInt(m.group(1));
        } catch(Exception e) {}
        return 0;
    }
    
    public int getResIndex(int height) {
        if (height <= 144) return 0;
        if (height <= 240) return 1;
        if (height <= 360) return 2;
        if (height <= 480) return 3;
        if (height <= 720) return 4;
        if (height <= 1080) return 5;
        if (height <= 1440) return 6;
        return 7; 
    }

   public static double calculateFrameDropDensity(String droppedFramesText) {
        if (droppedFramesText == null || droppedFramesText.equals("N/A")) return 0.0;
        try {
            String[] parts = droppedFramesText.split("/");
            if (parts.length == 2) {
                double dropped = Double.parseDouble(parts[0].trim());
                double total = Double.parseDouble(parts[1].trim());
                if (total > 0) return dropped / total;
            }
        } catch (Exception e) {}
        return 0.0;
    }

    private JSONObject getFFRTFromLogcat(long startPlayTime) {
        JSONObject result = new JSONObject();
        result.put("time_ms", -1);
        try {
            long maxWait = System.currentTimeMillis() + 8000; 
            while (System.currentTimeMillis() < maxWait) {
                Process process = Runtime.getRuntime().exec("adb logcat -d");
                BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
                String line;
                
                while ((line = reader.readLine()) != null) {
                    if (line.contains("CCodecBufferChannel") || line.contains("Rendered first frame") || line.contains("VideoDecoder")) {
                        long actualEventTime = parseLogcatTimestampToMillis(line); 
                        
                        // FIX: Time sync logic to prevent 9 million ms spikes
                        long adjustedStartPlayTime = startPlayTime + deviceTimeOffset;
                        long ffrt = actualEventTime - adjustedStartPlayTime;
                        
                        if (ffrt >= 0) {
                            result.put("time_ms", ffrt);
                            return result; 
                        }
                    }
                }
                Thread.sleep(100); 
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
