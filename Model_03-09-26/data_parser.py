"""
Data Parser for the Pause Recommender Neural Network.

Parses NetworkMetrics and AppMetrics JSON files, time-aligns them,
engineers features, and generates training labels via buffer simulation.

Usage:
    python data_parser.py
"""
import os
import json
import re
import numpy as np
import pandas as pd
from datetime import datetime

import config


# ============================================================
# Helper: Load concatenated JSON objects from a file
# ============================================================
def _load_concatenated_json(filepath: str) -> list:
    """
    Load a file that contains multiple JSON objects concatenated
    back-to-back (e.g., }{  with no comma between them).
    Returns a list of parsed JSON dicts.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Strategy: use a brace-depth counter to find top-level object boundaries
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(content):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                json_str = content[start:i + 1]
                try:
                    objects.append(json.loads(json_str))
                except json.JSONDecodeError as e:
                    print(f"  [Warning] Failed to parse JSON object at pos {start}: {e}")
                start = None
    
    return objects


# ============================================================
# Step 1: Parse Network Metrics
# ============================================================
def parse_network_metrics(filepath: str) -> pd.DataFrame:
    """
    Parse YoutubeLongForm_NetworkMetrics.json into a DataFrame.
    Handles files with multiple concatenated JSON objects (one per session).
    
    Each timestamped entry becomes a row with columns:
    - timestamp, downlink_mbps, uplink_mbps, rsrp, rsrq, rssnr,
      network_type, band, carrier, fc
    """
    print(f"[Parser] Loading network metrics from: {filepath}")
    json_objects = _load_concatenated_json(filepath)
    print(f"  Found {len(json_objects)} recording session(s)")

    rows = []
    for data in json_objects:
        for key, value in data.items():
            if key in config.NETWORK_SKIP_KEYS:
                continue
            if not isinstance(value, dict):
                continue
            try:
                ts = pd.to_datetime(key)
            except (ValueError, TypeError):
                continue

            rows.append({
                "timestamp": ts,
                "downlink_mbps": float(value.get("Downlink_Speed_Mbps", 0)),
                "uplink_mbps": float(value.get("Uplink_Speed_Mbps", 0)),
                "rsrp": float(value.get("RSRP", -120)),
                "rsrq": float(value.get("RSRQ", -20)),
                "rssnr": float(value.get("RSSNR", 0)),
                "network_type": value.get("Network_Type", "LTE"),
                "band": int(value.get("Band", 0)) if value.get("Band", "0").isdigit() else 0,
                "carrier": value.get("Carrier", "Unknown"),
                "fc": int(value.get("fc", 0)),
            })

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Encode network type as numeric
    df["network_type_encoded"] = df["network_type"].map(config.NETWORK_TYPE_MAP).fillna(0).astype(int)

    print(f"  Parsed {len(df)} network metric entries")
    print(f"  Time range: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")
    print(f"  Downlink speed: min={df['downlink_mbps'].min():.3f}, "
          f"max={df['downlink_mbps'].max():.3f}, "
          f"mean={df['downlink_mbps'].mean():.3f} Mbps")
    return df


# ============================================================
# Step 2: Parse App Metrics
# ============================================================
def _parse_fmt_string(fmt_str: str) -> dict:
    """
    Parse YouTube format string like '244 vp9 854x480@30' into components.
    Returns dict with resolution_height, resolution_width, fps, codec, format_id.
    """
    result = {
        "format_id": 0,
        "codec": "unknown",
        "resolution_width": 0,
        "resolution_height": 0,
        "fps": 0,
    }
    if not fmt_str or ":" in fmt_str:
        # Audio format like "251:CggKA2RyYxIBMQ opus" - skip
        return result

    parts = fmt_str.strip().split()
    if len(parts) >= 1:
        try:
            result["format_id"] = int(parts[0])
        except ValueError:
            pass
    if len(parts) >= 2:
        result["codec"] = parts[1]
    if len(parts) >= 3:
        # Parse "854x480@30"
        res_match = re.match(r"(\d+)x(\d+)@(\d+)", parts[2])
        if res_match:
            result["resolution_width"] = int(res_match.group(1))
            result["resolution_height"] = int(res_match.group(2))
            result["fps"] = int(res_match.group(3))
    return result


def _parse_dropped_frames(df_str: str) -> tuple:
    """Parse '0/535' into (dropped=0, total=535)."""
    if not df_str or "/" not in df_str:
        return 0, 0
    parts = df_str.split("/")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 0, 0


def parse_app_metrics(filepath: str) -> pd.DataFrame:
    """
    Parse YoutubeLongForm_AppMetrics.json into a DataFrame.

    Extracts from each timestamped entry:
    - buffer_health_s, jitter_ms, latency_ms, dropped_frames, total_frames,
      resolution_height, video_bitrate_kbps (actual ABR-selected bitrate from data)
    """
    print(f"\n[Parser] Loading app metrics from: {filepath}")
    json_objects = _load_concatenated_json(filepath)
    print(f"  Found {len(json_objects)} recording session(s)")

    rows = []
    for data in json_objects:
        for key, value in data.items():
            if key in config.APP_SKIP_KEYS:
                continue
            if not isinstance(value, dict):
                continue
            try:
                ts = pd.to_datetime(key)
            except (ValueError, TypeError):
                continue

            # Parse the nested stats JSON string
            stats_str = value.get("stats", "{}")
            try:
                stats = json.loads(stats_str)
            except (json.JSONDecodeError, TypeError):
                stats = {}

            # Extract buffer health
            extra = value.get("extraStats", {})
            readahead_str = extra.get("readahead", "0 s")
            try:
                buffer_health_s = float(readahead_str.replace(" s", "").strip())
            except ValueError:
                buffer_health_s = float(stats.get("bh", 0)) / 1000.0

            # Extract ping metrics
            ping = value.get("Youtube_Ping_Metrics", {})
            jitter_ms = float(ping.get("Jitter_ms", 0))
            try:
                latency_ms = float(ping.get("Latency_ms", "0"))
            except (ValueError, TypeError):
                latency_ms = 0.0

            # Extract dropped frames
            df_str = extra.get("droppedFrames", stats.get("df", "0/0"))
            dropped_frames, total_frames = _parse_dropped_frames(df_str)

            # Extract video format
            fmt_info = _parse_fmt_string(stats.get("fmt", ""))

            # ---- Change (i): Extract actual ABR-selected video bitrate ----
            # YouTube stats embed video bitrate in 'vbr' (kbps) or 'abr' fields.
            # We take whichever is present and non-zero; fall back to config default.
            vbr_raw = stats.get("vbr", stats.get("abr", 0))
            try:
                video_bitrate_kbps = float(vbr_raw)
            except (ValueError, TypeError):
                video_bitrate_kbps = 0.0
            # 0 means the field is absent; will be forward-filled after merging
            # and then filled with the config fallback in engineer_features()

            rows.append({
                "timestamp": ts,
                "buffer_health_s": buffer_health_s,
                "jitter_ms": jitter_ms,
                "latency_ms": latency_ms,
                "dropped_frames": dropped_frames,
                "total_frames": total_frames,
                "resolution_height": fmt_info["resolution_height"],
                "codec": fmt_info["codec"],
                "fps": fmt_info["fps"],
                "video_bitrate_kbps": video_bitrate_kbps,
            })

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Compute drop rate
    df["drop_rate"] = np.where(
        df["total_frames"] > 0,
        df["dropped_frames"] / df["total_frames"],
        0.0
    )

    # Replace zero bitrate entries with NaN so they forward-fill correctly
    df["video_bitrate_kbps"] = df["video_bitrate_kbps"].replace(0.0, np.nan)

    print(f"  Parsed {len(df)} app metric entries")
    print(f"  Buffer health: min={df['buffer_health_s'].min():.1f}s, "
          f"max={df['buffer_health_s'].max():.1f}s, "
          f"mean={df['buffer_health_s'].mean():.1f}s")
    bitrate_valid = df["video_bitrate_kbps"].dropna()
    if len(bitrate_valid) > 0:
        print(f"  Video bitrate from data: min={bitrate_valid.min():.1f}, "
              f"max={bitrate_valid.max():.1f}, "
              f"mean={bitrate_valid.mean():.1f} kbps")
    else:
        print(f"  Video bitrate: not found in stats; fallback={config.DEFAULT_VIDEO_BITRATE_KBPS} kbps")
    print(f"  Jitter: mean={df['jitter_ms'].mean():.2f}ms, "
          f"Latency: mean={df['latency_ms'].mean():.2f}ms")
    return df



# ============================================================
# Step 3: Time-Align and Merge
# ============================================================
def time_align_and_merge(net_df: pd.DataFrame, app_df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample both DataFrames to a 1-second grid and merge.
    
    - Network metrics (~2 samples/s): aggregate via mean per second
    - App metrics (~1 sample/6s): forward-fill to 1-second grid
    """
    print("\n[Parser] Time-aligning data to 1-second grid...")

    # Set timestamp as index for resampling
    net_df = net_df.set_index("timestamp")
    app_df = app_df.set_index("timestamp")

    # Determine the overlapping time range
    start_time = max(net_df.index.min(), app_df.index.min())
    end_time = min(net_df.index.max(), app_df.index.max())
    print(f"  Overlapping range: {start_time} -> {end_time}")

    # Resample network metrics (mean aggregation over RESAMPLE_INTERVAL)
    net_numeric_cols = [
        "downlink_mbps", "uplink_mbps", "rsrp", "rsrq", "rssnr",
        "network_type_encoded", "band", "fc"
    ]
    net_resampled = net_df[net_numeric_cols].resample(config.RESAMPLE_INTERVAL).mean()
    net_resampled["downlink_mbps"] = net_resampled["downlink_mbps"].fillna(0.0)
    net_resampled["uplink_mbps"] = net_resampled["uplink_mbps"].fillna(0.0)
    net_resampled["rsrp"] = net_resampled["rsrp"].ffill().bfill()
    net_resampled["rsrq"] = net_resampled["rsrq"].ffill().bfill()
    net_resampled["rssnr"] = net_resampled["rssnr"].ffill().bfill()
    net_resampled["network_type_encoded"] = net_resampled["network_type_encoded"].ffill().bfill()
    net_resampled["band"] = net_resampled["band"].ffill().bfill()
    net_resampled["fc"] = net_resampled["fc"].ffill().bfill()

    # Resample app metrics to RESAMPLE_INTERVAL (forward-fill since samples are sparse)
    app_numeric_cols = [
        "buffer_health_s", "jitter_ms", "latency_ms",
        "dropped_frames", "total_frames", "drop_rate",
        "resolution_height", "video_bitrate_kbps"
    ]
    app_resampled = app_df[app_numeric_cols].resample(config.RESAMPLE_INTERVAL).last()
    app_resampled["buffer_health_s"] = app_resampled["buffer_health_s"].ffill().bfill()
    app_resampled["jitter_ms"] = app_resampled["jitter_ms"].ffill().bfill().fillna(0.0)
    app_resampled["latency_ms"] = app_resampled["latency_ms"].ffill().bfill().fillna(0.0)
    app_resampled["dropped_frames"] = app_resampled["dropped_frames"].ffill().fillna(0.0)
    app_resampled["total_frames"] = app_resampled["total_frames"].ffill().fillna(0.0)
    app_resampled["drop_rate"] = app_resampled["drop_rate"].ffill().fillna(0.0)
    app_resampled["resolution_height"] = app_resampled["resolution_height"].ffill().fillna(480.0)
    app_resampled["video_bitrate_kbps"] = app_resampled["video_bitrate_kbps"].ffill().fillna(config.DEFAULT_VIDEO_BITRATE_KBPS)

    # Merge on the common grid
    merged = net_resampled.join(app_resampled, how="inner")
    merged = merged.loc[start_time:end_time]
    
    # Clean remaining NaNs
    merged = merged.ffill().bfill().fillna(0.0)

    # Add elapsed seconds from start
    merged["elapsed_s"] = (merged.index - merged.index[0]).total_seconds()

    # Round integer-like columns
    merged["band"] = merged["band"].round().astype(int)
    merged["network_type_encoded"] = merged["network_type_encoded"].round().astype(int)
    merged["fc"] = merged["fc"].round().astype(int)

    print(f"  Merged DataFrame: {len(merged)} rows × {len(merged.columns)} columns")
    return merged


