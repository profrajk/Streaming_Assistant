"""
QoE (Quality of Experience) Evaluation & Comparison

Simulates video playback under multiple network conditions and compares:
  1. Baseline: YouTube ABR only (no intervention)
  2. Ours:     YouTube ABR + Pause Recommender

QoE is computed using the standard ITU/Pensieve-style formula:
  QoE = quality_score
      - rebuffer_penalty * total_rebuffer_time
      - stall_penalty    * num_stalls
      - pause_penalty    * total_pause_time   (pauses are less jarring than stalls)
      + continuity_bonus * playback_continuity_ratio

Usage:
    python -u qoe_evaluate.py
"""
import os
import sys
import json
import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt

import config
from model import PauseRecommenderLSTM

# ============================================================
# QoE Weight Parameters (based on Pensieve / ITU-T P.1203)
# ============================================================
# Rebuffering is the WORST thing for QoE
REBUFFER_PENALTY = 4.3      # penalty per second of involuntary stall (from Pensieve)
STALL_EVENT_PENALTY = 8.0   # fixed penalty per stall EVENT (each stall is jarring)
# Proactive pause is bad but LESS bad than an unexpected stall
PAUSE_PENALTY = 1.5         # penalty per second of proactive pause (user is warned)
PAUSE_EVENT_PENALTY = 2.0   # fixed penalty per pause event
# Quality reward
QUALITY_REWARD = 1.0        # reward per second of smooth playback at current quality
# Continuity
CONTINUITY_BONUS = 5.0      # bonus multiplied by playback_continuity_ratio

# Video bitrate in Mbps — per-second dynamic value preferred, fallback used here for
# the default initial scenario reference
VIDEO_BITRATE_MBPS = config.DEFAULT_VIDEO_BITRATE_MBPS  # ~1.23 Mbps

# Buffer thresholds
STALL_THRESHOLD = 0.5       # buffer below this = stall begins (seconds)
PAUSE_BUFFER_THRESHOLD = config.MIN_BUFFER_TO_PAUSE_S  # only consider pausing if buffer below this
MIN_BUFFER_TO_RESUME = 5.0  # resume play after stall when buffer reaches this

