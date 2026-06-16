## DelayCalcTool 计算说明

DelayCalcTool 用于分析多通道音频中各通道相对参考通道的到达时延，并给出稳定性、可靠性与音频质量相关辅助指标。

当前工具会输出和展示以下几类数据：

- `delay_samples`：各通道相对参考通道的时延，单位为采样点
- `delay_time_ms`：把 `delay_samples` 换算成毫秒后的时间差
- `per-segment delay track`：每个分段上的 delay 轨迹，用于观察漂移
- `confidence / |rho|`：基于归一化相关系数的 delay 置信度
- `bandwidth label`：宽带 / 窄带判定
- `clipping / fill stats`：数字截幅 / 疑似恒值填充统计

本文档说明这些数据是如何计算的、其原理是什么，以及它们有什么用。

---

## 1. 工具输入与总体流程

工具输入：

- WAV 文件，自动读取采样率、位深、通道数
- PCM 文件，需要手动指定采样率、位深、通道数

当前版本只支持 `16-bit PCM` 数据。

总体流程：

1. 读取多通道音频数据
2. 选择一个参考通道 `ref_ch`
3. 按 `segment_s / step_s / start_s` 把整段音频切成多个分段
4. 对每个分段执行一次 GCC-PHAT 时延估计
5. 对每个通道的多段 delay 取中位数，得到最终 `delay_samples`
6. 对每个分段、每个通道再计算一个归一化相关系数 `|rho|`，作为该分段 delay 的可靠性
7. 额外做带宽判定与数字截幅 / 填充检测

---

## 2. 基本定义

设：

- 采样率为 $f_s$ Hz
- 某通道相对参考通道的时延为 $\Delta n$ 个采样点

则时间差为：

$$
\Delta t = \frac{\Delta n}{f_s}
$$

换成毫秒：

$$
\Delta t_{ms} = \frac{\Delta n}{f_s} \times 1000
$$

符号含义：

- $\Delta n > 0$：该通道相对参考通道更晚到达，即滞后
- $\Delta n < 0$：该通道相对参考通道更早到达，即超前
- 参考通道自身的 delay 恒为 `0`

用途：

- 用于多通道对齐
- 用于判断麦克风阵列、录音链路、采集卡、DSP 通路之间是否存在固定时差
- 用于后续波束形成、AEC、阵列定位、回声路径分析前的前置校正

---

## 3. `delay_samples` 是怎么计算的

### 3.1 单段 delay 估计原理：GCC-PHAT

在某个分段内，设：

- 参考通道信号为 $x[n]$
- 待测通道信号为 $y[n]$

先做傅里叶变换：

$$
X(k) = \mathcal{F}\{x[n]\}, \quad Y(k) = \mathcal{F}\{y[n]\}
$$

构造互功率谱：

$$
R_{xy}(k) = X(k)Y^*(k)
$$

然后进行 PHAT 加权，只保留相位信息：

$$
G^{PHAT}_{xy}(k) = \frac{R_{xy}(k)}{|R_{xy}(k)| + \varepsilon}
$$

其中 $\varepsilon$ 是一个很小的常数，用于防止除零。

再做逆变换得到时域互相关：

$$
r_{xy}[\tau] = \mathcal{F}^{-1}\{G^{PHAT}_{xy}(k)\}
$$

在给定最大时延搜索范围内寻找绝对值峰值：

$$
\hat{\tau} = \arg\max_{\tau \in [-\tau_{max},\tau_{max}]} |r_{xy}[\tau]|
$$

这个 $\hat{\tau}$ 就是该分段上的 `delay_samples`。

工程含义：

- GCC-PHAT 对幅度起伏不敏感，更关注相位一致性
- 相比直接互相关，它对语音、多路径、增益差异通常更稳一些

用途：

- 估计通道相对到达时间差
- 判断两个通道是否同步、谁先谁后

### 3.2 多段统计

整段音频往往不是均匀稳定的：可能有静音、说话、噪声、突发冲击、掉帧等异常片段。因此工具不会只计算一次 delay，而是按参数切成多段：

- `segment_s`：每段长度，单位秒
- `step_s`：分段步长，单位秒
- `start_s`：起始偏移，单位秒

第 $k$ 段对应：

$$
[n_0 + kS,\ n_0 + kS + L)
$$

其中：

- $L = segment_s \cdot f_s$
- $S = step_s \cdot f_s$
- $n_0 = start_s \cdot f_s$

每段都独立计算一次 delay，最后对每个通道的多段结果取中位数：

$$
\widetilde{\Delta n}_c = median(\Delta n_{c,0}, \Delta n_{c,1}, ..., \Delta n_{c,K-1})
$$