# ============================================================
# Step 4: Feature Engineering
# ============================================================
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived features: rolling stats, trends, ratios.
    """
    print("\n[Parser] Engineering features...")
    df = df.copy()

    # --- Throughput rolling statistics ---
    df["downlink_ma_5s"] = (
        df["downlink_mbps"].rolling(window=config.MA_SHORT_WINDOW, min_periods=1).mean()
    )
    df["downlink_ma_30s"] = (
        df["downlink_mbps"].rolling(window=config.MA_LONG_WINDOW, min_periods=1).mean()
    )
    df["downlink_std_10s"] = (
        df["downlink_mbps"].rolling(window=config.STD_WINDOW, min_periods=1).std().fillna(0)
    )

    # --- Signal quality trend ---
    df["rsrp_delta_5s"] = df["rsrp"] - df["rsrp"].shift(config.DELTA_WINDOW, fill_value=df["rsrp"].iloc[0])

    # --- Buffer health trend (slope over TREND_WINDOW seconds) ---
    def rolling_slope(series, window):
        """Compute rolling linear regression slope."""
        slopes = []
        for i in range(len(series)):
            start = max(0, i - window + 1)
            segment = series.iloc[start:i + 1]
            if len(segment) < 2:
                slopes.append(0.0)
            else:
                x = np.arange(len(segment), dtype=float)
                y = segment.values.astype(float)
                # Simple slope via least squares: slope = cov(x,y) / var(x)
                x_mean = x.mean()
                y_mean = y.mean()
                var_x = ((x - x_mean) ** 2).sum()
                if var_x == 0:
                    slopes.append(0.0)
                else:
                    slopes.append(((x - x_mean) * (y - y_mean)).sum() / var_x)
        return pd.Series(slopes, index=series.index)

    df["buffer_trend_10s"] = rolling_slope(df["buffer_health_s"], config.TREND_WINDOW)

    # --- Throughput-to-bitrate ratio ---
    # Change (i): Use real per-timestep video bitrate from AppMetrics.
    # video_bitrate_kbps was extracted from the stats field and forward-filled.
    # Fall back to the config default where the field was absent.
    bitrate_mbps_series = df["video_bitrate_kbps"].fillna(
        config.DEFAULT_VIDEO_BITRATE_KBPS
    ) / 1000.0
    bitrate_mbps_series = bitrate_mbps_series.clip(lower=0.001)  # avoid div-by-zero
    df["throughput_to_bitrate_ratio"] = df["downlink_mbps"] / bitrate_mbps_series

    # Fill any remaining NaN with 0
    df = df.fillna(0)

    print(f"  Added features: downlink_ma_5s, downlink_ma_30s, downlink_std_10s, "
          f"rsrp_delta_5s, buffer_trend_10s, throughput_to_bitrate_ratio")
    print(f"  Final feature set: {len(config.FEATURE_COLUMNS)} features")
    return df


# ============================================================
# Step 4b: Divide Input Data into Segments and Document Ranges
# ============================================================
def create_and_save_segments(df: pd.DataFrame, num_segments: int = config.DEFAULT_NUM_SEGMENTS) -> list:
    """
    Divide the input data containing all features into N segments.
    Saves individual Segment_{i}.csv and Segment_{i}.json files in SEGMENTS_DIR,
    and documents the exact ranges of the 6 essential features in segments_ranges.txt.
    Preserves 100% of rows and all features without any data loss.
    """
    os.makedirs(config.SEGMENTS_DIR, exist_ok=True)
    total_samples = len(df)
    chunk_size = int(np.ceil(total_samples / num_segments))
    segments = []

    print(f"\n[Parser] Dividing input data into {num_segments} segments (directory: {config.SEGMENTS_DIR})...")

    for i in range(num_segments):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, total_samples)
        seg_df = df.iloc[start_idx:end_idx].copy()
        seg_name = f"Segment_{i+1}"

        # Save to CSV and JSON in Segments directory
        csv_path = os.path.join(config.SEGMENTS_DIR, f"{seg_name}.csv")
        json_path = os.path.join(config.SEGMENTS_DIR, f"{seg_name}.json")
        seg_df.to_csv(csv_path)
        seg_df.to_json(json_path, orient="index", indent=2)

        # Compute ranges for the 6 essential features
        key_ranges = {}
        for f in config.FORECAST_FEATURE_COLUMNS:
            key_ranges[f] = {
                "min": float(seg_df[f].min()),
                "max": float(seg_df[f].max()),
                "mean": float(seg_df[f].mean()),
                "std": float(seg_df[f].std())
            }

        # Compute ranges for all other features
        other_features = [c for c in seg_df.columns if c not in config.FORECAST_FEATURE_COLUMNS]
        other_ranges = {}
        for f in other_features:
            if pd.api.types.is_numeric_dtype(seg_df[f]):
                other_ranges[f] = {
                    "min": float(seg_df[f].min()),
                    "max": float(seg_df[f].max()),
                    "mean": float(seg_df[f].mean())
                }

        segments.append({
            "name": seg_name,
            "segment_number": i + 1,
            "sample_count": len(seg_df),
            "start_index": start_idx,
            "end_index": end_idx - 1,
            "start_time": str(seg_df.index[0]),
            "end_time": str(seg_df.index[-1]),
            "key_ranges": key_ranges,
            "other_ranges": other_ranges,
            "csv_file": f"{seg_name}.csv",
            "json_file": f"{seg_name}.json",
        })

    # Write documentation text file
    txt_path = config.SEGMENTS_TXT_PATH
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("INPUT DATA 5-SEGMENT PARTITION AND FEATURE RANGES SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Number of segments: {num_segments}\n")
        f.write(f"Total input samples: {total_samples} rows ({config.RESAMPLE_INTERVAL} grid)\n")
        f.write(f"Total features preserved: {len(df.columns)} columns (0 data lost)\n")
        f.write(f"Segments directory: {config.SEGMENTS_DIR}\n\n")

        f.write("-" * 80 + "\n")
        f.write("ESSENTIAL 6 FEATURES: RANGES BY SEGMENT\n")
        f.write("-" * 80 + "\n\n")

        for seg in segments:
            f.write(f"{seg['name']}:\n")
            f.write(f"  Samples: {seg['sample_count']} rows ({seg['start_time']} -> {seg['end_time']})\n")
            f.write(f"  Files: {seg['csv_file']}, {seg['json_file']}\n")
            f.write("  Feature Ranges:\n")
            for feat_name, stats in seg["key_ranges"].items():
                f.write(f'    "{feat_name}" : {stats["min"]:.3f} - {stats["max"]:.3f}  (mean: {stats["mean"]:.3f})\n')
            f.write("\n")

        f.write("=" * 80 + "\n")
        f.write("SIDE-BY-SIDE COMPARISON TABLE: 6 ESSENTIAL FEATURES ACROSS SEGMENTS\n")
        f.write("=" * 80 + "\n")
        header = f"{'Feature':<30} | " + " | ".join([f"{s['name']:<18}" for s in segments]) + "\n"
        f.write(header)
        f.write("-" * (32 + 21 * num_segments) + "\n")

        for feat in config.FORECAST_FEATURE_COLUMNS:
            line = f"{feat:<30} | "
            for seg in segments:
                r = seg["key_ranges"][feat]
                val_str = f"{r['min']:.1f} to {r['max']:.1f}"
                line += f"{val_str:<18} | "
            f.write(line[:-2] + "\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("ALL REMAINING FEATURES SUMMARY (PRESERVED IN ALL SEGMENT FILES)\n")
        f.write("=" * 80 + "\n")
        for feat in segments[0]["other_ranges"].keys():
            line = f"{feat:<28} | "
            for seg in segments:
                r = seg["other_ranges"].get(feat, {"min": 0, "max": 0})
                val_str = f"{r['min']:.1f} to {r['max']:.1f}"
                line += f"{val_str:<18} | "
            f.write(line[:-2] + "\n")

    print(f"  Saved {num_segments} segment files and ranges report: {txt_path}")
    return segments


# ============================================================
# Step 5: Labeling from Real Buffer Data
# ============================================================
def generate_labels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate training labels via forward buffer simulation on REAL measured buffer data.

    For each timestep t, simulate buffer evolution 30 seconds ahead using the
    actual recorded throughput and bitrate. If the buffer would drop to or below
    CRITICAL_BUFFER_S within the lookahead window, mark should_pause=1 and
    compute the recommended pause duration to reach SAFE_BUFFER_TARGET_S.
    """
    print("\n[Parser] Generating labels from REAL buffer data...")

    throughput      = df["downlink_mbps"].values          # Mbps
    real_buffer     = df["buffer_health_s"].values         # seconds (measured)

    # Per-timestep video bitrate: use recorded value or fallback constant
    if "video_bitrate_kbps" in df.columns:
        video_bitrate_arr = df["video_bitrate_kbps"].fillna(
            config.DEFAULT_VIDEO_BITRATE_KBPS).values / 1000.0   # → Mbps
    else:
        video_bitrate_arr = np.full(len(df), config.DEFAULT_VIDEO_BITRATE_MBPS)

    video_bitrate_arr = np.clip(video_bitrate_arr, 0.001, None)   # avoid div-by-zero

    lookahead_steps = config.LOOKAHEAD_STEPS
    critical        = config.CRITICAL_BUFFER_S
    safe_target     = config.SAFE_BUFFER_TARGET_S
    step_sec        = config.STEP_DURATION_S
    n_steps         = len(df)

    should_pause   = np.zeros(n_steps, dtype=np.float32)
    pause_duration = np.zeros(n_steps, dtype=np.float32)

    for t in range(n_steps):
        buffer      = float(real_buffer[t])
        would_stall = False

        end_t = min(t + lookahead_steps, n_steps)
        for future_t in range(t, end_t):
            tp      = throughput[future_t]
            vbr     = video_bitrate_arr[future_t]
            net_rate = ((tp / vbr) - 1.0) * step_sec
            buffer  += net_rate
            buffer   = max(buffer, 0.0)

            if buffer <= critical:
                would_stall = True
                break

        if would_stall:
            should_pause[t] = 1.0
            recent_start = max(0, t - 3)
            avg_tp  = np.mean(throughput[recent_start:t + 1])
            avg_vbr = np.mean(video_bitrate_arr[recent_start:t + 1])
            if avg_tp > 0:
                fill_rate = avg_tp / avg_vbr
                needed    = max(0.0, safe_target - real_buffer[t])
                dur       = needed / max(fill_rate, 0.01)
            else:
                dur = 10.0
            pause_duration[t] = float(np.clip(dur, 1.0, config.MAX_PAUSE_DURATION_S))

    df = df.copy()
    df["should_pause"]     = should_pause
    df["pause_duration_s"] = pause_duration

    n_pos  = int(should_pause.sum())
    total  = n_steps
    print(f"  Labels done: {n_pos}/{total} positive ({100*n_pos/total:.1f}%) — real buffer only")
    return df


