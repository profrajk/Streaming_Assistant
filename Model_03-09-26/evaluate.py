"""
Evaluation Script for the Predictive Pause Recommender.

Evaluates:
  1. Stage 1: Future Feature Forecasting Accuracy (Throughput, RSRP, Buffer MAE & RMSE)
  2. Stage 2: Pause Classification & Duration Regression Performance
  3. Visualizations: Training Curves, Feature Forecasts, Timeline & Confusion Matrix
"""
import os
import json
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, mean_absolute_error, mean_squared_error,
    confusion_matrix
)

import config
from model import PredictivePauseRecommenderLSTM


def plot_training_curves(history_path, save_path):
    with open(history_path, 'r') as f:
        history = json.load(f)
        
    epochs = range(1, len(history['train_loss']) + 1)
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # 1. Total Loss
    axes[0].plot(epochs, history['train_loss'], label='Train Total', color='blue')
    axes[0].plot(epochs, history['val_loss'], label='Val Total', color='orange')
    axes[0].set_title('Total Multi-Task Loss')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # 2. Forecasting Loss
    if 'train_fcast_loss' in history:
        axes[1].plot(epochs, history['train_fcast_loss'], label='Train Forecast MSE', color='purple')
        axes[1].plot(epochs, history['val_fcast_loss'], label='Val Forecast MSE', color='magenta')
        axes[1].set_title('Feature Forecasting Loss (Stage 1)')
        axes[1].set_xlabel('Epoch')
        axes[1].set_ylabel('MSE Loss')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        
    # 3. Classification Loss
    axes[2].plot(epochs, history['train_cls_loss'], label='Train Pause BCE', color='green')
    axes[2].plot(epochs, history['val_cls_loss'], label='Val Pause BCE', color='red')
    axes[2].set_title('Pause Decision Loss (Stage 2)')
    axes[2].set_xlabel('Epoch')
    axes[2].set_ylabel('BCE Loss')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()


def plot_feature_forecast(Y_true, Y_pred, save_path):
    """
    Plot predicted vs ground truth future feature trajectories for sample sequences.
    """
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    fig.suptitle(f'Stage 1: Predicted Future Features vs Actual Ground Truth (Next {config.FUTURE_HORIZON_S} Seconds)', fontsize=13, fontweight='bold')
    
    # Average trajectory over validation set
    t_horizon = np.arange(1, config.FUTURE_HORIZON_STEPS + 1) * config.STEP_DURATION_S
    
    # 1. Throughput (Index 0)
    tp_true = Y_true[:, :, 0].mean(axis=0)
    tp_pred = Y_pred[:, :, 0].mean(axis=0)
    axes[0].plot(t_horizon, tp_true, 'o-', label='Actual Future Downlink (Mbps)', color='blue', linewidth=2)
    axes[0].plot(t_horizon, tp_pred, 's--', label='Predicted Future Downlink (Mbps)', color='orange', linewidth=2)
    axes[0].set_ylabel('Throughput (Mbps)')
    axes[0].set_title('Downlink Throughput Forecast')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # 2. RSRP (Index 1)
    rsrp_true = Y_true[:, :, 1].mean(axis=0)
    rsrp_pred = Y_pred[:, :, 1].mean(axis=0)
    axes[1].plot(t_horizon, rsrp_true, 'o-', label='Actual Future RSRP (dBm)', color='green', linewidth=2)
    axes[1].plot(t_horizon, rsrp_pred, 's--', label='Predicted Future RSRP (dBm)', color='red', linewidth=2)
    axes[1].set_ylabel('RSRP (dBm)')
    axes[1].set_title('Radio Signal Strength (RSRP) Forecast')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # 3. Buffer Health (Index 4)
    buf_true = Y_true[:, :, 4].mean(axis=0)
    buf_pred = Y_pred[:, :, 4].mean(axis=0)
    axes[2].plot(t_horizon, buf_true, 'o-', label='Actual Future Buffer (s)', color='purple', linewidth=2)
    axes[2].plot(t_horizon, buf_pred, 's--', label='Predicted Future Buffer (s)', color='magenta', linewidth=2)
    axes[2].set_ylabel('Buffer (s)')
    axes[2].set_xlabel('Future Horizon (Seconds Ahead)')
    axes[2].set_title('Buffer Health Trajectory Forecast')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()