为什么用中位数：

- 比平均值更抗异常段
- 某几段估计失败，不容易把最终结果拖偏

用途：

- 让最终 delay 更稳
- 适合长录音、多场景、多说话片段的工程分析

---

## 4. `delay_time_ms` / 文本中的毫秒是怎么来的

这是由 `delay_samples` 直接换算得到：

$$
delay\_time\_ms = \frac{delay\_samples}{f_s} \times 1000
$$

用途：

- 给人看更直观
- 便于和设备规格、算法参数、AEC 尾长、同步设计目标直接比对

例如：

- `delay_samples = 16`
- `f_s = 16000`

则：

$$
delay\_time\_ms = \frac{16}{16000} \times 1000 = 1 ms
$$

---

## 5. `per-segment delay track` / Delay Drift 图是怎么来的

工具在每个有效分段上都会计算一个 delay，不只保留最终中位数，也保留整条分段轨迹：

- `times_s[k]`：第 `k` 段中心时间点，单位秒
- `per_channel_delays[ch][k]`：第 `k` 段上该通道相对参考通道的 delay

图中的横轴：

- 分段中心时间 `times_s`

图中的纵轴：

- 每段的 `delay_samples`

用途：

- 观察 delay 是否稳定
- 判断是否存在时间漂移
- 排查采样率不一致、异步时钟、缓存滑移、掉帧重采样等问题

典型解读：

- 轨迹基本水平且波动很小：说明通道间 delay 基本稳定
- 轨迹缓慢线性漂移：可能存在采样时钟偏差
- 轨迹偶发大跳变：可能存在异常片段、静音段、突发噪声或丢帧

---

## 6. `confidence / |rho|` 是怎么计算的

### 6.1 计算方法

对于某个分段，先用 GCC-PHAT 得到该段的 `delay_samples`，然后按这个 delay 把两路信号在重叠区间上对齐，计算归一化相关系数：

$$
\rho = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum (x_i - \bar{x})^2 \sum (y_i - \bar{y})^2} + \varepsilon}
$$

工具使用的是绝对值：

$$
|\rho| \in [0,1]
$$

越接近 `1`，说明在该 delay 下两路波形越一致，该段 delay 越可信。

### 6.2 为什么这个值有意义

delay 本身只是“峰值位置”，但并不保证这个峰值一定非常可靠。

例如：

- 静音段
- 低能量段
- 纯噪声段
- 两路根本不是同一内容的段

这些段也可能给出一个 delay，但这个 delay 并不可信。

`|rho|` 的作用就是给这个 delay 一个“可信度”量化指标。

### 6.3 工具里的摘要值和轨迹值

工具同时输出：

- `per_channel_confidences[ch][k]`：每个分段的 `|rho|`
- `summary_confidences[ch]`：该通道所有分段 `|rho|` 的中位数

文本结果里的“置信度摘要”就是 `summary_confidences`。

图里的 `Confidence` 曲线显示的是每段 `|rho|` 轨迹。

用途：

- 判断最终 delay 是否可靠
- 找出哪些时间段不可信
- 辅助筛选可用于同步或标定的有效区间

经验解读：

- `|rho|` 接近 `1`：高可信
- `|rho|` 中等：有参考价值，但应结合波形与场景再判断
- `|rho|` 很低：该段 delay 很可能不可靠

---

## 7. `bandwidth label` / 宽带窄带判定是怎么来的

工具会对参考通道做一个简单的频谱能量比分析。

规则：

- 如果 `sr <= 8000`，直接判定为 `NB`
- 如果 `sr >= 16000`，统计 `4kHz ~ Nyquist` 的高频能量占比：

$$
hi\_ratio = \frac{E(4kHz \sim Nyquist)}{E(0 \sim Nyquist)}
$$

当 `hi_ratio >= threshold` 时判定为 `WB`，否则判定为 `NB`。

当前阈值为：

- `threshold = 0.02`

输出字段：

- `label`：`WB` 或 `NB`
- `hi_ratio`：高频能量占比
- `threshold`：当前判定阈值

用途：

- 快速判断音频内容更像宽带语音还是窄带语音
- 评估上游链路是否被 3.4kHz 左右带宽限制
- 结合 delay 分析判断频带受限是否会影响可靠性

---

## 8. `clipping / fill stats` 是怎么来的

工具会对每个通道统计 16-bit 满刻度样本：

- 正饱和：`+32767`
- 负饱和：`-32768`

输出字段：

- `pos_count`：正饱和样本数
- `neg_count`：负饱和样本数
- `pos_ratio`：正饱和样本占比
- `neg_ratio`：负饱和样本占比
- `ratio_total`：总饱和占比
- `max_run`：最长连续饱和样本长度
- `first_run_start`：最长片段首次出现位置