# ============================================================
# Step 6: Create Sequences for Predictive LSTM
# ============================================================
def create_sequences(df: pd.DataFrame, window_size: int = config.SEQUENCE_LENGTH,
                     horizon_size: int = config.FUTURE_HORIZON_STEPS):
    """
    Create sliding window sequences for the Predictive LSTM on 5s grid.

    For each timestep i:
      - X_seq: Past historical features [i - window_size : i] of shape (W=6, 16)
      - Y_future: Future ground-truth features [i : i + horizon_size] of shape (H=4, 6)
      - y_cls: Should pause label at time i - 1
      - y_reg: Pause duration at time i - 1

    Returns:
        X: np.array of shape (N, window_size, num_features)
        Y_future: np.array of shape (N, horizon_size, num_forecast_features)
        y_cls: np.array of shape (N,) - binary should_pause labels
        y_reg: np.array of shape (N,) - pause_duration_s labels
    """
    print(f"\n[Parser] Creating predictive sequences (past_window={window_size} steps, future_horizon={horizon_size} steps)...")

    features         = df[config.FEATURE_COLUMNS].values.astype(np.float32)
    forecast_features = df[config.FORECAST_FEATURE_COLUMNS].values.astype(np.float32)
    labels_cls       = df["should_pause"].values.astype(np.float32)
    labels_reg       = df["pause_duration_s"].values.astype(np.float32)

    n = len(features)
    if n < window_size + horizon_size:
        raise ValueError(f"Not enough data ({n} rows) for window={window_size} + horizon={horizon_size}")

    all_X, all_Y_future, all_y_cls, all_y_reg = [], [], [], []

    for i in range(window_size, n - horizon_size + 1):
        all_X.append(features[i - window_size:i])
        all_Y_future.append(forecast_features[i:i + horizon_size])
        all_y_cls.append(labels_cls[i - 1])
        all_y_reg.append(labels_reg[i - 1])

    X        = np.array(all_X,        dtype=np.float32)
    Y_future = np.array(all_Y_future, dtype=np.float32)
    y_cls    = np.array(all_y_cls,    dtype=np.float32)
    y_reg    = np.array(all_y_reg,    dtype=np.float32)

    print(f"  Sequences created: X={X.shape}, Y_future={Y_future.shape}, y_cls={y_cls.shape}, y_reg={y_reg.shape}")
    print(f"  Positive labels: {int(y_cls.sum())}/{len(y_cls)} "
          f"({100*y_cls.sum()/len(y_cls):.1f}%)")

    return X, Y_future, y_cls, y_reg



