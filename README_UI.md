# DelayScope UI 工具

本工具用于分析多通道 WAV / PCM 音频中，各通道相对参考通道的时间差、漂移趋势、可靠性以及输入质量。

## 1. 使用方式

### 直接运行

```powershell
cd C:\path\to\DelayScope
pip install -r requirements_ui.txt
python delay_calc_ui.py
```

### 打包运行

```powershell
cd C:\path\to\DelayScope
.\build_ui.bat
```

可执行文件位置：

- `dist\DelayScope.exe`

## 2. 界面输入项说明

### 输入文件

- 选择 `.wav` 或 `.pcm` 文件

### 格式

- `WAV`：自动读取采样率、位深、通道数
- `PCM`：需手动填写采样率、位深、通道数

### 参考通道

- 选择哪一路作为时间基准
- 所有 delay 都是“相对这一路”的结果

### 分段参数

- `每段`：每个分析片段长度，单位秒
- `步长`：相邻片段之间的起点间隔，单位秒
- `起始`：从原始音频第几秒开始分析

## 3. 工具输出了哪些数据

### 3.1 Delay 结果

文本区中的：

- `chX: +N (M ms)`

表示：

- 通道 `chX` 相对参考通道的延时为 `N` 个采样点
- 对应时间差为 `M` 毫秒

用途：

- 用于多通道时间对齐
- 用于判断各链路先后顺序

### 3.2 Delay Drift 图

该图显示每个有效分段上的 delay 值：

- 横轴：分段中心时间，单位秒
- 纵轴：该分段的 `delay_samples`

用途：

- 判断 delay 是否稳定
- 判断是否存在时间漂移
- 排查时钟偏差、缓存滑移、异步采集问题

### 3.3 Confidence 图

该图显示每个有效分段上的归一化相关系数绝对值 `|rho|`：

- 范围约为 `0 ~ 1`
- 越接近 `1`，delay 结果越可靠

用途：

- 判断某个分段的 delay 是否可信
- 找出静音、弱相关、异常分段

### 3.4 置信度摘要

文本里的“各通道 delay 置信度摘要”显示的是：

- 每个通道所有分段 `|rho|` 的中位数

用途：

- 快速看最终 delay 的整体可信度

### 3.5 带宽判定

输出示例：

- `宽带(WB)`
- `窄带(NB)`
- `hi_ratio`
- `threshold`

含义：

- 通过参考通道的频谱高频能量占比判断，当前内容更像宽带还是窄带

用途：

- 判断输入信号频带是否受限
- 辅助理解 delay / confidence 的表现

### 3.6 数字截幅 / 填充检测

文本中的：

- `pos_count`
- `neg_count`
- `ratio_total`
- `短平顶截幅`
- `疑似填充/丢帧`

含义：

- 统计 16-bit 满刻度样本以及最长连续饱和片段

用途：

- 判断前端是否削顶
- 排查采集数据是否出现恒值填充或丢帧

## 4. 数据计算原理概述

### Delay

- 每个分段使用 GCC-PHAT 计算时延峰值
- 所有分段结果取中位数，得到最终 `delay_samples`

### Delay Drift

- 保留每个分段的原始 delay 结果
- 用于画出 delay 随时间变化的轨迹

### Confidence

- 按估计 delay 对齐两路分段信号
- 计算重叠区间上的归一化相关系数绝对值 `|rho|`
- 用于表示该分段 delay 的可靠性

### 带宽判定

- 分析参考通道 `4kHz ~ Nyquist` 的频谱能量占比

### 截幅 / 填充检测

- 检查样本是否达到 16-bit 满刻度
- 同时统计最长连续饱和片段

完整公式和更详细原理见：

- [README.md](README.md)

## 5. 图表交互

独立图表窗口支持：

- 两个页面：`Delay Drift` 和 `Confidence`
- 双击：恢复全视图
- 左键拖动：框选缩放
- 中键拖动：平移
- 鼠标滚轮：缩放
- 工具栏：`Home / Back / Forward / Pan / Zoom / Save`
- 状态栏：显示 `Normal / Zoom / Pan`

## 6. 使用建议

- 若只关心固定时延：看最终 `delay_samples`
- 若关心时延是否稳定：看 `Delay Drift`
- 若关心结果是否可信：看 `Confidence`
- 若发现结果异常：同时检查带宽判定和截幅 / 填充检测

## 7. 依赖

- Python 3.7+
- numpy
- matplotlib
- customtkinter
- pyinstaller
