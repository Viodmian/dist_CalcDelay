# -*- coding: utf-8 -*-
"""
Delay 计算核心：支持 WAV / PCM，GCC-PHAT 多段统计，以指定通道为参考输出 delay_samples。
同时提供 16bit 数字截幅 / 填充检测。
"""
import numpy as np
import wave
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


def _rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x) + 1e-20))


def analyze_bandwidth(data, sr, ch=0, window_s=2.0):
    """
    判定音频内容更接近“窄带(NB)”还是“宽带(WB)”。

    规则（工程启发式）：
    - sr <= 8000：直接判定为 NB（系统带宽上限不足以承载 >4kHz 的宽带语音）
    - sr >= 16000：取一段音频做频谱能量比：
        hi_ratio = E(4kHz~Nyquist) / E(0~Nyquist)
      hi_ratio 高于阈值则判定为 WB，否则 NB。

    返回 dict：
      {
        "label": "WB" | "NB",
        "hi_ratio": float,   # 高频能量占比
        "threshold": float,
        "sr": int
      }
    """
    sr = int(sr)
    if sr <= 8000:
        return {"label": "NB", "hi_ratio": 0.0, "threshold": 0.02, "sr": sr}

    n_frames, n_ch = data.shape
    ch = int(np.clip(ch, 0, n_ch - 1))
    win_len = int(window_s * sr)
    win_len = max(min(win_len, n_frames), min(sr // 2, n_frames))  # 至少 0.5s
    # 取中间窗口，避免开头静音或切换
    start = max(0, (n_frames - win_len) // 2)
    seg = data[start : start + win_len, ch].astype(np.float64)
    if seg.size < 16:
        return {"label": "NB", "hi_ratio": 0.0, "threshold": 0.02, "sr": sr}

    # 简单去均值 + 汉宁窗
    seg = seg - float(np.mean(seg))
    w = np.hanning(seg.size)
    xw = seg * w
    # FFT
    X = np.fft.rfft(xw)
    P = (np.abs(X) ** 2).astype(np.float64)
    freqs = np.fft.rfftfreq(xw.size, d=1.0 / sr)

    # 0~Nyquist 总能量
    total_e = float(np.sum(P)) + 1e-20
    # 4kHz 以上能量（如果 Nyquist < 4kHz，则为 0）
    hi_mask = freqs >= 4000.0
    hi_e = float(np.sum(P[hi_mask])) if np.any(hi_mask) else 0.0
    hi_ratio = hi_e / total_e

    # 阈值：经验值。语音宽带一般会有可见的 >4kHz 能量；窄带则几乎没有。
    threshold = 0.02
    label = "WB" if hi_ratio >= threshold else "NB"
    return {"label": label, "hi_ratio": float(hi_ratio), "threshold": float(threshold), "sr": sr}


def load_wav(path):
    """加载 WAV，返回 (data, sr)。data shape=(n_frames, n_ch), 16bit 仅支持。"""
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        sr = w.getframerate()
        nframes = w.getnframes()
        raw = w.readframes(nframes)
    if sw != 2:
        raise ValueError("仅支持 16-bit WAV")
    data = np.frombuffer(raw, dtype=np.int16)
    data = data.reshape(-1, nch).astype(np.float64) / 32768.0
    return data, sr


def load_pcm(path, sample_rate, bit_depth, channels):
    """加载裸 PCM。支持 16bit，返回 (data, sr)。"""
    if bit_depth != 16:
        raise ValueError("仅支持 16-bit PCM")
    data = np.fromfile(path, dtype=np.int16)
    if data.size % channels != 0:
        raise ValueError(f"文件长度 {data.size} 不是通道数 {channels} 的整数倍")
    data = data.reshape(-1, channels).astype(np.float64) / 32768.0
    return data, int(sample_rate)


def analyze_clipping(path, is_wav, pcm_sample_rate=None, pcm_bit_depth=16, pcm_channels=None):
    """
    数字截幅 / 填充检测：统计每个通道在 16bit 上限/下限处的样本数与最长硬顶片段。
    返回列表 stats，长度为通道数；每个元素为字典：
        {
            "pos_count": 正饱和样本数 (== 32767),
            "neg_count": 负饱和样本数 (== -32768),
            "pos_ratio": 正饱和样本占比,
            "neg_ratio": 负饱和样本占比,
            "ratio":     总截幅样本占比 (0~1),
            "max_run":   最长连续截幅片段长度（采样点）,
            "first_run_start": 第一段最长片段的大致起始位置（采样点，若无则为 -1）,
            "mode":      'none' | 'clipping' | 'fill'
        }
    """
    if is_wav:
        with wave.open(path, "rb") as w:
            nch = w.getnchannels()
            sw = w.getsampwidth()
            nframes = w.getnframes()
            raw = w.readframes(nframes)
        if sw != 2:
            raise ValueError("仅支持 16-bit WAV")
        data_i16 = np.frombuffer(raw, dtype=np.int16).reshape(-1, nch)
    else:
        if pcm_bit_depth != 16:
            raise ValueError("仅支持 16-bit PCM")
        if pcm_channels is None:
            raise ValueError("PCM 模式下需要提供通道数以做截幅检测")
        data_i16 = np.fromfile(path, dtype=np.int16)
        if data_i16.size % pcm_channels != 0:
            raise ValueError(f"文件长度 {data_i16.size} 不是通道数 {pcm_channels} 的整数倍")
        data_i16 = data_i16.reshape(-1, pcm_channels)

    n_frames, n_ch = data_i16.shape
    total = float(n_frames)
    stats = []
    for ch in range(n_ch):
        x = data_i16[:, ch]
        pos_mask = x == 32767
        neg_mask = x == -32768
        clip_mask = pos_mask | neg_mask
        pos_count = int(pos_mask.sum())
        neg_count = int(neg_mask.sum())

        if clip_mask.any():
            idx = np.flatnonzero(clip_mask)
            diffs = np.diff(idx)
            boundaries = np.where(diffs != 1)[0] + 1
            starts = np.concatenate(([0], boundaries))
            ends = np.concatenate((boundaries, [len(idx)]))
            lengths = ends - starts
            max_idx = int(np.argmax(lengths))
            max_run = int(lengths[max_idx])
            first_run_start = int(idx[starts[max_idx]])
        else:
            max_run = 0
            first_run_start = -1

        if total > 0:
            pos_ratio = pos_count / total
            neg_ratio = neg_count / total
        else:
            pos_ratio = neg_ratio = 0.0
        ratio = pos_ratio + neg_ratio

        if max_run > 0:
            mode = "clipping"
        else:
            mode = "none"

        stats.append(
            {
                "pos_count": pos_count,
                "neg_count": neg_count,
                "pos_ratio": float(pos_ratio),
                "neg_ratio": float(neg_ratio),
                "ratio": float(ratio),
                "max_run": max_run,
                "first_run_start": first_run_start,
                "mode": mode,
            }
        )

    return stats


def gcc_phat_delay(sig_a, sig_b, max_tau_samples=None, interp=1):
    """
    计算 sig_b 相对 sig_a 的时延（采样点）。
    正数表示 sig_b 相对 sig_a 滞后。
    """
    n = len(sig_a)
    assert len(sig_b) == n
    if max_tau_samples is None:
        max_tau_samples = n // 2
    max_tau_samples = min(max_tau_samples, n // 2 - 1)

    n_fft = n * 2 * interp
    a = np.zeros(n_fft)
    b = np.zeros(n_fft)
    a[:n] = sig_a
    b[:n] = sig_b

    fa = np.fft.rfft(a)
    fb = np.fft.rfft(b)
    R = fa * np.conj(fb)
    denom = np.abs(R)
    denom[denom < 1e-12] = 1e-12
    R = R / denom
    corr = np.fft.irfft(R, n=n_fft)

    half = n_fft // 2
    max_tau_idx = min(int(max_tau_samples * interp), half - 1)
    idx_neg_start = n_fft - max_tau_idx
    region_pos = corr[0 : max_tau_idx + 1]
    region_neg = corr[idx_neg_start:]
    if np.max(np.abs(region_pos)) >= np.max(np.abs(region_neg)):
        peak_idx = np.argmax(np.abs(region_pos))
    else:
        peak_idx = idx_neg_start + np.argmax(np.abs(region_neg))
    if peak_idx <= half:
        delay_samples = peak_idx / interp
    else:
        delay_samples = (peak_idx - n_fft) / interp
    return float(delay_samples)


def _normalized_corr_confidence(sig_a, sig_b, delay_samples):
    """
    计算给定 delay_samples 下的归一化相关系数绝对值，作为 delay 置信度。
    返回范围约为 [0, 1]，越接近 1 代表该段越可靠。
    """
    # gcc_phat_delay 的符号方向与“对齐 sig_b 到 sig_a”相反；
    # 这里取反后再做重叠对齐，保证置信度反映估计 delay 下的实际相似度。
    lag = -int(np.round(float(delay_samples)))
    n = len(sig_a)
    if n != len(sig_b) or n < 8:
        return 0.0

    if lag >= 0:
        overlap = n - lag
        if overlap < 8:
            return 0.0
        x = sig_a[:overlap]
        y = sig_b[lag:lag + overlap]
    else:
        lead = -lag
        overlap = n - lead
        if overlap < 8:
            return 0.0
        x = sig_a[lead:lead + overlap]
        y = sig_b[:overlap]

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    x = x - float(np.mean(x))
    y = y - float(np.mean(y))

    denom = float(np.sqrt(np.sum(x * x) * np.sum(y * y))) + 1e-12
    rho = float(np.dot(x, y) / denom)
    return float(np.clip(abs(rho), 0.0, 1.0))


def _segment_delays_fft_reuse(seg, ref_ch, max_tau_samples, interp=1):
    """
    单段内计算所有通道相对 ref_ch 的 delay_samples（复用 FFT）。
    seg shape=(seg_len, n_ch)
    返回 (delays, confidences)，长度均为 n_ch
    """
    n, n_ch = seg.shape
    if n < 8:
        return [0.0] * n_ch, [0.0] * n_ch

    n_fft = n * 2 * interp
    a = np.zeros((n_fft, n_ch), dtype=np.float64)
    a[:n, :] = seg

    F = np.fft.rfft(a, axis=0)
    Fref = F[:, ref_ch]
    R = Fref[:, None] * np.conj(F)
    denom = np.abs(R)
    denom[denom < 1e-12] = 1e-12
    R = R / denom
    corr = np.fft.irfft(R, n=n_fft, axis=0)

    half = n_fft // 2
    max_tau_idx = min(int(max_tau_samples * interp), half - 1)
    idx_neg_start = n_fft - max_tau_idx

    region_pos = corr[0 : max_tau_idx + 1, :]
    region_neg = corr[idx_neg_start:, :]
    abs_pos = np.abs(region_pos)
    abs_neg = np.abs(region_neg)

    max_pos = abs_pos.max(axis=0)
    max_neg = abs_neg.max(axis=0)
    use_pos = max_pos >= max_neg

    peak_pos = abs_pos.argmax(axis=0)
    peak_neg = abs_neg.argmax(axis=0)
    peak_idx = np.where(use_pos, peak_pos, idx_neg_start + peak_neg)

    delay = np.where(peak_idx <= half, peak_idx / interp, (peak_idx - n_fft) / interp).astype(np.float64)
    delay[ref_ch] = 0.0
    delays = [float(x) for x in delay]
    confidences = [0.0] * n_ch
    for ch in range(n_ch):
        if ch == ref_ch:
            confidences[ch] = 1.0
        else:
            confidences[ch] = _normalized_corr_confidence(seg[:, ref_ch], seg[:, ch], delays[ch])
    return delays, confidences


def compute_delays(
    data,
    sr,
    ref_ch,
    segment_s=10.0,
    step_s=10.0,
    start_s=0.0,
    max_tau_s=0.2,
    *,
    parallel=True,
    workers=None,
    fft_reuse=True,
    return_details=False,
    confidence_threshold=0.45,
):
    """
    多段 GCC-PHAT，以 ref_ch 为参考，返回各通道相对 ref 的 delay_samples（中位数）。
    返回: (delays_list, n_segs) 或 (delays_list, n_segs, details)
    - delays_list[i] = 通道 i 相对 ref 的 delay（ref 自身为 0）
    """
    n_frames, n_ch = data.shape
    seg_len = int(segment_s * sr)
    step_len = int(step_s * sr)
    start_frame = int(start_s * sr)
    max_tau_samples = int(max_tau_s * sr)

    ch_delays = [[] for _ in range(n_ch)]

    segments = []
    seg_idx = 0
    while True:
        s = start_frame + seg_idx * step_len
        e = s + seg_len
        if e > n_frames:
            break
        center_s = ((s + e) * 0.5) / float(sr)
        segments.append((seg_idx, s, e, center_s))
        seg_idx += 1

    n_segs = len(segments)
    min_confident_segments = min(n_segs, max(3, int(np.ceil(n_segs * 0.2)))) if n_segs > 0 else 0
    if n_segs == 0:
        if return_details:
            details = {
                "times_s": [],
                "per_channel_delays": [[] for _ in range(n_ch)],
                "per_channel_confidences": [[] for _ in range(n_ch)],
                "summary_confidences": [0.0 for _ in range(n_ch)],
                "raw_delays": [0.0 for _ in range(n_ch)],
                "confident_segment_counts": [0 for _ in range(n_ch)],
                "used_confidence_filter": [False for _ in range(n_ch)],
                "confidence_threshold": float(confidence_threshold),
                "min_confident_segments": min_confident_segments,
            }
            return [0.0 for _ in range(n_ch)], 0, details
        return [0.0 for _ in range(n_ch)], 0

    def compute_one(seg_info):
        idx, s, e, center_s = seg_info
        seg = data[s:e, :]
        if fft_reuse:
            delays, confidences = _segment_delays_fft_reuse(seg, ref_ch, max_tau_samples, interp=1)
            return idx, center_s, delays, confidences
        out = [0.0] * n_ch
        conf = [0.0] * n_ch
        for ch in range(n_ch):
            if ch == ref_ch:
                out[ch] = 0.0
                conf[ch] = 1.0
            else:
                out[ch] = gcc_phat_delay(seg[:, ref_ch], seg[:, ch], max_tau_samples=max_tau_samples, interp=1)
                conf[ch] = _normalized_corr_confidence(seg[:, ref_ch], seg[:, ch], out[ch])
        return idx, center_s, out, conf

    per_seg_times = [0.0] * n_segs
    per_seg_delays = [[0.0] * n_segs for _ in range(n_ch)]
    per_seg_confidences = [[0.0] * n_segs for _ in range(n_ch)]

    def store_result(result):
        idx, center_s, dlist, clist = result
        per_seg_times[idx] = float(center_s)
        for ch in range(n_ch):
            value = float(dlist[ch])
            ch_delays[ch].append(value)
            per_seg_delays[ch][idx] = value
            per_seg_confidences[ch][idx] = float(clist[ch])

    if parallel and n_segs > 1:
        if workers is None:
            cpu = os.cpu_count() or 2
            workers = max(1, min(4, cpu // 2))
        workers = max(1, min(int(workers), n_segs))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(compute_one, seg_info) for seg_info in segments]
            for fut in as_completed(futures):
                store_result(fut.result())
    else:
        for seg_info in segments:
            store_result(compute_one(seg_info))

    raw_delays = [float(np.median(ch_delays[ch])) for ch in range(n_ch)]
    delays = [0.0 for _ in range(n_ch)]
    confident_segment_counts = [0 for _ in range(n_ch)]
    used_confidence_filter = [False for _ in range(n_ch)]

    for ch in range(n_ch):
        if ch == ref_ch:
            delays[ch] = 0.0
            confident_segment_counts[ch] = n_segs
            continue

        confident_values = [
            per_seg_delays[ch][idx]
            for idx, conf in enumerate(per_seg_confidences[ch])
            if conf >= float(confidence_threshold)
        ]
        confident_segment_counts[ch] = len(confident_values)
        if confident_segment_counts[ch] >= min_confident_segments:
            delays[ch] = float(np.median(confident_values))
            used_confidence_filter[ch] = True
        else:
            delays[ch] = raw_delays[ch]

    if return_details:
        summary_confidences = [float(np.median(per_seg_confidences[ch])) for ch in range(n_ch)]
        details = {
            "times_s": per_seg_times,
            "per_channel_delays": per_seg_delays,
            "per_channel_confidences": per_seg_confidences,
            "summary_confidences": summary_confidences,
            "raw_delays": raw_delays,
            "confident_segment_counts": confident_segment_counts,
            "used_confidence_filter": used_confidence_filter,
            "confidence_threshold": float(confidence_threshold),
            "min_confident_segments": min_confident_segments,
        }
        return delays, n_segs, details
    return delays, n_segs