# ============================================================
# Step 7: Data Augmentation
# ============================================================
def augment_data(X: np.ndarray, Y_future: np.ndarray, y_cls: np.ndarray, y_reg: np.ndarray,
                 noise_std: float = config.AUGMENT_NOISE_STD,
                 num_copies: int = config.NUM_AUGMENTED_COPIES) -> tuple:
    """
    Augment training data by adding Gaussian noise to past features.
    Only augments positive samples (should_pause=1) to help with class imbalance.
    """
    print(f"\n[Parser] Augmenting data ({num_copies} copies of positive samples)...")
    
    positive_mask = y_cls == 1.0
    X_pos = X[positive_mask]
    Y_pos = Y_future[positive_mask]
    y_cls_pos = y_cls[positive_mask]
    y_reg_pos = y_reg[positive_mask]
    
    if len(X_pos) == 0:
        print("  No positive samples to augment!")
        return X, Y_future, y_cls, y_reg
    
    # Compute feature-wise std for scaling noise
    feature_stds = X.std(axis=(0, 1))  # std per feature
    feature_stds = np.maximum(feature_stds, 1e-6)  # avoid zero
    
    aug_X_list = [X]
    aug_Y_list = [Y_future]
    aug_cls_list = [y_cls]
    aug_reg_list = [y_reg]
    
    for copy_i in range(num_copies):
        noise = np.random.randn(*X_pos.shape).astype(np.float32) * noise_std * feature_stds
        X_noisy = X_pos + noise
        X_noisy = np.maximum(X_noisy, 0)
        
        aug_X_list.append(X_noisy)
        aug_Y_list.append(Y_pos)
        aug_cls_list.append(y_cls_pos)
        aug_reg_list.append(y_reg_pos)
    
    X_aug = np.concatenate(aug_X_list, axis=0)
    Y_future_aug = np.concatenate(aug_Y_list, axis=0)
    y_cls_aug = np.concatenate(aug_cls_list, axis=0)
    y_reg_aug = np.concatenate(aug_reg_list, axis=0)
    
    print(f"  Before augmentation: {len(X)} samples ({int(y_cls.sum())} positive)")
    print(f"  After augmentation:  {len(X_aug)} samples ({int(y_cls_aug.sum())} positive)")
    
    return X_aug, Y_future_aug, y_cls_aug, y_reg_aug


