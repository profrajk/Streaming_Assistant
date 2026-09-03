"""
Configuration file for the Pause Recommender Neural Network.
All hyperparameters, thresholds, and paths are defined here.
"""
import os

# ============================================================
# Paths
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "Input Data", "Input_data_01-09-26")
NETWORK_METRICS_PATH = os.path.join(INPUT_DIR, "YoutubeLongForm_NetworkMetrics.json")
APP_METRICS_PATH = os.path.join(INPUT_DIR, "YoutubeLongForm_AppMetrics.json")
PROCESSED_DATA_DIR = os.path.join(BASE_DIR, "processed_data")
CHECKPOINT_DIR = os.path.join(BASE_DIR, "checkpoints")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

SEGMENTS_DIR = os.path.join(BASE_DIR, "Input Data", "Segments")
SEGMENTS_TXT_PATH = os.path.join(SEGMENTS_DIR, "segments_ranges.txt")

DEFAULT_NUM_SEGMENTS = 5

# ============================================================
# Data Parsing
# ============================================================
# Keys in the JSON that are NOT timestamped data entries
NETWORK_SKIP_KEYS = {"metadata"}
APP_SKIP_KEYS = {
    "metadata", "QoE_Metrics", "Stability_Features",
    "Temporal_Features", "Perception_Oriented_Features"
}

# Resample interval for time alignment (1-second grid)
RESAMPLE_INTERVAL = "5s"
STEP_DURATION_S = 5       # 1 sample per second

# Network type encoding
NETWORK_TYPE_MAP = {
    "NR_SA": 2,     # 5G Standalone
    "NR_NSA": 1,    # 5G Non-Standalone
    "LTE": 0,       # 4G LTE
}

# Default video bitrate (kbps) — FALLBACK only if AppMetrics bitrate unavailable.
# With dynamic data, the per-timestep bitrate is read dynamically from AppMetrics.
DEFAULT_VIDEO_BITRATE_KBPS = 1229.76
DEFAULT_VIDEO_BITRATE_MBPS = DEFAULT_VIDEO_BITRATE_KBPS / 1000.0

# ============================================================
# Feature Engineering (on 1-second grid)
# ============================================================
# Rolling window sizes (in seconds)
MA_SHORT_WINDOW = 5       # 5-second moving average
MA_LONG_WINDOW = 30       # 30-second moving average
STD_WINDOW = 10           # 10-second rolling std dev
TREND_WINDOW = 10         # 10-second trend (slope)
DELTA_WINDOW = 5          # 5-second delta for signal changes

# Feature columns the model will use (in order)
FEATURE_COLUMNS = [
    # Throughput features (5)
    "downlink_mbps",
    "uplink_mbps",
    "downlink_ma_5s",
    "downlink_ma_30s",
    "downlink_std_10s",
    # Radio signal features (4)
    "rsrp",
    "rsrq",
    "rssnr",
    "rsrp_delta_5s",
    # Network context (2)
    "network_type_encoded",
    "band",
    # Buffer state (2)
    "buffer_health_s",
    "buffer_trend_10s",
    # App quality (3)
    "throughput_to_bitrate_ratio",
    "jitter_ms",
    "latency_ms",
]
NUM_FEATURES = len(FEATURE_COLUMNS)

# ============================================================
# Labeling (Real Buffer from Ground Truth — on 5s grid)
# ============================================================
# Buffer thresholds
CRITICAL_BUFFER_S = 20.0       # Buffer below this = stall imminent → should_pause=1
SAFE_BUFFER_TARGET_S = 80.0   # Conservative target buffer when pausing
LOOKAHEAD_S = 30              # Look-ahead window in seconds
LOOKAHEAD_STEPS = LOOKAHEAD_S // STEP_DURATION_S

# ============================================================
# Model Architecture
# ============================================================
SEQUENCE_LENGTH = 30      # Sliding window of 30 seconds
LSTM_HIDDEN_1 = 128       # First LSTM layer hidden size
LSTM_HIDDEN_2 = 64        # Second LSTM layer hidden size
DENSE_HIDDEN = 32         # Dense layer before output heads
DROPOUT_1 = 0.3           # Dropout after first LSTM
DROPOUT_2 = 0.2           # Dropout after second LSTM

# ============================================================
# Training
# ============================================================
TRAIN_VAL_SPLIT = 0.8     # 80% train, 20% validation (time-contiguous)
BATCH_SIZE = 64
LEARNING_RATE = 0.001
MAX_EPOCHS = 200
EARLY_STOP_PATIENCE = 15  # Stop if val loss doesn't improve for 15 epochs
LR_REDUCE_PATIENCE = 7    # Reduce LR if val loss plateaus for 7 epochs
LR_REDUCE_FACTOR = 0.5    # Multiply LR by this factor

# Multi-task loss weights
FORECAST_LOSS_WEIGHT = 1.0         # γ for MSE loss on future feature forecasting
CLASSIFICATION_LOSS_WEIGHT = 1.0   # α for BCE loss (pause classification)
REGRESSION_LOSS_WEIGHT = 0.5       # β for MSE loss (duration prediction)

# ============================================================
# Future Feature Forecasting (Two-Stage Predictive Architecture)
# ============================================================
FUTURE_HORIZON_S = 15     # Predict future dynamics for next 15 seconds (H = 15)
FUTURE_HORIZON_STEPS = FUTURE_HORIZON_S // STEP_DURATION_S  # H = 15 steps

# Key future target features the model forecasts second-by-second
FORECAST_FEATURE_COLUMNS = [
    "downlink_mbps",                # Future throughput trajectory
    "rsrp",                         # Future radio signal strength
    "rsrq",                         # Future signal quality
    "rssnr",                        # Future signal-to-noise ratio
    "buffer_health_s",              # Future buffer depletion/growth
    "throughput_to_bitrate_ratio",  # Future ratio vs video consumption
]
NUM_FORECAST_FEATURES = len(FORECAST_FEATURE_COLUMNS)

# ============================================================
# Data Augmentation
# ============================================================
AUGMENT_NOISE_STD = 0.05   # Gaussian noise std (fraction of feature std)
NUM_AUGMENTED_COPIES = 2   # Number of noisy copies per real sample

# ============================================================
# Conservative Pause Policy  (Change iv)
# ============================================================
# Higher threshold requires more confidence before triggering a pause.
PAUSE_DECISION_THRESHOLD = 0.65   # Was 0.50; now requires 65% confidence

# Hard cap: even if the model recommends longer, clip to this duration.
MAX_PAUSE_DURATION_S = 20.0       # Prevents overly-long single pauses

# Cooldown: minimum seconds between two consecutive pause recommendations.
PAUSE_COOLDOWN_S = 15             # No back-to-back pauses within 15s

# Only recommend a pause when the buffer has actually dropped to this level.
MIN_BUFFER_TO_PAUSE_S = 20.0      # Don't pause when buffer is comfortable (matches CRITICAL_BUFFER_S)

# ============================================================
# Evaluation
# ============================================================
RANDOM_SEED = 42
