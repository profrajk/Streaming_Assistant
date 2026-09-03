"""
Training Script for the Predictive Pause Recommender Neural Network.

Trains the two-stage model:
  1. Feature Forecaster (predicts future network & buffer trajectory)
  2. Pause Recommender (predicts proactive pause decision & duration)
"""
import os
import sys
import time
import json
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torch.optim.lr_scheduler import ReduceLROnPlateau

import config
from model import PredictivePauseRecommenderLSTM, PredictivePauseLoss


class PredictiveStreamingDataset(Dataset):
    def __init__(self, X, Y_future, y_cls, y_reg):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.Y_future = torch.tensor(Y_future, dtype=torch.float32)
        self.y_cls = torch.tensor(y_cls, dtype=torch.float32).unsqueeze(-1)
        self.y_reg = torch.tensor(y_reg, dtype=torch.float32).unsqueeze(-1)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.Y_future[idx], self.y_cls[idx], self.y_reg[idx]


def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


def train_one_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    total_loss, total_fcast_loss, total_cls_loss, total_reg_loss = 0.0, 0.0, 0.0, 0.0
    
    for X_b, Y_fut_b, y_cls_b, y_reg_b in dataloader:
        X_b = X_b.to(device)
        Y_fut_b = Y_fut_b.to(device)
        y_cls_b = y_cls_b.to(device)
        y_reg_b = y_reg_b.to(device)

        optimizer.zero_grad()
        
        future_pred, prob_pred, dur_pred = model(X_b)
        
        loss, fcast_loss, cls_loss, reg_loss = criterion(
            future_pred, prob_pred, dur_pred,
            Y_fut_b, y_cls_b, y_reg_b
        )
        
        loss.backward()
        optimizer.step()

        b_size = X_b.size(0)
        total_loss += loss.item() * b_size
        total_fcast_loss += fcast_loss.item() * b_size
        total_cls_loss += cls_loss.item() * b_size
        total_reg_loss += reg_loss.item() * b_size

    num_samples = len(dataloader.dataset)
    return (
        total_loss / num_samples,
        total_fcast_loss / num_samples,
        total_cls_loss / num_samples,
        total_reg_loss / num_samples,
    )


def validate(model, dataloader, criterion, device):
    model.eval()
    total_loss, total_fcast_loss, total_cls_loss, total_reg_loss = 0.0, 0.0, 0.0, 0.0
    
    with torch.no_grad():
        for X_b, Y_fut_b, y_cls_b, y_reg_b in dataloader:
            X_b = X_b.to(device)
            Y_fut_b = Y_fut_b.to(device)
            y_cls_b = y_cls_b.to(device)
            y_reg_b = y_reg_b.to(device)

            future_pred, prob_pred, dur_pred = model(X_b)
            
            loss, fcast_loss, cls_loss, reg_loss = criterion(
                future_pred, prob_pred, dur_pred,
                Y_fut_b, y_cls_b, y_reg_b
            )

            b_size = X_b.size(0)
            total_loss += loss.item() * b_size
            total_fcast_loss += fcast_loss.item() * b_size
            total_cls_loss += cls_loss.item() * b_size
            total_reg_loss += reg_loss.item() * b_size

    num_samples = len(dataloader.dataset)
    return (
        total_loss / num_samples,
        total_fcast_loss / num_samples,
        total_cls_loss / num_samples,
        total_reg_loss / num_samples,
    )