如果存在持续很长的恒值饱和片段，界面会提示：

- 短平顶截幅
- 疑似填充 / 丢帧

用途：

- 判断前端是否过载削顶
- 排查采集链路是否出现恒值填充、DMA 异常、数据掉帧
- 辅助解释某些 delay 或 confidence 异常

典型关系：

- 截幅严重时，delay 仍可能算得出来，但可靠性可能下降
- 长时间恒值填充时，某些分段的 delay 与 `|rho|` 往往都会异常

---

## 9. 界面中每一行数据的含义和用途

### 9.1 文件信息

- `文件`：当前分析的输入文件路径
- `采样率`：音频采样率，单位 Hz
- `通道数`：音频通道数量
- `时长`：总时长，单位秒

用途：

- 确认输入规格是否符合预期
- 防止 PCM 参数填错后误判结果

### 9.2 带宽判定

- `宽带(WB)` / `窄带(NB)`
- `hi_ratio`
- `threshold`

用途：

- 判断频带条件
- 解释某些场景下 delay / confidence 的稳定性差异

### 9.3 分段信息

- `segment_s`
- `step_s`
- `start_s`
- `有效段数`

用途：

- 确认当前 delay 是基于多少段统计出来的
- 有效段数太少时，最终结果可信度通常较差

### 9.4 参考通道

- `参考通道: chN`

用途：

- 所有 delay 都是相对它计算的
- 更换参考通道后，所有结果都会跟着变换

### 9.5 各通道 delay

- `chX: +12.0 (0.75 ms)`

含义：

- 该通道相对参考通道滞后 12 个采样点，约 0.75 ms

用途：

- 用于通道对齐
- 用于同步校验

### 9.6 各通道置信度摘要

- `chX: 0.962`

含义：

- 该通道在所有有效分段上的 `|rho|` 中位数

用途：

- 给最终 delay 一个整体可靠性概览

### 9.7 截幅 / 填充检测

- `ratio_total`
- `短平顶截幅`
- `疑似填充/丢帧`

用途：

- 判断输入数据质量
- 辅助解释异常 delay 和异常 confidence

---

## 10. 这些数据在工程上怎么用

### 10.1 多通道同步 / 对齐

使用 `delay_samples` 或 `delay_time_ms` 对所有通道做时间补偿，使它们对齐到参考通道。

### 10.2 漂移排查

使用 `Delay Drift` 图判断：

- 是否存在时钟偏差
- 是否存在缓存滑移
- 是否存在异步采集导致的慢性漂移

### 10.3 可靠性筛选

使用 `|rho|` 轨迹筛选可靠分段：

- 高 `|rho|` 区间可用于标定与精确分析
- 低 `|rho|` 区间应谨慎解读或直接排除

### 10.4 质量诊断

结合：

- 宽带 / 窄带判定
- 截幅 / 填充检测
- delay 漂移图
- confidence 图

可以快速定位问题属于：

- 内容相关性不足
- 带宽受限
- 时钟不同步
- 前端削顶
- 数据填充 / 丢帧

---

## 11. 使用时的注意事项

- 当前仅支持 16-bit WAV / PCM
- PCM 参数填写错误会直接导致结果无意义
- 静音段、噪声段、弱相关段会导致 `|rho|` 偏低
- 如果各分段 delay 波动很大，应优先看 `Confidence` 和截幅 / 填充统计，而不是只看最终中位数
- 如果只是想知道“固定时延是多少”，看最终 `delay_samples`
- 如果想知道“时延是否稳定”，看 `Delay Drift`
- 如果想知道“这个结果能不能信”，看 `Confidence`

---

## 12. 代码对应关系

- [delay_core.py](e:/downloads/dist_CalcDelay/delay_core.py)
  - `load_wav(...)` / `load_pcm(...)`：读取输入音频
  - `analyze_bandwidth(...)`：宽带 / 窄带判定
  - `analyze_clipping(...)`：数字截幅 / 填充检测
  - `gcc_phat_delay(...)`：单段 GCC-PHAT delay 估计
  - `_normalized_corr_confidence(...)`：基于对齐后的归一化相关系数计算 `|rho|`
  - `compute_delays(...)`：多段 delay 统计、分段轨迹、置信度摘要

- [delay_calc_ui.py](e:/downloads/dist_CalcDelay/delay_calc_ui.py)
  - `run_calculation(...)`：组织所有计算结果并生成人类可读文本
  - 图表窗口：展示 `Delay Drift` 与 `Confidence` 两个页面

图形界面只是展示层，核心计算公式和数据定义都在 `delay_core.py` 中。

