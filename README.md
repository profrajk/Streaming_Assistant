Streaming Assistant is a QoE-aware intelligent assistant designed to improve the user experience during adaptive video streaming under challenging and variable network conditions.

Conventional Adaptive Bitrate (ABR) algorithms continuously adapt the video representation based primarily on network throughput, buffer occupancy, and other streaming conditions. However, when network conditions deteriorate rapidly or remain below the bitrate required to sustain playback, ABR may not always prevent future rebuffering.

The Streaming Assistant addresses this gap by predicting potential future QoE degradation and recommending appropriate interventions before a severe playback interruption occurs.

The core principle is: **A small, temporary QoE sacrifice can prevent a much larger future QoE degradation.**


**Motivation**

Modern mobile and wireless networks can exhibit significant variations in:

Available throughput
Radio-frequency (RF) conditions
Network latency
Throughput variability
Buffer occupancy

These variations can cause the playback buffer to gradually deplete even when the video is currently playing smoothly.

An ABR algorithm may respond by switching to a lower representation. However, if the available throughput continues to remain insufficient, the buffer can eventually become empty, resulting in rebuffering/stalling.

The Streaming Assistant therefore focuses on the future state of playback, rather than only the current streaming state.


**Research Objective**

The primary objective of this project is to develop an intelligent assistant capable of:

Monitoring the current streaming conditions.
Understanding the relationship between network conditions and buffer evolution.
Predicting the likelihood of future playback degradation.
Recommending an appropriate intervention.
Improving overall session-level QoE rather than optimizing only instantaneous video quality.
