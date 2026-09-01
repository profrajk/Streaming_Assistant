package appTests;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.io.BufferedReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.math.BigDecimal;

import org.json.JSONObject;
import org.openqa.selenium.remote.DesiredCapabilities;
import org.openqa.selenium.support.ui.WebDriverWait;
import org.testng.annotations.AfterClass;
import org.testng.annotations.BeforeClass;

import io.appium.java_client.MobileElement;
import io.appium.java_client.android.AndroidDriver;

public class BaseTestClass {
	
	static AndroidDriver<MobileElement> driver;
	long startTime;
	long curTime;
	long endTime;
	DesiredCapabilities cap = new DesiredCapabilities();
	JSONObject testResults = new JSONObject();
	WebDriverWait wait;
	LocalDateTime now;
	
    public volatile boolean keepPolling = true;
    public volatile double liveLatency = 0.0;
    public volatile double liveJitter = 0.0;
    
    public volatile long deviceTimeOffset = 0L;

    public static BigDecimal formatExactDecimal(double val) {
        if (Double.isNaN(val) || Double.isInfinite(val)) {
            return BigDecimal.ZERO;
        }
        return new BigDecimal(String.format(java.util.Locale.US, "%.6f", val));
    }
    
    public void syncDeviceTime() {
        try {
            // 1. Get the exact UNIX epoch timestamp (in seconds) from the mobile phone
            Process p = Runtime.getRuntime().exec("adb shell date +%s");
            BufferedReader reader = new BufferedReader(new InputStreamReader(p.getInputStream()));
            String line = reader.readLine();
            
            if (line != null && !line.trim().isEmpty()) {
                long phoneEpochSeconds = Long.parseLong(line.trim());
                
                // 2. Force-update the Jetson Nano's system time using the phone's time
                // '@' tells the Linux date command to parse an exact epoch timestamp
                String setTimeCmd = "sudo date -s @" + phoneEpochSeconds;
                
                // Execute the system time update on the Jetson Nano
                Process syncProcess = Runtime.getRuntime().exec(new String[]{"/bin/sh", "-c", setTimeCmd});
                int exitCode = syncProcess.waitFor();
                
                if (exitCode == 0) {
                    System.out.println("Jetson Nano system clock successfully updated to Phone Time!");
                } else {
                    System.out.println("Sudo time update failed. Falling back to passive offset calculation...");
                }

                // 3. Keep the offset math as a safe backup fallback mechanism
                long phoneTimeMs = phoneEpochSeconds * 1000;
                long jetsonTimeMs = System.currentTimeMillis();
                deviceTimeOffset = phoneTimeMs - jetsonTimeMs;
                
                System.out.println("Time successfully synced with Mobile! Offset applied: " + deviceTimeOffset + "ms");
            }
        } catch (Exception e) {
            System.out.println("Warning: Could not sync time with mobile device. " + e.getMessage());
        }
    }


    @BeforeClass()
	public void initializeTest() {
        syncDeviceTime();

		JSONObject metadata = new JSONObject();
		
        now = Instant.ofEpochMilli(System.currentTimeMillis() + deviceTimeOffset)
                     .atZone(ZoneId.of("Asia/Kolkata"))
                     .toLocalDateTime();
        metadata.put("timestamp", now.toString());

        JSONObject locationData = getlocation();
        metadata.put("location", locationData);

        testResults.put("metadata", metadata);
        
		startTime = System.currentTimeMillis();
		curTime = System.currentTimeMillis();
		cap.setCapability("deviceName", "OnePlus 11R");
		cap.setCapability("udid", "d335e940");
		cap.setCapability("appium:ignoreHiddenApiPolicyError", true);
		cap.setCapability("platformVersion", "14");
		cap.setCapability("platformName", "Android");
		cap.setCapability("automationName", "UiAutomator2");
		cap.setCapability("noReset", true);
		cap.setCapability("fullReset", false);
		cap.setCapability("autoGrantPermissions", true);
		cap.setCapability("autoAcceptAlerts", true);
		cap.setCapability("appium:forceAppLaunch", true);
	}
	