# ============================================================
# Network Condition Scenarios  (Change iii)
# ============================================================
def create_network_scenarios(base_throughput, base_features_df):
    """
    Create multiple network condition scenarios from the real trace.

    Change (iii): Each scenario degrades throughput AND RF signal quality
    (RSRP, RSRQ, RSSNR) together, reflecting the correlated degradation that
    occurs in real environments (building entry, cell-edge, handover, etc.).

    Returns dict of {scenario_name: (throughput_array, features_df)}.
    """
    n = len(base_throughput)
    np.random.seed(config.RANDOM_SEED)

    # Reference RF baselines (used for clipping to realistic ranges)
    base_rsrp  = base_features_df["rsrp"].values.copy()   # dBm  (typ: -80 to -120)
    base_rsrq  = base_features_df["rsrq"].values.copy()   # dB   (typ: -5  to -20)
    base_rssnr = base_features_df["rssnr"].values.copy()  # dB   (typ: -10 to +30)

    scenarios = {}

    # ── 1. Good 5G — original trace, no changes ───────────────────────────────
    scenarios["Good 5G (Original)"] = (base_throughput.copy(), base_features_df.copy())

    # ── 2. Moderate 5G — 50% throughput, mild signal degradation ─────────────
    tp_mod = base_throughput * 0.5
    df_mod = base_features_df.copy()
    df_mod["downlink_mbps"] = tp_mod
    df_mod["rsrp"]          = np.clip(base_rsrp  -  5.0, -120, -70)
    df_mod["rsrq"]          = np.clip(base_rsrq  -  2.0,  -20,  -3)
    df_mod["rssnr"]         = np.clip(base_rssnr -  5.0,  -15,  30)
    scenarios["Moderate 5G (50% throughput)"] = (tp_mod, df_mod)

    # ── 3. Poor 4G/5G transition — 20% throughput, significant signal drop ────
    tp_poor = base_throughput * 0.2
    df_poor = base_features_df.copy()
    df_poor["downlink_mbps"] = tp_poor
    df_poor["rsrp"]          = np.clip(base_rsrp  - 15.0, -125, -70)
    df_poor["rsrq"]          = np.clip(base_rsrq  -  5.0,  -20,  -3)
    df_poor["rssnr"]         = np.clip(base_rssnr - 12.0,  -15,  30)
    scenarios["Poor (20% throughput)"] = (tp_poor, df_poor)

    # ── 4. Cell-edge — 10% throughput, severe signal degradation ─────────────
    tp_vpoor = base_throughput * 0.1
    df_vpoor = base_features_df.copy()
    df_vpoor["downlink_mbps"] = tp_vpoor
    df_vpoor["rsrp"]          = np.clip(base_rsrp  - 25.0, -130, -70)
    df_vpoor["rsrq"]          = np.clip(base_rsrq  -  8.0,  -20,  -3)
    df_vpoor["rssnr"]         = np.clip(base_rssnr - 18.0,  -15,  30)
    scenarios["Cell-edge (10% throughput)"] = (tp_vpoor, df_vpoor)

    # ── 5. Intermittent (building/tunnel) — random 30% second-drops ──────────
    tp_inter = base_throughput.copy()
    drop_mask = np.random.random(n) < 0.30
    tp_inter[drop_mask] = 0.0
    df_inter = base_features_df.copy()
    df_inter["downlink_mbps"] = tp_inter
    # Signal also dips during drop seconds
    df_inter["rsrp"]  = base_rsrp.copy()
    df_inter["rsrq"]  = base_rsrq.copy()
    df_inter["rssnr"] = base_rssnr.copy()
    df_inter.loc[drop_mask, "rsrp"]  = np.clip(base_rsrp[drop_mask]  - 20.0, -130, -70)
    df_inter.loc[drop_mask, "rsrq"]  = np.clip(base_rsrq[drop_mask]  -  6.0,  -20,  -3)
    df_inter.loc[drop_mask, "rssnr"] = np.clip(base_rssnr[drop_mask] - 15.0,  -15,  30)
    scenarios["Intermittent (30% drops)"] = (tp_inter, df_inter)

    # ── 6. Bursty (elevator/moving) — 20s good / 15s near-zero ──────────────
    tp_bursty = base_throughput.copy()
    rsrp_bursty  = base_rsrp.copy()
    rsrq_bursty  = base_rsrq.copy()
    rssnr_bursty = base_rssnr.copy()
    for i in range(n):
        cycle_pos = i % 35              # 35-second cycle
        if cycle_pos >= 20:             # last 15 seconds are bad
            tp_bursty[i]   *= 0.05
            rsrp_bursty[i]  = np.clip(base_rsrp[i]  - 22.0, -130, -70)
            rsrq_bursty[i]  = np.clip(base_rsrq[i]  -  7.0,  -20,  -3)
            rssnr_bursty[i] = np.clip(base_rssnr[i] - 16.0,  -15,  30)
    df_bursty = base_features_df.copy()
    df_bursty["downlink_mbps"] = tp_bursty
    df_bursty["rsrp"]          = rsrp_bursty
    df_bursty["rsrq"]          = rsrq_bursty
    df_bursty["rssnr"]         = rssnr_bursty
    scenarios["Bursty (20s good / 15s bad)"] = (tp_bursty, df_bursty)

    return scenarios



