"""
Predictive Pause Recommender Neural Network.

Two-Stage Architecture:
  Stage 1: Temporal Feature Forecaster (predicts future network & buffer features for next H seconds)
  Stage 2: Pause Decision Network (predicts pause probability & duration based on forecasted dynamics)
"""
import torch
import torch.nn as nn
import config


class PredictivePauseRecommenderLSTM(nn.Module):
    """
    Two-stage predictive model:
      1. Encodes past 30 seconds of 16 features via 2-layer LSTM.
      2. Forecasts future H=10 seconds of key features (Throughput, RSRP, RSRQ, RSSNR, Buffer, Throughput/Bitrate).
      3. Decision head evaluates the forecasted future to recommend pause probability & duration.
    """
    def __init__(
        self,
        num_features=config.NUM_FEATURES,
        seq_length=config.SEQUENCE_LENGTH,
        future_horizon=config.FUTURE_HORIZON_STEPS,
        num_forecast_features=config.NUM_FORECAST_FEATURES,
        lstm_hidden_1=config.LSTM_HIDDEN_1,
        lstm_hidden_2=config.LSTM_HIDDEN_2,
        dense_hidden=config.DENSE_HIDDEN,
        dropout_1=config.DROPOUT_1,
        dropout_2=config.DROPOUT_2
    ):
        super(PredictivePauseRecommenderLSTM, self).__init__()
        
        self.num_features = num_features
        self.seq_length = seq_length
        self.future_horizon = future_horizon
        self.num_forecast_features = num_forecast_features
        
        # 1. Batch Normalization across historical features
        self.bn1 = nn.BatchNorm1d(num_features)
        
        # 2. Historical Encoder (LSTM Layer 1 & 2)
        self.lstm1 = nn.LSTM(
            input_size=num_features,
            hidden_size=lstm_hidden_1,
            batch_first=True
        )
        self.dropout1 = nn.Dropout(dropout_1)
        
        self.lstm2 = nn.LSTM(
            input_size=lstm_hidden_1,
            hidden_size=lstm_hidden_2,
            batch_first=True
        )
        self.dropout2 = nn.Dropout(dropout_2)
        
        # 3. Stage 1: Future Feature Forecaster
        # Predicts (future_horizon x num_forecast_features) from historical representation
        self.forecast_dim = future_horizon * num_forecast_features
        self.forecaster = nn.Sequential(
            nn.Linear(lstm_hidden_2, 64),
            nn.ReLU(),
            nn.Linear(64, self.forecast_dim)
        )
        
        # 4. Stage 2: Pause Decision Network
        # Concatenates historical encoding (64) + forecasted future features (H * K)
        decision_input_dim = lstm_hidden_2 + self.forecast_dim
        self.decision_fc = nn.Sequential(
            nn.Linear(decision_input_dim, dense_hidden),
            nn.ReLU()
        )
        
        # Output Heads
        self.head_cls = nn.Linear(dense_hidden, 1)
        self.sigmoid = nn.Sigmoid()
        
        self.head_reg = nn.Linear(dense_hidden, 1)
        self.relu_out = nn.ReLU()

    def forward(self, x):
        """
        Args:
            x: Tensor of shape (batch_size, seq_length, num_features)
        Returns:
            future_features_pred: (batch_size, future_horizon, num_forecast_features)
            pause_prob: (batch_size, 1)
            pause_duration: (batch_size, 1)
        """
        # Apply BatchNorm1d (requires channel dim in position 1)
        x_t = x.transpose(1, 2)
        x_norm = self.bn1(x_t).transpose(1, 2)
        
        # Encoder
        x_enc, _ = self.lstm1(x_norm)
        x_enc = self.dropout1(x_enc)
        
        _, (h_n, _) = self.lstm2(x_enc)
        h_last = self.dropout2(h_n[-1])  # (batch_size, lstm_hidden_2)
        
        # Stage 1: Forecast Future Features
        forecast_flat = self.forecaster(h_last)  # (batch_size, H * K)
        future_features_pred = forecast_flat.view(
            -1, self.future_horizon, self.num_forecast_features
        )
        
        # Stage 2: Decision Based on Forecasted Future + Historical Context
        combined = torch.cat([h_last, forecast_flat], dim=-1)
        feat_dec = self.decision_fc(combined)
        
        pause_prob = self.sigmoid(self.head_cls(feat_dec))
        pause_duration = self.relu_out(self.head_reg(feat_dec))
        
        return future_features_pred, pause_prob, pause_duration


class PredictivePauseLoss(nn.Module):
    """
    Multi-task loss:
      1. Future Feature Forecasting Loss (MSE)
      2. Pause Classification Loss (BCE)
      3. Pause Duration Loss (Masked MSE)
    """
    def __init__(
        self,
        forecast_weight=config.FORECAST_LOSS_WEIGHT,
        cls_weight=config.CLASSIFICATION_LOSS_WEIGHT,
        reg_weight=config.REGRESSION_LOSS_WEIGHT
    ):
        super(PredictivePauseLoss, self).__init__()
        self.forecast_weight = forecast_weight
        self.cls_weight = cls_weight
        self.reg_weight = reg_weight
        
        self.mse_forecast = nn.MSELoss()
        self.bce_cls = nn.BCELoss()
        self.mse_reg = nn.MSELoss(reduction='none')

    def forward(self, future_pred, pause_prob_pred, pause_dur_pred,
                future_target, pause_label, dur_label):
        # 1. Forecasting Loss
        forecast_loss = self.mse_forecast(future_pred, future_target)
        
        # 2. Classification Loss
        cls_loss = self.bce_cls(pause_prob_pred, pause_label)
        
        # 3. Masked Regression Loss (only where should_pause == 1)
        reg_losses = self.mse_reg(pause_dur_pred, dur_label)
        mask = pause_label.float()
        
        if mask.sum() > 0:
            reg_loss = (reg_losses * mask).sum() / mask.sum()
        else:
            reg_loss = torch.tensor(0.0, device=pause_prob_pred.device)
            
        total_loss = (
            self.forecast_weight * forecast_loss +
            self.cls_weight * cls_loss +
            self.reg_weight * reg_loss
        )
        
        return total_loss, forecast_loss, cls_loss, reg_loss


# Backward compatibility aliases
PauseRecommenderLSTM = PredictivePauseRecommenderLSTM
PauseRecommenderLoss = PredictivePauseLoss