	@AfterClass
	public void noteTime() {
		endTime = System.currentTimeMillis();
		long totalTime = endTime - startTime;
		System.out.println("Time taken for entire test: " + totalTime + " milliseconds");
	}
	
	public static void terminateApp(String appPackage) {
		try {
			driver.terminateApp(appPackage);
			Thread.sleep(2000);
		} catch (InterruptedException e) {
			e.printStackTrace();
		}
		driver.quit();
	}
	
	public static void saveResultsToFile(String appName, String fileSuffix, JSONObject results) {
        String filePath = System.getProperty("user.dir") + "/AppTestLogs/" + appName + "_" + fileSuffix + ".json";

        try (FileWriter file = new FileWriter(filePath, true)) { 
            List<String> keys = new ArrayList<>();
            java.util.Iterator<String> keysIterator = results.keys();
            while (keysIterator.hasNext()) {
                keys.add(keysIterator.next());
            }
            
            // Step 1: Sort everything alphabetically first
            Collections.sort(keys); 
            
            // Step 2: Construct a new list to enforce exact hierarchical placement
            List<String> finalKeys = new ArrayList<>();
            
            // Top elements (metadata first, QoE metrics immediately after)
            if (keys.remove("metadata")) finalKeys.add("metadata");
            if (keys.remove("QoE_Metrics")) finalKeys.add("QoE_Metrics");
            
            // Middle elements (standard test loops, steps, etc.)
            finalKeys.addAll(keys);
            
            // Bottom elements (Youtube features, Ping, and End Timestamp pushed to the very end)
            if (finalKeys.remove("Stability_Features")) finalKeys.add("Stability_Features");
            if (finalKeys.remove("Temporal_Features")) finalKeys.add("Temporal_Features");
            if (finalKeys.remove("Perception_Oriented_Features")) finalKeys.add("Perception_Oriented_Features");
            if (finalKeys.remove("pingData")) finalKeys.add("pingData");
            if (finalKeys.remove("Test_End_Timestamp")) finalKeys.add("Test_End_Timestamp");

            keys = finalKeys;

            StringBuilder sb = new StringBuilder();
            sb.append("{\n");

            for (int i = 0; i < keys.size(); i++) {
                String key = keys.get(i);
                Object value = results.get(key);
                
                sb.append("    \"").append(key).append("\": ");
                
                if (value instanceof JSONObject) {
                    String innerJson = ((JSONObject) value).toString(4);
                    innerJson = innerJson.replaceAll("(?m)^", "    ").replaceFirst("    ", ""); 
                    sb.append(innerJson);
                } else if (value instanceof org.json.JSONArray) {
                    String innerJson = ((org.json.JSONArray) value).toString(4);
                    innerJson = innerJson.replaceAll("(?m)^", "    ").replaceFirst("    ", ""); 
                    sb.append(innerJson);
                } else if (value instanceof String) {
                    sb.append(JSONObject.quote((String)value));
                } else {
                    sb.append(value);
                }
                
                if (i < keys.size() - 1) {
                    sb.append(",");
                }
                sb.append("\n");
            }
            sb.append("}\n");

            file.write(sb.toString());
            System.out.println("Saved " + fileSuffix + " data to: " + filePath);
        } catch (Exception e) {
            System.err.println("Error writing log for app: " + appName);
            e.printStackTrace();
        }	    
	}