def plot_timeline(df, preds_prob, save_path):
    plt.figure(figsize=(12, 10))
    
    # Subplot 1: Buffer Health
    plt.subplot(3, 1, 1)
    if 'buffer_health_s' in df.columns:
        plt.plot(df['buffer_health_s'].values, label='Buffer Health (s)')
    plt.axhline(y=config.CRITICAL_BUFFER_S, color='r', linestyle='--', label='Critical Threshold')
    plt.ylabel('Buffer (s)')
    plt.title('Buffer Health over Time')
    plt.legend()
    
    # Subplot 2: Downlink Mbps
    plt.subplot(3, 1, 2)
    if 'downlink_mbps' in df.columns:
        plt.plot(df['downlink_mbps'].values, label='Downlink Mbps')
    plt.ylabel('Throughput (Mbps)')
    plt.title('Downlink Throughput over Time')
    plt.legend()
    
    # Subplot 3: Pause Probability & Ground Truth
    plt.subplot(3, 1, 3)
    plot_len = len(preds_prob)
    x_axis = range(len(df) - plot_len, len(df))
    
    plt.plot(x_axis, preds_prob, label='Predicted Pause Prob', color='blue')
    plt.axhline(y=config.PAUSE_DECISION_THRESHOLD, color='g', linestyle='--', label='Threshold')
    
    if 'should_pause' in df.columns:
        gt = df['should_pause'].values[-plot_len:]
        gt_idx = np.where(gt == 1)[0]
        plt.scatter(np.array(x_axis)[gt_idx], preds_prob[gt_idx], color='red', label='Ground Truth Pause', zorder=5)
    
    plt.ylabel('Probability')
    plt.xlabel('Time Step')
    plt.title('Pause Probability vs Threshold')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()