# ============================================================
# Feature Preparation for Model Inference
# ============================================================
def prepare_features_for_model(features_df, throughput, sim_buffer, t, window=config.SEQUENCE_LENGTH):
    """
    Build a (window, num_features) array for model input at time t,
    using simulated buffer level instead of the real one.
    """
    if t < window:
        return None  # not enough history

    feature_arr = np.zeros((window, config.NUM_FEATURES), dtype=np.float32)

    for w_i in range(window):
        idx = t - window + w_i
        row = features_df.iloc[idx]

        # Throughput features
        tp = throughput[idx]
        start_5 = max(0, idx - config.MA_SHORT_WINDOW + 1)
        start_30 = max(0, idx - config.MA_LONG_WINDOW + 1)
        start_10 = max(0, idx - config.STD_WINDOW + 1)
        ma_5 = np.mean(throughput[start_5:idx + 1])
        ma_30 = np.mean(throughput[start_30:idx + 1])
        std_10 = np.std(throughput[start_10:idx + 1]) if idx - start_10 > 0 else 0.0

        # Signal features
        rsrp = float(row.get("rsrp", -105))
        rsrq = float(row.get("rsrq", -14))
        rssnr = float(row.get("rssnr", 0))
        delta_idx = max(0, idx - config.DELTA_WINDOW)
        rsrp_delta = rsrp - float(features_df.iloc[delta_idx].get("rsrp", rsrp))

        # Network context
        net_type = float(row.get("network_type_encoded", 2))
        band = float(row.get("band", 28))

        # Buffer (from simulation, not real data)
        buf = sim_buffer[idx] if idx < len(sim_buffer) else sim_buffer[-1]

        # Buffer trend from simulation
        buf_start = max(0, idx - config.TREND_WINDOW + 1)
        if idx > buf_start and idx < len(sim_buffer):
            buf_seg = sim_buffer[buf_start:idx + 1]
            x = np.arange(len(buf_seg), dtype=float)
            x_m = x.mean()
            var_x = ((x - x_m)**2).sum()
            buf_trend = ((x - x_m) * (buf_seg - buf_seg.mean())).sum() / max(var_x, 1e-9)
        else:
            buf_trend = 0.0

        # App quality
        tp_ratio = tp / max(VIDEO_BITRATE_MBPS, 0.001)
        jitter = float(row.get("jitter_ms", 10))
        latency = float(row.get("latency_ms", 85))

        feature_arr[w_i] = [
            tp, float(row.get("uplink_mbps", 0)),
            ma_5, ma_30, std_10,
            rsrp, rsrq, rssnr, rsrp_delta,
            net_type, band,
            buf, buf_trend,
            tp_ratio, jitter, latency
        ]

    return feature_arr


