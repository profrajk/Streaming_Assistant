"""
Segment Input Data into 5 Segments and Document 6 Essential Feature Ranges.

Preserves all 23 features and all rows across the 5 segments.
Outputs CSV/JSON files and a detailed text file in 'Input Data/Segments/'.
"""
import os
import json
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DATA_DIR = os.path.join(BASE_DIR, "Input Data")
SEGMENTS_DIR = os.path.join(INPUT_DATA_DIR, "Segments")
ALIGNED_DATA_PATH = os.path.join(BASE_DIR, "processed_data", "aligned_data.csv")

KEY_FEATURES = [
    "downlink_mbps",                # Future throughput trajectory
    "rsrp",                         # Future radio signal strength
    "rsrq",                         # Future signal quality
    "rssnr",                        # Future signal-to-noise ratio
    "buffer_health_s",              # Future buffer depletion/growth
    "throughput_to_bitrate_ratio",  # Future ratio vs video consumption
]


def main():
    os.makedirs(SEGMENTS_DIR, exist_ok=True)
    print(f"[Segmenter] Target directory: {SEGMENTS_DIR}")

    if not os.path.exists(ALIGNED_DATA_PATH):
        raise FileNotFoundError(f"Input aligned data not found at {ALIGNED_DATA_PATH}")

    df = pd.read_csv(ALIGNED_DATA_PATH, index_col=0)
    total_samples = len(df)
    total_cols = len(df.columns)
    print(f"[Segmenter] Loaded input data: {total_samples} rows x {total_cols} columns")

    # Divide into 5 equal-sized sequential segments without dropping any data
    chunk_size = int(np.ceil(total_samples / 5))
    segments = []

    for i in range(5):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, total_samples)
        seg_df = df.iloc[start_idx:end_idx].copy()
        seg_name = f"Segment_{i+1}"

        # Save to CSV and JSON in Segments directory
        csv_path = os.path.join(SEGMENTS_DIR, f"{seg_name}.csv")
        json_path = os.path.join(SEGMENTS_DIR, f"{seg_name}.json")
        seg_df.to_csv(csv_path)
        seg_df.to_json(json_path, orient="index", indent=2)

        # Compute ranges for the 6 key features
        key_ranges = {}
        for f in KEY_FEATURES:
            key_ranges[f] = {
                "min": float(seg_df[f].min()),
                "max": float(seg_df[f].max()),
                "mean": float(seg_df[f].mean()),
                "std": float(seg_df[f].std())
            }

        # Compute ranges for all other features
        other_features = [c for c in seg_df.columns if c not in KEY_FEATURES]
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

    # Write detailed text file
    txt_path = os.path.join(SEGMENTS_DIR, "segments_ranges.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("INPUT DATA 5-SEGMENT PARTITION AND FEATURE RANGES SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total input samples: {total_samples} rows (5-second grid)\n")
        f.write(f"Total features preserved: {total_cols} columns (0 data lost)\n")
        f.write(f"Number of segments: 5\n")
        f.write(f"Segments directory: {SEGMENTS_DIR}\n\n")

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
        header = f"{'Feature':<30} | {'Segment 1':<18} | {'Segment 2':<18} | {'Segment 3':<18} | {'Segment 4':<18} | {'Segment 5':<18}\n"
        f.write(header)
        f.write("-" * 130 + "\n")

        for feat in KEY_FEATURES:
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

    print(f"\n[Segmenter] Saved 5 segment CSVs and JSONs to: {SEGMENTS_DIR}")
    print(f"[Segmenter] Saved ranges summary report to: {txt_path}")

    # Print summary to console
    print("\n" + "=" * 80)
    print("5 SEGMENTS CREATED SUCCESSFULLY")
    print("=" * 80)
    for seg in segments:
        print(f"\n{seg['name']} ({seg['sample_count']} rows, {seg['start_time']} -> {seg['end_time']}):")
        for feat_name, stats in seg["key_ranges"].items():
            print(f'    "{feat_name}": {stats["min"]:.3f} - {stats["max"]:.3f}')


if __name__ == "__main__":
    main()