    public JSONObject getGeoTime() {
		JSONObject geoTime = new JSONObject();
		geoTime.put("location", getlocation());
		DateTimeFormatter appFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneId.of("Asia/Kolkata"));
		geoTime.put("time", appFormatter.format(Instant.ofEpochMilli(System.currentTimeMillis() + deviceTimeOffset)));
		return geoTime;
	}

	public static JSONObject capturePingData(String url) {
		JSONObject pingData = new JSONObject();
        try {
            Process process = Runtime.getRuntime().exec("adb shell ping -c 5 " + url);
            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;
            Pattern patternTTLTime = Pattern.compile("ttl=(\\d+)\\s+time=([\\d.]+)\\s+ms");
            Pattern patternRTT = Pattern.compile("rtt min/avg/max/mdev = ([\\d.]+)/([\\d.]+)/([\\d.]+)");

            int ttlSum = 0;
            int ttlCount = 0;
            String minRTT = "", avgRTT = "", maxRTT = "";
            double prev = 0, curr = 0, diffsum = 0;
            
            while ((line = reader.readLine()) != null) {
                Matcher matcherTTLTime = patternTTLTime.matcher(line);
                if (matcherTTLTime.find()) {
                    String ttl = matcherTTLTime.group(1);
                    String time = matcherTTLTime.group(2);
                    prev = curr;
                    curr = Double.parseDouble(time);
                    if (prev != 0) diffsum += Math.abs(curr - prev);
                    ttlSum += Integer.parseInt(ttl);
                    ttlCount++;
                }

                Matcher matcherRTT = patternRTT.matcher(line);
                if (matcherRTT.find()) {
                    minRTT = matcherRTT.group(1);
                    avgRTT = matcherRTT.group(2);
                    maxRTT = matcherRTT.group(3);
                }
            }
            
            if (ttlCount > 1) {
                pingData.put("jitter", (double) diffsum / (ttlCount - 1));
            } else {
                pingData.put("jitter", 0.0);
            }

            pingData.put("avgTTL", ttlCount > 0 ? (double) ttlSum / ttlCount : 0);
            pingData.put("minRTT", minRTT);
            pingData.put("avgRTT", avgRTT);
            pingData.put("maxRTT", maxRTT);
        } catch (IOException e) {
        	pingData.put("error", e);
        }
        return pingData;
	}

    public void startContinuousPing(String url) {
        ExecutorService pingExecutor = Executors.newSingleThreadExecutor();
        pingExecutor.submit(() -> {
            try {
                Process process = Runtime.getRuntime().exec("adb shell ping " + url);
                BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
                String line;
                double prevLatency = 0.0;
                
                while (keepPolling && (line = reader.readLine()) != null) {
                    Matcher m = Pattern.compile("time=([\\d.]+)\\s+ms").matcher(line);
                    if (m.find()) {
                        double currentLatency = Double.parseDouble(m.group(1));
                        liveLatency = currentLatency;
                        
                        if (prevLatency > 0.0) {
                            liveJitter = Math.abs(currentLatency - prevLatency);
                        }
                        prevLatency = currentLatency;
                    }
                }
                process.destroy();
            } catch (Exception e) {
                System.out.println("Continuous Ping Error: " + e.getMessage());
            }
        });
    }

    public static JSONObject getlocation() {
        JSONObject locationData = new JSONObject();

        try {
            Process p = Runtime.getRuntime().exec("adb shell dumpsys location");
            BufferedReader reader = new BufferedReader(new InputStreamReader(p.getInputStream()));

            String line;
            String locationLine = null;

            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.contains("last location=Location[fused")) {
                    locationLine = line;
                } else if (locationLine == null && line.contains("last location=Location[network")) {
                    locationLine = line;
                }
            }

            if (locationLine != null) {
                int start = locationLine.indexOf(' ') + 1;
                start = locationLine.indexOf(' ', start) + 1;
                int end = locationLine.indexOf(" hAcc");

                String coords = locationLine.substring(start, end).trim();
                String[] parts = coords.split(",");

                String latitude = parts[0].replace("*", "").trim();
                String longitude = parts[1].replace("*", "").trim();

                String altitude = "";
                int altIndex = locationLine.indexOf("alt=");
                if (altIndex != -1) {
                    int altEnd = locationLine.indexOf(" ", altIndex);
                    if (altEnd == -1) altEnd = locationLine.length();
                    altitude = locationLine.substring(altIndex + 4, altEnd);
                }

                locationData.put("status", "success");
                locationData.put("latitude", latitude);
                locationData.put("longitude", longitude);
                locationData.put("altitude", altitude);
            } else {
                locationData.put("status", "failed");
            }

        } catch (Exception e) {
            locationData.put("status", "failed");
            locationData.put("error", e.getMessage());
        }

        return locationData;
    }

    public static String getCarrierName() {
        try {
            Process p = Runtime.getRuntime().exec("adb shell getprop gsm.operator.alpha");
            BufferedReader reader = new BufferedReader(new InputStreamReader(p.getInputStream()));
            String line = reader.readLine();
            if (line != null && !line.trim().isEmpty()) return line.replace(",", "").trim();
        } catch (Exception e) {}
        return "Unknown";
    }

    public static String deriveBandFromFc(int fc) {
        if (fc >= 0 && fc <= 599) return "1";
        if (fc >= 1200 && fc <= 1949) return "3";
        if (fc >= 2400 && fc <= 2649) return "5";
        if (fc >= 3450 && fc <= 3799) return "8";
        if (fc >= 2750 && fc <= 3449) return "7";
        if (fc >= 38650 && fc <= 39649) return "40";
        if (fc >= 39650 && fc <= 41589) return "41";
        if (fc >= 422000 && fc <= 434000) return "n1";
        if (fc >= 361000 && fc <= 376000) return "n3";
        if (fc >= 173900 && fc <= 178100) return "n5";
        if (fc >= 185000 && fc <= 192000) return "n8";
        if (fc >= 141000 && fc <= 151800) return "n28"; 
        if (fc >= 743333 && fc <= 756666) return "n41";
        if (fc >= 620000 && fc <= 653000) return "n78"; 
        return "UNKNOWN";
    }
	
    public Future<JSONObject> startRANAndSpeedPolling() {
        startContinuousPing("8.8.8.8");

        ExecutorService executor = Executors.newSingleThreadExecutor();
        return executor.submit(() -> {
            JSONObject sessionMetrics = new JSONObject();
            long lastRxBytes = -1;
            long lastTxBytes = -1; 
            long lastTime = System.currentTimeMillis() + deviceTimeOffset;

            int loopCounter = 0;
            int cachedRsrp = -1;
            int cachedRsrq = -1;
            int cachedRssnr = -1;
            String cachedNetworkType = "UNKNOWN";
            int cachedFc = -1;
            String cachedBand = "UNKNOWN";

            DateTimeFormatter timeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS")
                    .withZone(ZoneId.of("Asia/Kolkata"));

            while (keepPolling) {
                JSONObject currentSnapshot = new JSONObject();
                String carrierName = getCarrierName();
                currentSnapshot.put("Carrier", carrierName);
                
                long exactTimestamp = System.currentTimeMillis() + deviceTimeOffset;
                String humanReadableKey = timeFormatter.format(Instant.ofEpochMilli(exactTimestamp));

                try {
                    Process p = Runtime.getRuntime().exec("adb shell cat /proc/net/dev");
                    double dlSpeedMbps = 0.0;
                    double ulSpeedMbps = 0.0;

                    if (p.waitFor(2, java.util.concurrent.TimeUnit.SECONDS)) {
                        BufferedReader reader = new BufferedReader(new InputStreamReader(p.getInputStream()));
                        String line;
                        long totalRx = 0;
                        long totalTx = 0;
                        
                        while ((line = reader.readLine()) != null) {
                            if (line.contains(":")) {
                                String[] splitLine = line.split(":");
                                String iface = splitLine[0].trim();
                                
                                if (!iface.equals("lo") && !iface.contains("wlan") && !iface.contains("p2p")) {
                                    String[] stats = splitLine[1].trim().split("\\s+");
                                    if (stats.length >= 9) {
                                        totalRx += Long.parseLong(stats[0]); 
                                        totalTx += Long.parseLong(stats[8]); 
                                    }
                                }
                            }
                        }
                        
                        if (lastRxBytes != -1 && lastTxBytes != -1) {
                            double timeDelta = (exactTimestamp - lastTime) / 1000.0;
                            if (timeDelta > 0) {
                                dlSpeedMbps = ((totalRx - lastRxBytes) * 8.0 / 1000000.0) / timeDelta;
                                ulSpeedMbps = ((totalTx - lastTxBytes) * 8.0 / 1000000.0) / timeDelta;
                            }
                        }
                        lastRxBytes = totalRx;
                        lastTxBytes = totalTx;
                        lastTime = exactTimestamp;
                    }
                    
                    currentSnapshot.put("Downlink_Speed_Mbps", formatExactDecimal(Math.max(0, dlSpeedMbps)));
                    currentSnapshot.put("Uplink_Speed_Mbps", formatExactDecimal(Math.max(0, ulSpeedMbps)));
                    
                    if (loopCounter % 6 == 0) {
                        Process ranP = Runtime.getRuntime().exec("adb shell dumpsys telephony.registry");
                        BufferedReader ranReader = new BufferedReader(new InputStreamReader(ranP.getInputStream()));
                        String ranLine;
                        
                        while ((ranLine = ranReader.readLine()) != null) {
                            String lowerLine = ranLine.toLowerCase();

                            Matcher techMatcher = Pattern.compile("getrildataradiotechnology=\\d+\\(([a-zA-Z0-9_]+)\\)", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            if (techMatcher.find()) cachedNetworkType = techMatcher.group(1).toUpperCase();

                            Matcher fcMatcher = Pattern.compile("(?:mchannelnumber|mearfcn|mnrarfcn)\\s*=\\s*(\\d+)", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            if (fcMatcher.find()) {
                                int f = Integer.parseInt(fcMatcher.group(1));
                                if (f != 2147483647 && f > 0) cachedFc = f;
                            }

                            Matcher bandMatcher = Pattern.compile("mbands?\\s*=\\s*\\[([\\d,\\s]+)\\]", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            if (bandMatcher.find()) cachedBand = bandMatcher.group(1).trim();

                            Matcher mRsrp = Pattern.compile("(?:ssrsrp|rsrp)\\s*=\\s*(-?\\d+)", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            while (mRsrp.find()) {
                                int r = Integer.parseInt(mRsrp.group(1));
                                if (r != 2147483647 && r >= -140 && r <= -40) cachedRsrp = r;
                            }
                            
                            Matcher mRsrq = Pattern.compile("(?:ssrsrq|rsrq)\\s*=\\s*(-?\\d+)", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            while (mRsrq.find()) {
                                int r = Integer.parseInt(mRsrq.group(1));
                                if (r != 2147483647 && r >= -30 && r <= 0) cachedRsrq = r;
                            }
                            
                            // Unified RSSNR logic (captures both LTE rssnr and 5G sssinr under one umbrella)
                            Matcher mSinr = Pattern.compile("(?:sssinr|rssnr)\\s*=\\s*(-?\\d+)", Pattern.CASE_INSENSITIVE).matcher(lowerLine);
                            while (mSinr.find()) {
                                int s = Integer.parseInt(mSinr.group(1));
                                if (s != 2147483647) cachedRssnr = (cachedNetworkType.startsWith("LTE") && s > 50) ? (s / 10) : s;
                            }

                            if (lowerLine.contains("msignalstrength=") && (cachedRsrp == -1 || cachedRsrp == 0)) {
                                Matcher legacyMatcher = Pattern.compile("signalstrength:\\s*([\\d\\s\\-]+)").matcher(lowerLine);
                                if (legacyMatcher.find()) {
                                    String[] parts = legacyMatcher.group(1).strip().split("\\s+");
                                    if (parts.length >= 11) {
                                        try {
                                            int pRsrp = Integer.parseInt(parts[8]);
                                            int pRsrq = Integer.parseInt(parts[9]);
                                            int pSnr = Integer.parseInt(parts[10]);
                                            if (pRsrp >= -140 && pRsrp <= -40) cachedRsrp = pRsrp;
                                            if (pRsrq >= -30 && pRsrq <= 0) cachedRsrq = pRsrq;
                                            if (pSnr != 2147483647) cachedRssnr = (pSnr > 50) ? (pSnr / 10) : pSnr;
                                        } catch (Exception e) {}
                                    }
                                }
                            }
                        }
                        ranP.destroy();
                        if (("UNKNOWN".equals(cachedBand) || "".equals(cachedBand)) && cachedFc != -1) {
                            cachedBand = deriveBandFromFc(cachedFc);
                        }
                    }

                    currentSnapshot.put("RSRP", cachedRsrp == -1 ? 0 : cachedRsrp);
                    currentSnapshot.put("RSRQ", cachedRsrq == -1 ? 0 : cachedRsrq);
                    currentSnapshot.put("RSSNR", cachedRssnr == -1 ? 0 : cachedRssnr); // Outputting unified value
                    currentSnapshot.put("Network_Type", cachedNetworkType);
                    currentSnapshot.put("fc", cachedFc == -1 ? 0 : cachedFc);
                    currentSnapshot.put("Band", cachedBand);
                    
                    loopCounter++;
                    sessionMetrics.put(humanReadableKey, currentSnapshot);
                    
                    long targetInterval = 500; 
                    long elapsedLoop = (System.currentTimeMillis() + deviceTimeOffset) - exactTimestamp;
                    long sleepTime = targetInterval - elapsedLoop;
                    
                    if (sleepTime > 0) Thread.sleep(sleepTime);
                    else Thread.sleep(10); 
                    
                } catch (Exception e) {
                    System.out.println("Polling Error: " + e.getMessage());
                }
            }
            return sessionMetrics;
        });
    }

    public static double calculateVariance(List<Double> values) {
        if (values == null || values.isEmpty()) return 0.0;
        double sum = 0.0;
        for (double v : values) sum += v;
        double mean = sum / values.size();
        
        double sqDiffSum = 0.0;
        for (double v : values) sqDiffSum += (v - mean) * (v - mean);
        return sqDiffSum / values.size();
    }

    public static double calculateBitrateFluctuationIndex(List<Double> bitrates) {
        if (bitrates == null || bitrates.size() <= 1) return 0.0;
        double diffSum = 0.0;
        for (int i = 1; i < bitrates.size(); i++) {
            diffSum += Math.abs(bitrates.get(i) - bitrates.get(i-1));
        }
        return diffSum / (bitrates.size() - 1);
    }

    public static String evaluateStallClusteringList(List<Long> stallTimes) {
        if (stallTimes == null || stallTimes.isEmpty()) return "none";
        if (stallTimes.size() == 1) return "isolated";
        Collections.sort(stallTimes);
        long burstThresholdMs = 10000; 
        for (int i = 1; i < stallTimes.size(); i++) {
            if (stallTimes.get(i) - stallTimes.get(i-1) < burstThresholdMs) return "bursty";
        }
        return "isolated";
    }

    public static int calculateResolutionDropSeverity(List<Integer> resolutions) {
        if (resolutions == null || resolutions.isEmpty()) return 0;
        int max = resolutions.get(0);
        int maxDrop = 0;
        for (int i = 1; i < resolutions.size(); i++) {
            int current = resolutions.get(i);
            if (current < max) {
                int drop = max - current;
                if (drop > maxDrop) maxDrop = drop;
            } else if (current > max) {
                max = current; 
            }
        }
        return maxDrop;
    }
public static double calculateSmoothnessScore(int totalStalls, double frameDropDensity) {
        double score = 100.0;
        score -= (totalStalls * 15.0); 
        score -= (frameDropDensity * 10.0); 
        return Math.max(0.0, score);
    }

    public static String evaluateStallClustering(JSONObject stallData) {
        if (stallData == null || stallData.length() <= 1) return "isolated";
        List<Long> stallTimes = new ArrayList<>();
        DateTimeFormatter appFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneId.of("Asia/Kolkata"));
        for (String key : stallData.keySet()) {
            try {
                long ts = LocalDateTime.parse(key, appFormatter).atZone(ZoneId.of("Asia/Kolkata")).toInstant().toEpochMilli();
                stallTimes.add(ts);
            } catch(Exception e) {
                stallTimes.add(Long.parseLong(key));
            }
        }
        Collections.sort(stallTimes);
        long burstThresholdMs = 10000; 
        for (int i = 1; i < stallTimes.size(); i++) {
            if (stallTimes.get(i) - stallTimes.get(i-1) < burstThresholdMs) return "bursty";
        }
        return "isolated";
    }
}