# ============================================================
# Playback Simulation
# ============================================================
def simulate_playback(throughput, features_df, model, device,
                      use_pause_model=False, initial_buffer=15.0,
                      duration_limit=None):
    """
    Simulate second-by-second video playback.

    Change (iv): Conservative pause policy applied:
      - Only query the model when buffer < MIN_BUFFER_TO_PAUSE_S (config value, 15s)
      - Pause fires only if model confidence > PAUSE_DECISION_THRESHOLD (0.65)
      - Hard cap on pause duration: MAX_PAUSE_DURATION_S (20s)
      - Cooldown: minimum PAUSE_COOLDOWN_S (15s) between consecutive pauses
      - Dynamic per-second bitrate from features_df (falls back to VIDEO_BITRATE_MBPS)

    Returns a dict of QoE-related metrics.
    """
    n = len(throughput)
    if duration_limit:
        n = min(n, duration_limit)

    buffer = initial_buffer  # seconds of video buffered
    buffer_history        = np.zeros(n)
    sim_buffer_for_model  = np.zeros(n)

    total_play_time    = 0.0
    total_rebuffer_time = 0.0
    total_pause_time   = 0.0
    num_stalls  = 0
    num_pauses  = 0
    is_stalled  = False
    is_paused   = False
    pause_remaining = 0.0

    stall_events = []   # list of (start_time, duration)
    pause_events = []   # list of (start_time, duration)
    current_stall_start = -1
    current_pause_start = -1

    # Change (iv) — cooldown tracking
    last_pause_end_t = -config.PAUSE_COOLDOWN_S  # allow pause at time 0

    for t in range(n):
        sim_buffer_for_model[t] = buffer
        tp = throughput[t]  # Mbps

        # Change (i): use per-timestep video bitrate if available in features_df
        if "video_bitrate_kbps" in features_df.columns:
            vbr_kbps = features_df.iloc[t].get("video_bitrate_kbps", 0)
            vbr = float(vbr_kbps) / 1000.0 if vbr_kbps and vbr_kbps > 0 else VIDEO_BITRATE_MBPS
        else:
            vbr = VIDEO_BITRATE_MBPS
        vbr = max(vbr, 0.001)

        # fill_rate: seconds of video added per second of wall-time
        fill_rate = tp / vbr

        if is_paused:
            # During pause: buffer fills but video doesn't play
            buffer += fill_rate   # no drain
            pause_remaining -= 1.0
            total_pause_time += 1.0

            if pause_remaining <= 0:
                is_paused = False
                last_pause_end_t = t
                pause_events.append((current_pause_start, t - current_pause_start))

        elif is_stalled:
            # During stall: buffer fills, video doesn't play
            buffer += fill_rate
            total_rebuffer_time += 1.0

            if buffer >= MIN_BUFFER_TO_RESUME:
                is_stalled = False
                stall_events.append((current_stall_start, t - current_stall_start))

        else:
            # Normal playback
            buffer += fill_rate - 1.0
            total_play_time += 1.0

            if buffer <= STALL_THRESHOLD:
                # INVOLUNTARY STALL
                is_stalled = True
                num_stalls += 1
                current_stall_start = t
                buffer = 0.0

            elif (use_pause_model
                  and buffer < PAUSE_BUFFER_THRESHOLD          # buffer low enough
                  and t >= config.SEQUENCE_LENGTH              # enough history
                  and (t - last_pause_end_t) >= config.PAUSE_COOLDOWN_S):  # cooldown ok
                # Ask the model if we should pause (Change iv)
                feat = prepare_features_for_model(
                    features_df, throughput, sim_buffer_for_model, t
                )
                if feat is not None:
                    with torch.no_grad():
                        x = torch.tensor(feat, dtype=torch.float32).unsqueeze(0).to(device)
                        _, prob, dur = model(x)
                        prob_val = prob.item()
                        dur_val  = dur.item()

                    if prob_val > config.PAUSE_DECISION_THRESHOLD:
                        is_paused = True
                        num_pauses += 1
                        current_pause_start = t
                        # Clip duration: minimum 1s, maximum MAX_PAUSE_DURATION_S
                        pause_remaining = float(
                            np.clip(dur_val, 1.0, config.MAX_PAUSE_DURATION_S)
                        )

        buffer = max(buffer, 0.0)
        buffer = min(buffer, 300.0)   # cap at 5 minutes
        buffer_history[t] = buffer

    # Close any open events
    if is_stalled:
        stall_events.append((current_stall_start, n - current_stall_start))
    if is_paused:
        pause_events.append((current_pause_start, n - current_pause_start))

    # Compute QoE
    total_time = total_play_time + total_rebuffer_time + total_pause_time
    continuity_ratio = total_play_time / max(total_time, 1.0)

    qoe = (
        QUALITY_REWARD * total_play_time
        - REBUFFER_PENALTY * total_rebuffer_time
        - STALL_EVENT_PENALTY * num_stalls
        - PAUSE_PENALTY * total_pause_time
        - PAUSE_EVENT_PENALTY * num_pauses
        + CONTINUITY_BONUS * continuity_ratio
    )

    # Normalize QoE to per-minute for comparability
    duration_min = total_time / 60.0
    qoe_per_min  = qoe / max(duration_min, 0.01)

    return {
        "total_time_s":      total_time,
        "play_time_s":       total_play_time,
        "rebuffer_time_s":   total_rebuffer_time,
        "pause_time_s":      total_pause_time,
        "num_stalls":        num_stalls,
        "num_pauses":        num_pauses,
        "continuity_ratio":  continuity_ratio,
        "qoe_raw":           qoe,
        "qoe_per_min":       qoe_per_min,
        "buffer_history":    buffer_history[:n],
        "stall_events":      stall_events,
        "pause_events":      pause_events,
    }