def plot_confusion_matrix(y_true, y_pred_cls, save_path):
    cm = confusion_matrix(y_true, y_pred_cls)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=['No Pause', 'Pause'], yticklabels=['No Pause', 'Pause'])
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.title('Stage 2: Pause Decision Confusion Matrix')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # Load validation data
    print("Loading validation data...")
    X_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "X_val.npy"))
    Y_fut_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "Y_future_val.npy"))
    y_cls_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_cls_val.npy"))
    y_reg_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_reg_val.npy"))
    
    df_aligned = pd.read_csv(os.path.join(config.PROCESSED_DATA_DIR, "aligned_data.csv"))

    print("Loading best predictive model...")
    model = PredictivePauseRecommenderLSTM(
        num_features=config.NUM_FEATURES,
        seq_length=config.SEQUENCE_LENGTH,
        future_horizon=config.FUTURE_HORIZON_STEPS,
        num_forecast_features=config.NUM_FORECAST_FEATURES,
        lstm_hidden_1=config.LSTM_HIDDEN_1,
        lstm_hidden_2=config.LSTM_HIDDEN_2,
        dense_hidden=config.DENSE_HIDDEN,
        dropout_1=config.DROPOUT_1,
        dropout_2=config.DROPOUT_2
    ).to(device)
    
    model.load_state_dict(torch.load(os.path.join(config.CHECKPOINT_DIR, "best_model.pt"), map_location=device, weights_only=True))
    model.eval()

    # Predict
    print("Computing predictions...")
    all_fut_pred = []
    all_prob = []
    all_dur = []
    
    batch_size = 256
    with torch.no_grad():
        for i in range(0, len(X_val), batch_size):
            X_batch = torch.tensor(X_val[i:i+batch_size], dtype=torch.float32).to(device)
            fut_p, prob, dur = model(X_batch)
            all_fut_pred.append(fut_p.cpu().numpy())
            all_prob.extend(prob.cpu().numpy().flatten())
            all_dur.extend(dur.cpu().numpy().flatten())
            
    all_fut_pred = np.concatenate(all_fut_pred, axis=0)
    all_prob = np.array(all_prob)
    all_dur = np.array(all_dur)
    
    y_pred_cls = (all_prob > config.PAUSE_DECISION_THRESHOLD).astype(int)
    
    # ----------------------------------------------------
    # Stage 1: Future Feature Forecasting Metrics
    # ----------------------------------------------------
    print("\n" + "=" * 60)
    print(f"STAGE 1: FUTURE FEATURE FORECASTING EVALUATION (H = {config.FUTURE_HORIZON_S}s)")
    print("=" * 60)
    for feat_idx, feat_name in enumerate(config.FORECAST_FEATURE_COLUMNS):
        y_t = Y_fut_val[:, :, feat_idx].flatten()
        y_p = all_fut_pred[:, :, feat_idx].flatten()
        mae = mean_absolute_error(y_t, y_p)
        rmse = np.sqrt(mean_squared_error(y_t, y_p))
        print(f"  {feat_name:<30} | MAE: {mae:>8.4f} | RMSE: {rmse:>8.4f}")

    # ----------------------------------------------------
    # Stage 2: Classification & Regression Metrics
    # ----------------------------------------------------
    print("\n" + "=" * 60)
    print("STAGE 2: PAUSE DECISION EVALUATION")
    print("=" * 60)
    acc = accuracy_score(y_cls_val, y_pred_cls)
    prec = precision_score(y_cls_val, y_pred_cls, zero_division=0)
    rec = recall_score(y_cls_val, y_pred_cls, zero_division=0)
    f1 = f1_score(y_cls_val, y_pred_cls, zero_division=0)
    
    print("Classification (should_pause):")
    print(f"Accuracy : {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall   : {rec:.4f}")
    print(f"F1-Score : {f1:.4f}")
    
    mask = (y_cls_val == 1)
    if np.sum(mask) > 0:
        mae = mean_absolute_error(y_reg_val[mask], all_dur[mask])
        rmse = np.sqrt(mean_squared_error(y_reg_val[mask], all_dur[mask]))
        print("\nRegression (pause_duration_s) where should_pause=1:")
        print(f"MAE  : {mae:.4f}")
        print(f"RMSE : {rmse:.4f}")
    else:
        print("\nNo positive labels in validation set for regression evaluation.")
        
    print("\nGenerating visualizations...")
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    
    hist_path = os.path.join(config.RESULTS_DIR, "training_history.json")
    if os.path.exists(hist_path):
        plot_training_curves(hist_path, os.path.join(config.RESULTS_DIR, "training_curves.png"))
        
    plot_feature_forecast(Y_fut_val, all_fut_pred, os.path.join(config.RESULTS_DIR, "feature_forecast_comparison.png"))
    plot_timeline(df_aligned, all_prob, os.path.join(config.RESULTS_DIR, "timeline_predictions.png"))
    plot_confusion_matrix(y_cls_val, y_pred_cls, os.path.join(config.RESULTS_DIR, "confusion_matrix.png"))
    
    print(f"Saved visualizations to {config.RESULTS_DIR}")

    print("\nOpening visualization graphs for display...")
    try:
        if os.name == 'nt':
            p_list = [
                os.path.join(config.RESULTS_DIR, "training_curves.png"),
                os.path.join(config.RESULTS_DIR, "feature_forecast_comparison.png"),
                os.path.join(config.RESULTS_DIR, "timeline_predictions.png"),
                os.path.join(config.RESULTS_DIR, "confusion_matrix.png"),
            ]
            for p in p_list:
                if os.path.exists(p):
                    os.startfile(p)
            print("  Opened graphs in default image viewer.")
    except Exception as e:
        print(f"  Note: Could not automatically open image viewer: {e}")

if __name__ == '__main__':
    main()