# ============================================================
# Step 8: Train/Val Split
# ============================================================
def train_val_split(X: np.ndarray, Y_future: np.ndarray, y_cls: np.ndarray, y_reg: np.ndarray,
                    split_ratio: float = config.TRAIN_VAL_SPLIT) -> dict:
    """
    Split data into train and validation sets.
    Uses stratified random split to maintain class balance.
    """
    print(f"\n[Parser] Splitting data ({split_ratio:.0%} train / {1-split_ratio:.0%} val)...")
    
    np.random.seed(config.RANDOM_SEED)
    n = len(X)
    
    # Stratified split: maintain positive ratio in both sets
    pos_indices = np.where(y_cls == 1.0)[0]
    neg_indices = np.where(y_cls == 0.0)[0]
    
    np.random.shuffle(pos_indices)
    np.random.shuffle(neg_indices)
    
    n_pos_train = int(len(pos_indices) * split_ratio)
    n_neg_train = int(len(neg_indices) * split_ratio)
    
    train_indices = np.concatenate([
        pos_indices[:n_pos_train],
        neg_indices[:n_neg_train]
    ])
    val_indices = np.concatenate([
        pos_indices[n_pos_train:],
        neg_indices[n_neg_train:]
    ])
    
    np.random.shuffle(train_indices)
    np.random.shuffle(val_indices)
    
    result = {
        "X_train": X[train_indices],
        "Y_future_train": Y_future[train_indices],
        "y_cls_train": y_cls[train_indices],
        "y_reg_train": y_reg[train_indices],
        "X_val": X[val_indices],
        "Y_future_val": Y_future[val_indices],
        "y_cls_val": y_cls[val_indices],
        "y_reg_val": y_reg[val_indices],
    }
    
    print(f"  Train: {len(train_indices)} samples "
          f"({int(y_cls[train_indices].sum())} positive, "
          f"{100*y_cls[train_indices].mean():.1f}%)")
    print(f"  Val:   {len(val_indices)} samples "
          f"({int(y_cls[val_indices].sum())} positive, "
          f"{100*y_cls[val_indices].mean():.1f}%)")
    
    return result