def main():
    set_seed(config.RANDOM_SEED)

    os.makedirs(config.CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}", flush=True)

    # Check for S_buffer-Y flag in CLI arguments
    use_synthetic = any("S_buffer-Y" in arg or "--synthetic" in arg or "s_buffer=y" in arg.lower() for arg in sys.argv)
    if use_synthetic or not os.path.exists(os.path.join(config.PROCESSED_DATA_DIR, "X_train.npy")):
        print(f"Running data parser (synthetic_buffers={use_synthetic})...", flush=True)
        import data_parser
        data_parser.main()

    print("Loading data...", flush=True)
    X_train = np.load(os.path.join(config.PROCESSED_DATA_DIR, "X_train.npy"))
    Y_fut_train = np.load(os.path.join(config.PROCESSED_DATA_DIR, "Y_future_train.npy"))
    y_cls_train = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_cls_train.npy"))
    y_reg_train = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_reg_train.npy"))

    X_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "X_val.npy"))
    Y_fut_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "Y_future_val.npy"))
    y_cls_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_cls_val.npy"))
    y_reg_val = np.load(os.path.join(config.PROCESSED_DATA_DIR, "y_reg_val.npy"))

    print(f"  Train: {X_train.shape[0]} samples, Val: {X_val.shape[0]} samples", flush=True)
    print(f"  Historical shape: ({X_train.shape[1]} timesteps, {X_train.shape[2]} features)", flush=True)
    print(f"  Forecast target shape: ({Y_fut_train.shape[1]} horizon steps, {Y_fut_train.shape[2]} target features)", flush=True)

    train_dataset = PredictiveStreamingDataset(X_train, Y_fut_train, y_cls_train, y_reg_train)
    val_dataset = PredictiveStreamingDataset(X_val, Y_fut_val, y_cls_val, y_reg_val)

    train_loader = DataLoader(train_dataset, batch_size=config.BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=config.BATCH_SIZE, shuffle=False, num_workers=0)

    print("Initializing Predictive Pause Recommender LSTM...", flush=True)
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

    total_params = sum(p.numel() for p in model.parameters())
    print(f"  Model parameters: {total_params:,}", flush=True)

    optimizer = optim.Adam(model.parameters(), lr=config.LEARNING_RATE)
    criterion = PredictivePauseLoss(
        forecast_weight=config.FORECAST_LOSS_WEIGHT,
        cls_weight=config.CLASSIFICATION_LOSS_WEIGHT,
        reg_weight=config.REGRESSION_LOSS_WEIGHT
    )
    scheduler = ReduceLROnPlateau(optimizer, patience=config.LR_REDUCE_PATIENCE, factor=config.LR_REDUCE_FACTOR)

    history = {
        "train_loss": [], "val_loss": [],
        "train_fcast_loss": [], "val_fcast_loss": [],
        "train_cls_loss": [], "val_cls_loss": [],
        "train_reg_loss": [], "val_reg_loss": []
    }

    best_val_loss = float('inf')
    best_epoch = 0
    patience_counter = 0
    best_model_path = os.path.join(config.CHECKPOINT_DIR, "best_model.pt")

    print(f"\nStarting training (max {config.MAX_EPOCHS} epochs, early stop patience={config.EARLY_STOP_PATIENCE})...", flush=True)
    print("-" * 105, flush=True)
    
    for epoch in range(config.MAX_EPOCHS):
        epoch_start = time.time()
        
        t_loss, t_fc, t_cls, t_reg = train_one_epoch(model, train_loader, optimizer, criterion, device)
        v_loss, v_fc, v_cls, v_reg = validate(model, val_loader, criterion, device)

        epoch_time = time.time() - epoch_start

        history["train_loss"].append(t_loss)
        history["val_loss"].append(v_loss)
        history["train_fcast_loss"].append(t_fc)
        history["val_fcast_loss"].append(v_fc)
        history["train_cls_loss"].append(t_cls)
        history["val_cls_loss"].append(v_cls)
        history["train_reg_loss"].append(t_reg)
        history["val_reg_loss"].append(v_reg)

        lr = optimizer.param_groups[0]['lr']
        msg = (f"Epoch [{epoch+1:3d}/{config.MAX_EPOCHS}] "
               f"| Train: {t_loss:.4f} (fc:{t_fc:.4f} cls:{t_cls:.4f} reg:{t_reg:.4f}) "
               f"| Val: {v_loss:.4f} (fc:{v_fc:.4f} cls:{v_cls:.4f} reg:{v_reg:.4f}) "
               f"| LR: {lr:.6f} | {epoch_time:.1f}s")
        print(msg, flush=True)

        scheduler.step(v_loss)

        if v_loss < best_val_loss:
            best_val_loss = v_loss
            best_epoch = epoch
            patience_counter = 0
            torch.save(model.state_dict(), best_model_path)
            print(f"  --> Saved new best model at epoch {epoch+1}", flush=True)
        else:
            patience_counter += 1
            if patience_counter >= config.EARLY_STOP_PATIENCE:
                print(f"\nEarly stopping triggered at epoch {epoch+1}", flush=True)
                break

    print("-" * 105, flush=True)
    
    with open(os.path.join(config.RESULTS_DIR, "training_history.json"), 'w') as f:
        json.dump(history, f, indent=4)

    print(f"\nTraining complete!", flush=True)
    print(f"  Best Validation Loss: {best_val_loss:.4f} at Epoch {best_epoch+1}", flush=True)
    print(f"  Model saved to: {best_model_path}", flush=True)
    print(f"  History saved to: {os.path.join(config.RESULTS_DIR, 'training_history.json')}", flush=True)


if __name__ == '__main__':
    main()