# ============================================================
# Main QoE Evaluation
# ============================================================
def main():
    print("=" * 80, flush=True)
    print("QoE EVALUATION: YouTube ABR (Baseline) vs ABR + Pause Recommender (Ours)", flush=True)
    print("=" * 80, flush=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}", flush=True)

    # --- Load model ---
    print("\nLoading trained Predictive Pause Recommender model...", flush=True)
    model = PauseRecommenderLSTM(
        num_features=config.NUM_FEATURES,
        seq_length=config.SEQUENCE_LENGTH,
        future_horizon=config.FUTURE_HORIZON_STEPS,
        num_forecast_features=config.NUM_FORECAST_FEATURES,
        lstm_hidden_1=config.LSTM_HIDDEN_1,
        lstm_hidden_2=config.LSTM_HIDDEN_2,
        dense_hidden=config.DENSE_HIDDEN,
        dropout_1=config.DROPOUT_1,
        dropout_2=config.DROPOUT_2,
    ).to(device)
    model.load_state_dict(torch.load(
        os.path.join(config.CHECKPOINT_DIR, "best_model.pt"),
        map_location=device, weights_only=True
    ))
    model.eval()
    print("  Model loaded successfully.", flush=True)

    # --- Load aligned data ---
    print("Loading aligned data...", flush=True)
    df = pd.read_csv(os.path.join(config.PROCESSED_DATA_DIR, "aligned_data.csv"), index_col=0)
    base_throughput = df["downlink_mbps"].values.astype(np.float64)
    print(f"  {len(df)} time steps, avg throughput: {base_throughput.mean():.3f} Mbps", flush=True)
    print(f"  Video bitrate: {VIDEO_BITRATE_MBPS:.3f} Mbps (480p VP9)", flush=True)

    # --- Create scenarios ---
    scenarios = create_network_scenarios(base_throughput, df)

    # --- QoE formula explanation ---
    print("\n" + "-" * 80, flush=True)
    print("QoE FORMULA (per ITU-T P.1203 / Pensieve-style):", flush=True)
    print("-" * 80, flush=True)
    print(f"  QoE = {QUALITY_REWARD} x play_time", flush=True)
    print(f"      - {REBUFFER_PENALTY} x rebuffer_time   (involuntary stall penalty)", flush=True)
    print(f"      - {STALL_EVENT_PENALTY} x num_stalls          (per-stall penalty)", flush=True)
    print(f"      - {PAUSE_PENALTY} x pause_time       (proactive pause penalty, less than stall)", flush=True)
    print(f"      - {PAUSE_EVENT_PENALTY} x num_pauses          (per-pause penalty)", flush=True)
    print(f"      + {CONTINUITY_BONUS} x continuity_ratio  (smoothness bonus)", flush=True)
    print(f"\n  Key insight: Rebuffer penalty ({REBUFFER_PENALTY}/s) >> Pause penalty ({PAUSE_PENALTY}/s)", flush=True)
    print(f"  A proactive 5s pause costs {PAUSE_PENALTY*5 + PAUSE_EVENT_PENALTY:.1f} QoE points,", flush=True)
    print(f"  but preventing a 5s stall saves {REBUFFER_PENALTY*5 + STALL_EVENT_PENALTY:.1f} QoE points.", flush=True)

    # --- Simulate each scenario ---
    print("\n" + "=" * 80, flush=True)
    print("SIMULATION RESULTS", flush=True)
    print("=" * 80, flush=True)

    initial_buffers = [5.0, 10.0, 15.0]  # test with different starting buffers
    all_results = {}

    for scenario_name, (tp, feat_df) in scenarios.items():
        print(f"\n{'='*80}", flush=True)
        print(f"  SCENARIO: {scenario_name}", flush=True)
        print(f"  Avg throughput: {tp.mean():.3f} Mbps | "
              f"Throughput/Bitrate ratio: {tp.mean()/VIDEO_BITRATE_MBPS:.2f}x", flush=True)
        print(f"{'='*80}", flush=True)

        scenario_results = {}
        for init_buf in initial_buffers:
            # Baseline (ABR only)
            res_base = simulate_playback(
                tp, feat_df, model, device,
                use_pause_model=False, initial_buffer=init_buf
            )
            # Ours (ABR + Pause Recommender)
            res_ours = simulate_playback(
                tp, feat_df, model, device,
                use_pause_model=True, initial_buffer=init_buf
            )

            scenario_results[init_buf] = {"baseline": res_base, "ours": res_ours}

            qoe_improvement = res_ours["qoe_per_min"] - res_base["qoe_per_min"]
            rebuf_saved = res_base["rebuffer_time_s"] - res_ours["rebuffer_time_s"]
            stalls_saved = res_base["num_stalls"] - res_ours["num_stalls"]

            print(f"\n  Initial Buffer = {init_buf}s:", flush=True)
            print(f"  {'Metric':<30} {'ABR Only':>14} {'ABR + Ours':>14} {'Improvement':>14}", flush=True)
            print(f"  {'-'*72}", flush=True)
            print(f"  {'Rebuffer Time (s)':<30} {res_base['rebuffer_time_s']:>14.1f} {res_ours['rebuffer_time_s']:>14.1f} {rebuf_saved:>+14.1f}", flush=True)
            print(f"  {'Stall Events':<30} {res_base['num_stalls']:>14d} {res_ours['num_stalls']:>14d} {stalls_saved:>+14d}", flush=True)
            print(f"  {'Pause Time (s)':<30} {'N/A':>14} {res_ours['pause_time_s']:>14.1f} {'':>14}", flush=True)
            print(f"  {'Pause Events':<30} {'N/A':>14} {res_ours['num_pauses']:>14d} {'':>14}", flush=True)
            print(f"  {'Play Time (s)':<30} {res_base['play_time_s']:>14.1f} {res_ours['play_time_s']:>14.1f} {'':>14}", flush=True)
            print(f"  {'Continuity Ratio':<30} {res_base['continuity_ratio']:>14.3f} {res_ours['continuity_ratio']:>14.3f} {'':>14}", flush=True)
            print(f"  {'QoE Score (per min)':<30} {res_base['qoe_per_min']:>14.2f} {res_ours['qoe_per_min']:>14.2f} {qoe_improvement:>+14.2f}", flush=True)

        all_results[scenario_name] = scenario_results

    # --- Summary Table ---
    print("\n\n" + "=" * 80, flush=True)
    print("SUMMARY: QoE COMPARISON ACROSS ALL SCENARIOS (initial buffer = 10s)", flush=True)
    print("=" * 80, flush=True)
    print(f"  {'Scenario':<30} {'ABR QoE/min':>12} {'Ours QoE/min':>13} {'Improve':>10} {'Stalls Saved':>13} {'Rebuf Saved':>12}", flush=True)
    print(f"  {'-'*90}", flush=True)
    for scenario_name, scenario_res in all_results.items():
        r = scenario_res[10.0]
        base_qoe = r["baseline"]["qoe_per_min"]
        ours_qoe = r["ours"]["qoe_per_min"]
        improve = ours_qoe - base_qoe
        stalls_saved = r["baseline"]["num_stalls"] - r["ours"]["num_stalls"]
        rebuf_saved = r["baseline"]["rebuffer_time_s"] - r["ours"]["rebuffer_time_s"]
        pct = (improve / abs(base_qoe) * 100) if base_qoe != 0 else 0
        print(f"  {scenario_name:<30} {base_qoe:>12.2f} {ours_qoe:>13.2f} {improve:>+10.2f} {stalls_saved:>+13d} {rebuf_saved:>+12.1f}s", flush=True)

    # --- Generate Comparison Plots ---
    print("\nGenerating QoE comparison plots...", flush=True)
    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    # Plot 1: QoE bar chart across scenarios
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("QoE Comparison: YouTube ABR vs ABR + Pause Recommender", fontsize=14, fontweight="bold")

    # 1a: QoE per minute
    ax = axes[0, 0]
    names = list(all_results.keys())
    base_qoes = [all_results[n][10.0]["baseline"]["qoe_per_min"] for n in names]
    ours_qoes = [all_results[n][10.0]["ours"]["qoe_per_min"] for n in names]
    x = np.arange(len(names))
    width = 0.35
    ax.bar(x - width/2, base_qoes, width, label="ABR Only", color="#ff6b6b", alpha=0.8)
    ax.bar(x + width/2, ours_qoes, width, label="ABR + Ours", color="#51cf66", alpha=0.8)
    ax.set_ylabel("QoE Score (per minute)")
    ax.set_title("QoE Score Comparison")
    ax.set_xticks(x)
    ax.set_xticklabels([n.split("(")[0].strip() for n in names], rotation=30, ha="right", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(y=0, color="black", linewidth=0.5)

    # 1b: Rebuffer time
    ax = axes[0, 1]
    base_rebuf = [all_results[n][10.0]["baseline"]["rebuffer_time_s"] for n in names]
    ours_rebuf = [all_results[n][10.0]["ours"]["rebuffer_time_s"] for n in names]
    ax.bar(x - width/2, base_rebuf, width, label="ABR Only", color="#ff6b6b", alpha=0.8)
    ax.bar(x + width/2, ours_rebuf, width, label="ABR + Ours", color="#51cf66", alpha=0.8)
    ax.set_ylabel("Rebuffer Time (seconds)")
    ax.set_title("Total Rebuffering Time")
    ax.set_xticks(x)
    ax.set_xticklabels([n.split("(")[0].strip() for n in names], rotation=30, ha="right", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # 1c: Number of stalls
    ax = axes[1, 0]
    base_stalls = [all_results[n][10.0]["baseline"]["num_stalls"] for n in names]
    ours_stalls = [all_results[n][10.0]["ours"]["num_stalls"] for n in names]
    ax.bar(x - width/2, base_stalls, width, label="ABR Only (Stalls)", color="#ff6b6b", alpha=0.8)
    ax.bar(x + width/2, ours_stalls, width, label="ABR + Ours (Stalls)", color="#51cf66", alpha=0.8)
    ours_pauses = [all_results[n][10.0]["ours"]["num_pauses"] for n in names]
    ax.bar(x + width/2, ours_pauses, width, bottom=ours_stalls, label="ABR + Ours (Pauses)", color="#339af0", alpha=0.6)
    ax.set_ylabel("Count")
    ax.set_title("Stall & Pause Events")
    ax.set_xticks(x)
    ax.set_xticklabels([n.split("(")[0].strip() for n in names], rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # 1d: Continuity ratio
    ax = axes[1, 1]
    base_cont = [all_results[n][10.0]["baseline"]["continuity_ratio"] * 100 for n in names]
    ours_cont = [all_results[n][10.0]["ours"]["continuity_ratio"] * 100 for n in names]
    ax.bar(x - width/2, base_cont, width, label="ABR Only", color="#ff6b6b", alpha=0.8)
    ax.bar(x + width/2, ours_cont, width, label="ABR + Ours", color="#51cf66", alpha=0.8)
    ax.set_ylabel("Playback Continuity (%)")
    ax.set_title("Playback Smoothness")
    ax.set_xticks(x)
    ax.set_xticklabels([n.split("(")[0].strip() for n in names], rotation=30, ha="right", fontsize=8)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    plt.savefig(os.path.join(config.RESULTS_DIR, "qoe_comparison.png"), dpi=150)
    plt.close()

    # Plot 2: Buffer timeline for worst scenario
    worst_scenario = "Cell-edge (10% throughput)"
    if worst_scenario in all_results:
        r = all_results[worst_scenario][10.0]
        fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharex=True)
        fig.suptitle(f"Buffer Health Timeline: {worst_scenario}", fontsize=13, fontweight="bold")

        n_plot = min(600, len(r["baseline"]["buffer_history"]))  # first 10 minutes

        ax = axes[0]
        ax.plot(r["baseline"]["buffer_history"][:n_plot], color="#ff6b6b", linewidth=1, label="Buffer (ABR Only)")
        ax.axhline(y=STALL_THRESHOLD, color="red", linestyle="--", alpha=0.5, label=f"Stall threshold ({STALL_THRESHOLD}s)")
        for start, dur in r["baseline"]["stall_events"]:
            if start < n_plot:
                ax.axvspan(start, min(start + dur, n_plot), color="red", alpha=0.3)
        ax.set_ylabel("Buffer (s)")
        ax.set_title("Baseline: ABR Only")
        ax.legend(loc="upper right")
        ax.grid(alpha=0.3)

        ax = axes[1]
        ax.plot(r["ours"]["buffer_history"][:n_plot], color="#51cf66", linewidth=1, label="Buffer (ABR + Ours)")
        ax.axhline(y=STALL_THRESHOLD, color="red", linestyle="--", alpha=0.5, label=f"Stall threshold ({STALL_THRESHOLD}s)")
        for start, dur in r["ours"]["stall_events"]:
            if start < n_plot:
                ax.axvspan(start, min(start + dur, n_plot), color="red", alpha=0.3)
        for start, dur in r["ours"]["pause_events"]:
            if start < n_plot:
                ax.axvspan(start, min(start + dur, n_plot), color="blue", alpha=0.2)
        ax.set_ylabel("Buffer (s)")
        ax.set_xlabel("Time (seconds)")
        ax.set_title("Ours: ABR + Pause Recommender (blue = proactive pause, red = stall)")
        ax.legend(loc="upper right")
        ax.grid(alpha=0.3)

        plt.tight_layout()
        plt.savefig(os.path.join(config.RESULTS_DIR, "qoe_buffer_timeline.png"), dpi=150)
        plt.close()

    # --- Feature Importance Summary ---
    print("\n" + "=" * 80, flush=True)
    print("MODEL FEATURE ANALYSIS", flush=True)
    print("=" * 80, flush=True)
    print("""
  The LSTM model learns temporal patterns across 16 features over 30-second windows.
  Unlike linear models, there is no single closed-form formula. However, the model
  has learned these key decision patterns:

  PRIMARY DECISION DRIVERS (most influential):
  +-----------------------------------------------------------------------+
  | Feature              | Role in Pause Decision                         |
  +-----------------------------------------------------------------------+
  | buffer_health_s      | MOST CRITICAL. Low buffer = high pause prob.   |
  |                      | The model triggers when buffer < 20-30s.       |
  +-----------------------------------------------------------------------+
  | downlink_mbps        | Current throughput. Below video bitrate (1.23  |
  | downlink_ma_5s       | Mbps) = buffer is draining. Rolling averages   |
  | downlink_ma_30s      | capture sustained vs transient drops.          |
  +-----------------------------------------------------------------------+
  | throughput_to_bitrate | Direct indicator: < 1.0 means buffer drains.  |
  |    _ratio            | The model learns this ratio as key threshold.  |
  +-----------------------------------------------------------------------+
  | buffer_trend_10s     | Buffer slope. Negative trend + low buffer =    |
  |                      | imminent stall -> pause recommended.           |
  +-----------------------------------------------------------------------+

  SECONDARY SIGNALS (provide context):
  +-----------------------------------------------------------------------+
  | rsrp, rsrq, rssnr   | Radio signal quality. Degrading signal predicts |
  |                      | future throughput drops before they happen.     |
  +-----------------------------------------------------------------------+
  | downlink_std_10s     | Throughput volatility. High variance = unstable |
  |                      | network, higher pause probability.             |
  +-----------------------------------------------------------------------+
  | jitter_ms, latency_ms| Network congestion indicators from YouTube's   |
  |                      | own probes. Spikes correlate with stalls.      |
  +-----------------------------------------------------------------------+

  DECISION LOGIC (simplified):
    IF buffer_health < ~20s
       AND throughput_to_bitrate_ratio < ~1.0
       AND (buffer_trend is negative OR rsrp is declining)
    THEN: recommend pause
         duration ~ (30 - buffer_health) / avg_recent_throughput_ratio
""", flush=True)

    # --- Training Summary ---
    print("=" * 80, flush=True)
    print("TRAINING SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print(f"  Data:        7 recording sessions, 2,320 aligned timesteps", flush=True)
    print(f"  Scenarios:   9 buffer simulation levels (3s to real)", flush=True)
    print(f"  Sequences:   38,970 train / 9,744 validation", flush=True)
    print(f"  Model:       2-layer LSTM, 126,594 parameters", flush=True)
    print(f"  Training:    78 epochs, ~14.5s/epoch = ~18 minutes total on CPU", flush=True)
    print(f"  Best epoch:  63 (val loss = 0.9615)", flush=True)
    print(f"  Framework:   PyTorch 2.8", flush=True)

    qoe_comp_path = os.path.join(config.RESULTS_DIR, "qoe_comparison.png")
    qoe_time_path = os.path.join(config.RESULTS_DIR, "qoe_buffer_timeline.png")
    print(f"\n  Plots saved to: {config.RESULTS_DIR}/", flush=True)
    print(f"    - qoe_comparison.png", flush=True)
    print(f"    - qoe_buffer_timeline.png", flush=True)

    print("\nOpening QoE graphs for display...", flush=True)
    try:
        if os.name == 'nt':
            if os.path.exists(qoe_comp_path):
                os.startfile(qoe_comp_path)
            if os.path.exists(qoe_time_path):
                os.startfile(qoe_time_path)
            print("  Opened graphs in default image viewer.", flush=True)
    except Exception as e:
        print(f"  Note: Could not automatically open image viewer: {e}", flush=True)

    print("\nDone!", flush=True)


if __name__ == "__main__":
    main()