# ============================================================
# Main Pipeline
# ============================================================
def main():
    print("=" * 60)
    print("PAUSE RECOMMENDER - DATA PARSING PIPELINE")
    print("=" * 60)
    
    # Create output directories
    os.makedirs(config.PROCESSED_DATA_DIR, exist_ok=True)
    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    # Step 1: Parse network metrics
    net_df = parse_network_metrics(config.NETWORK_METRICS_PATH)

    # Step 2: Parse app metrics
    app_df = parse_app_metrics(config.APP_METRICS_PATH)

    # Step 3: Time-align and merge
    aligned_df = time_align_and_merge(net_df, app_df)

    # Step 4: Engineer features
    featured_df = engineer_features(aligned_df)

    # Save the aligned data (for evaluation visualization later)
    aligned_csv_path = os.path.join(config.PROCESSED_DATA_DIR, "aligned_data.csv")
    featured_df.to_csv(aligned_csv_path, index=True)
    print(f"\n[Parser] Saved aligned data to: {aligned_csv_path}")

    # Step 4b: Divide into segments and document 6 essential feature ranges
    create_and_save_segments(featured_df)

    # Step 5: Generate labels via buffer simulation (real buffer data only)
    labeled_df = generate_labels(featured_df)

    # Step 6: Create Predictive LSTM sequences (past 30s -> future horizon)
    X, Y_future, y_cls, y_reg = create_sequences(labeled_df)

    # Step 7: Augment positive samples
    X_aug, Y_future_aug, y_cls_aug, y_reg_aug = augment_data(X, Y_future, y_cls, y_reg)

    # Step 8: Train/val split
    splits = train_val_split(X_aug, Y_future_aug, y_cls_aug, y_reg_aug)

    # Save processed data
    print(f"\n[Parser] Saving processed data to: {config.PROCESSED_DATA_DIR}")
    for name, arr in splits.items():
        path = os.path.join(config.PROCESSED_DATA_DIR, f"{name}.npy")
        np.save(path, arr)
        print(f"  {name}: shape={arr.shape}, saved to {path}")
    
    # Also save feature normalization stats (for inference later)
    # Use training data stats only to avoid data leakage
    feature_stats = {
        "mean": splits["X_train"].mean(axis=(0, 1)).tolist(),
        "std": splits["X_train"].std(axis=(0, 1)).tolist(),
        "feature_names": config.FEATURE_COLUMNS,
        "forecast_feature_names": config.FORECAST_FEATURE_COLUMNS,
    }
    stats_path = os.path.join(config.PROCESSED_DATA_DIR, "feature_stats.json")
    with open(stats_path, "w") as f:
        json.dump(feature_stats, f, indent=2)
    print(f"  Feature stats saved to: {stats_path}")

    print("\n" + "=" * 60)
    print("DATA PARSING COMPLETE!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  Network metric entries:   {len(net_df)}")
    print(f"  App metric entries:       {len(app_df)}")
    print(f"  Aligned time steps (5s):  {len(featured_df)}")
    print(f"  Total training sequences: {len(splits['X_train'])}")
    print(f"  Total validation sequences: {len(splits['X_val'])}")
    print(f"  Historical features/step: {config.NUM_FEATURES}")
    print(f"  Past sequence length:     {config.SEQUENCE_LENGTH} steps ({config.SEQUENCE_LENGTH * config.STEP_DURATION_S}s)")
    print(f"  Future horizon forecast:  {config.FUTURE_HORIZON_STEPS} steps ({config.FUTURE_HORIZON_S}s, {config.NUM_FORECAST_FEATURES} target features)")
    

if __name__ == "__main__":
    main()
