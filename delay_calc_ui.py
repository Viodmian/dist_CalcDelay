# -*- coding: utf-8 -*-
"""
DelayScope UI — 圆角卡片 + 蓝色主色（customtkinter）
"""
import os
import sys
import threading
import wave
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import matplotlib as mpl
    from matplotlib import font_manager
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# 使用本项目内部的 delay_core 模块，避免与外部同名包冲突。
from delay_core import load_wav, load_pcm, compute_delays, analyze_clipping, analyze_bandwidth

# 圆角 + 蓝色主色
CORNER_RADIUS = 12
BTN_RADIUS = 10
INPUT_RADIUS = 8
BG = "#f0f0f2"
CARD_BG = "#ffffff"
TEXT = "#1d1d1f"
TEXT_SEC = "#6e6e73"
ACCENT = "#007AFF"
ACCENT_HOVER = "#0051d5"
INPUT_BG = "#f5f5f7"
# 滚动条：与整体风格一致，细圆角
SCROLLBAR_TRACK = "#ebebed"
SCROLLBAR_THUMB = "#d1d1d6"
SCROLLBAR_THUMB_HOVER = "#007AFF"
PLOT_COLORS = ["#007AFF", "#FF3B30", "#34C759", "#FF9500", "#5AC8FA", "#5856D6", "#FF2D55", "#8E8E93"]
CONFIDENCE_OK = 0.75
CONFIDENCE_WARN = 0.45
APP_VERSION = "v1.1.0"
APP_NAME = "DelayScope"
APP_USER_MODEL_ID = "Viodmian.DelayScope.Desktop"

# Log / 输出限制，避免文本过大导致拖动/缩放卡顿
MAX_LOG_ENTRIES = 50
MAX_RENDER_LINES = 2500
BUNDLED_FONT_RELATIVE_PATH = os.path.join("fonts", "simhei.ttf")
LOGO_PNG_RELATIVE_PATH = os.path.join("assets", "branding", "delayscope-logo-ui.png")
LOGO_REPORT_RELATIVE_PATH = os.path.join("assets", "branding", "delayscope-logo-256.png")
LOGO_ICO_RELATIVE_PATH = os.path.join("assets", "branding", "delayscope-logo.ico")


def _bundled_resource_path(relative_path: str):
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return os.path.join(sys._MEIPASS, relative_path)
    except Exception:
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def _configure_windows_taskbar_identity():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _configure_matplotlib_fonts():
    """Prefer a bundled CJK-capable font for matplotlib, then fall back to system fonts."""
    if not HAS_MPL:
        return

    bundled_font_name = None
    bundled_font_path = _bundled_resource_path(BUNDLED_FONT_RELATIVE_PATH)
    if os.path.isfile(bundled_font_path):
        try:
            font_manager.fontManager.addfont(bundled_font_path)
            bundled_font_name = font_manager.FontProperties(fname=bundled_font_path).get_name()
        except Exception:
            bundled_font_name = None

    preferred_fonts = [
        bundled_font_name,
        "Microsoft YaHei",
        "Microsoft JhengHei",
        "SimHei",
        "SimSun",
        "NSimSun",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
    ]

    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
    except Exception:
        available = set()

    selected = [name for name in preferred_fonts if name and (not available or name in available)]
    if not selected:
        selected = [name for name in [bundled_font_name, "Microsoft YaHei", "SimHei", "DejaVu Sans"] if name]

    mpl.rcParams["font.sans-serif"] = selected + ["DejaVu Sans"]
    mpl.rcParams["font.family"] = "sans-serif"
    mpl.rcParams["axes.unicode_minus"] = False


_configure_matplotlib_fonts()


def _app_base_dir():
    # 统一工作目录到 exe 所在目录，避免依赖在“当前目录”写出杂项
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _app_runtime_dir():
    """
    运行时工作目录（放在用户临时/本地目录），避免在 exe 同级生成任何杂项目录（如 log/）。
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or tempfile.gettempdir()
    p = os.path.join(base, APP_NAME)
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        p = tempfile.gettempdir()
    return p


def _cleanup_empty_log_dir(base_dir: str):
    # 兼容某些环境/依赖会创建空的 log/ 目录；若为空则直接清理
    p = os.path.join(base_dir, "log")
    try:
        if os.path.isdir(p) and not os.listdir(p):
            os.rmdir(p)
    except Exception:
        pass


def _relocate_exe_log_dir(exe_dir: str, runtime_dir: str):
    """
    把 exe 同级的 log/ 迁移到运行目录，避免污染发版目录。
    """
    src = os.path.join(exe_dir, "log")
    dst = os.path.join(runtime_dir, "log")
    try:
        if not os.path.isdir(src):
            return
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            s = os.path.join(src, name)
            d = os.path.join(dst, name)
            try:
                if os.path.isdir(s):
                    # 尽量迁移子目录，失败则跳过
                    os.replace(s, d)
                else:
                    os.replace(s, d)
            except Exception:
                pass
        # 迁移后如果为空则删除
        if os.path.isdir(src) and not os.listdir(src):
            os.rmdir(src)
    except Exception:
        pass


def _install_log_dir_redirect_guard(exe_dir: str, runtime_dir: str):
    """
    拦截 Python 层对 exe 同级 log/ 的创建，重定向到运行目录。
    """
    target = os.path.normcase(os.path.normpath(os.path.join(exe_dir, "log")))
    redirect = os.path.normcase(os.path.normpath(os.path.join(runtime_dir, "log")))
    os.makedirs(redirect, exist_ok=True)

    _orig_mkdir = os.mkdir
    _orig_makedirs = os.makedirs
    _orig_path_mkdir = Path.mkdir

    def _norm_abs(p):
        try:
            return os.path.normcase(os.path.normpath(os.path.abspath(p)))
        except Exception:
            return ""

    def _map_path(p):
        # 拦截: exe_dir\log 及其子路径
        ap = _norm_abs(p)
        if ap == target or ap.startswith(target + os.sep):
            suffix = ap[len(target) :].lstrip("\\/")
            return os.path.join(redirect, suffix) if suffix else redirect
        return p

    def _mkdir(path, mode=0o777, *, dir_fd=None):
        return _orig_mkdir(_map_path(path), mode=mode, dir_fd=dir_fd)

    def _makedirs(name, mode=0o777, exist_ok=False):
        return _orig_makedirs(_map_path(name), mode=mode, exist_ok=exist_ok)

    def _path_mkdir(self, mode=0o777, parents=False, exist_ok=False):
        mapped = Path(_map_path(str(self)))
        return _orig_path_mkdir(mapped, mode=mode, parents=parents, exist_ok=exist_ok)

    os.mkdir = _mkdir
    os.makedirs = _makedirs
    Path.mkdir = _path_mkdir


def get_wav_info(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getframerate(), w.getnchannels()
    except Exception:
        return None


def classify_delay_reliability(ch, ref_ch, summary_conf, confident_count, n_segs, used_filter):
    if ch == ref_ch:
        return "可信", "参考通道"

    if n_segs <= 0:
        return "不可信", "没有可用分段"

    reliable_min_count = min(n_segs, max(3, (n_segs + 1) // 2))
    review_min_count = min(n_segs, 2 if n_segs >= 2 else 1)

    if confident_count == 0:
        return "不可信", f"0/{n_segs} 段达到 |rho| 阈值，最终值为回退结果"

    if summary_conf < 0.25:
        return "不可信", f"置信度中位数仅 {summary_conf:.3f}"

    if confident_count < review_min_count:
        return "不可信", f"仅 {confident_count}/{n_segs} 段达到 |rho| 阈值"

    if summary_conf >= CONFIDENCE_OK and confident_count >= reliable_min_count:
        return "可信", f"置信度高，且 {confident_count}/{n_segs} 段达到 |rho| 阈值"

    if summary_conf >= CONFIDENCE_WARN and confident_count >= review_min_count:
        if used_filter:
            return "存疑", f"有 {confident_count}/{n_segs} 段达标，但整体置信度仅 {summary_conf:.3f}"
        return "存疑", f"未使用高置信度筛选，且整体置信度仅 {summary_conf:.3f}"

    return "不可信", f"置信度和达标分段数量均不足（{confident_count}/{n_segs}, {summary_conf:.3f}）"


def format_delay_report_line(ch, ref_ch, delay_value, sr, verdict, reason, confident_count, n_segs, used_filter, raw_delay, summary_conf, min_confident_segments):
    verdict_tag = f"[{verdict}]"
    if summary_conf >= CONFIDENCE_OK:
        conf_level = "高"
    elif summary_conf >= CONFIDENCE_WARN:
        conf_level = "中"
    else:
        conf_level = "低"
    conf_desc = f"|rho|={summary_conf:.3f}/{conf_level}"
    if ch == ref_ch:
        extra = (
            f"(used {confident_count}/{n_segs} confident segments; "
            f"min_required={min_confident_segments}; {conf_desc}; 推荐采用)"
        )
        return f"  ch{ch}: {delay_value:+.1f}  ({delay_value/sr*1000:.2f} ms)  {verdict_tag}  {extra}"

    if verdict == "可信":
        recommendation = "推荐采用"
    elif verdict == "存疑":
        recommendation = "建议结合图表复核"
    else:
        recommendation = "仅保留观测值，不建议直接采用"

    if used_filter:
        source_desc = (
            f"source=confident_median {confident_count}/{n_segs} "
            f"(min>={min_confident_segments}); raw_all_segments={raw_delay:+.1f}"
        )
    else:
        source_desc = (
            f"source=all_segments_median; confident_segments={confident_count}/{n_segs} "
            f"(<{min_confident_segments}); raw_all_segments={raw_delay:+.1f}"
        )

    return (
        f"  ch{ch}: {delay_value:+.1f}  ({delay_value/sr*1000:.2f} ms)  {verdict_tag}  "
        f"({recommendation}; {conf_desc}; {source_desc}; {reason})"
    )


def run_calculation(path, is_wav, pcm_sr, pcm_bits, pcm_ch, ref_ch, segment_s, step_s, start_s, result_callback):
    try:
        if is_wav:
            data, sr = load_wav(path)
        else:
            data, sr = load_pcm(path, pcm_sr, pcm_bits, pcm_ch)
        n_frames, n_ch = data.shape
        duration_s = n_frames / sr
        delays, n_segs, details = compute_delays(
            data,
            sr,
            ref_ch,
            segment_s=segment_s,
            step_s=step_s,
            start_s=start_s,
            parallel=True,
            fft_reuse=True,
            return_details=True,
        )
        # 宽带/窄带判定（默认用参考通道做判定）
        bw = analyze_bandwidth(data, sr, ch=ref_ch)
        # 数字截幅 / 填充检测（基于 16bit 饱和）
        if is_wav:
            clip_stats = analyze_clipping(path, True)
        else:
            clip_stats = analyze_clipping(
                path,
                False,
                pcm_sample_rate=pcm_sr,
                pcm_bit_depth=pcm_bits,
                pcm_channels=pcm_ch,
            )

        details.update(
            {
                "source_path": path,
                "source_format": "WAV" if is_wav else "PCM",
                "sample_rate": int(sr),
                "channels": int(n_ch),
                "duration_s": float(duration_s),
                "segment_s": float(segment_s),
                "step_s": float(step_s),
                "start_s": float(start_s),
                "ref_ch": int(ref_ch),
                "delays": [float(x) for x in delays],
                "bandwidth": dict(bw),
                "clip_stats": clip_stats,
            }
        )

        lines = [
            f"文件: {path}",
            f"采样率: {sr} Hz  通道数: {n_ch}  时长: {duration_s:.2f} s",
            f"带宽判定: {('宽带(WB)' if bw['label']=='WB' else '窄带(NB)')}  (hi_ratio={bw['hi_ratio']*100:.2f}%, 阈值={bw['threshold']*100:.2f}%)",
            f"分段: segment_s={segment_s}, step_s={step_s}, start_s={start_s}  有效段数: {n_segs}",
            f"参考通道: ch{ref_ch} (delay = 0)",
            f"最终 delay 汇总策略: 仅当某通道满足 |rho| >= {details['confidence_threshold']:.2f} 的分段数量 >= {details['min_confident_segments']} 时，才使用高置信度分段中位数；否则回退到全部分段中位数",
            "",
            "各通道相对参考的 delay_samples（正数表示该通道滞后于参考；是否建议采用看标签）:",
        ]
        for ch in range(n_ch):
            d = delays[ch]
            conf = details["summary_confidences"][ch]
            confident_count = details["confident_segment_counts"][ch]
            used_filter = details["used_confidence_filter"][ch]
            raw_delay = details["raw_delays"][ch]
            min_confident_segments = details["min_confident_segments"]
            verdict, reason = classify_delay_reliability(
                ch,
                ref_ch,
                conf,
                confident_count,
                n_segs,
                used_filter,
            )
            lines.append(
                format_delay_report_line(
                    ch,
                    ref_ch,
                    d,
                    sr,
                    verdict,
                    reason,
                    confident_count,
                    n_segs,
                    used_filter,
                    raw_delay,
                    conf,
                    min_confident_segments,
                )
            )

        # 追加数字截幅 / 填充检测结果
        lines.append("")
        lines.append("数字截幅 / 填充检测 (16-bit，样本达到 ±32767 视为满刻度):")
        for ch in range(n_ch):
            st = clip_stats[ch]
            pos_c = st["pos_count"]
            neg_c = st["neg_count"]
            pos_ratio = st.get("pos_ratio", 0.0) * 100.0
            neg_ratio = st.get("neg_ratio", 0.0) * 100.0
            ratio = st["ratio"] * 100.0
            max_run = st["max_run"]
            first_start = st["first_run_start"]
            mode = st.get("mode", "none")
            if max_run > 0 and first_start >= 0:
                max_ms = max_run / sr * 1000.0
                start_ms = first_start / sr * 1000.0
                # 以 50ms 为阈值区分“短平顶截幅”和“长时间恒值填充(疑似丢帧)”
                if max_ms >= 50.0:
                    desc = f"疑似填充/丢帧：连续恒值约 {max_ms:.2f} ms @ {start_ms:.2f} ms"
                else:
                    desc = f"短平顶截幅：最长约 {max_ms:.2f} ms @ {start_ms:.2f} ms"
                lines.append(
                    f"  ch{ch}:\n"
                    f"        pos={pos_c}  ratio_pos={pos_ratio:.4f}%\n"
                    f"        neg={neg_c}  ratio_neg={neg_ratio:.4f}%\n"
                    f"        ratio_total={ratio:.4f}%  ({desc})"
                )
            else:
                lines.append(
                    f"  ch{ch}:\n"
                    f"        pos={pos_c}  ratio_pos={pos_ratio:.4f}%\n"
                    f"        neg={neg_c}  ratio_neg={neg_ratio:.4f}%\n"
                    f"        ratio_total={ratio:.4f}%  (未检测到明显数字截幅)"
                )

        msg = "\n".join(lines)
        result_callback(True, msg, delays, n_segs, details)
    except Exception as e:
        result_callback(False, str(e), None, 0, None)
    finally:
        # 计算后再兜底清理一次：如果有依赖在 exe 同级创建空 log/，立刻删除
        try:
            _cleanup_empty_log_dir(_app_base_dir())
        except Exception:
            pass


class DelayCalcApp:
    def __init__(self):
        base_dir = _app_base_dir()
        self.app_base_dir = base_dir
        runtime_dir = _app_runtime_dir()
        self.app_runtime_dir = runtime_dir
        _install_log_dir_redirect_guard(base_dir, runtime_dir)
        try:
            os.chdir(runtime_dir)
        except Exception:
            pass
        # 清理 exe 同级目录中可能出现的空 log/（兜底）
        _cleanup_empty_log_dir(base_dir)
        _relocate_exe_log_dir(base_dir, runtime_dir)

        if not HAS_CTK:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("依赖缺失", "请安装: pip install customtkinter")
            sys.exit(1)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        _configure_windows_taskbar_identity()

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self._apply_window_icon(self.root)
        # 定时兜底清理：有组件若异步创建空 log/，在下一次轮询中移除
        self.root.after(1000, self._periodic_cleanup_log_dir)
        # 初始窗口大小与最小宽度
        self.root.geometry("1040x980")
        self.root.minsize(900, 820)
        self.root.configure(fg_color=BG)
        # 记录基础宽度和 Log 面板宽度，展开 Log 时优先“加宽窗口”而不是压缩主区域
        self.base_width = 1040
        self.log_panel_width = 320

        # 使用 PanedWindow，让用户可拖动分割条改变历史面板宽度
        self.paned = tk.PanedWindow(
            self.root,
            orient="horizontal",
            sashrelief="flat",
            sashwidth=6,
            bg=BG,
            bd=0,
            showhandle=False,
        )
        self.paned.pack(fill="both", expand=True)

        # 左侧主内容区域（原来的滚动区域都放在这里）
        self.main_area = ctk.CTkFrame(self.paned, fg_color="transparent")
        self.paned.add(self.main_area, minsize=500)

        # 右侧 log 面板（默认隐藏，点击“Log”按钮时展开/收起，由 PanedWindow 管控大小）
        self.history_panel = None
        self.log_textbox = None  # Log 文本区域（便于后续动态刷新）
        self.log_placeholder = None
        self.result_placeholder = None

        # resize/拖动时的轻量渲染模式
        self._resize_after_id = None
        self._in_light_mode = False
        self._paned_dragging = False
        self.root.bind("<Configure>", self._on_root_configure)

        # 当前会话内的结果历史（只在本次打开期间有效）
        self.history = []

        self.file_path = ctk.StringVar(value="")
        self.is_wav = ctk.BooleanVar(value=True)
        self.pcm_sr = ctk.StringVar(value="16000")
        self.pcm_bits = ctk.StringVar(value="16")
        self.pcm_ch = ctk.StringVar(value="6")
        self.ref_ch = ctk.StringVar(value="0")
        self.segment_s = ctk.StringVar(value="10")
        self.step_s = ctk.StringVar(value="10")
        self.start_s = ctk.StringVar(value="0")
        self.plot_view = ctk.StringVar(value="delay")
        self.plot_channel_selection = set()
        self.plot_channel_count = 1

        self.ref_ch_buttons = []  # 参考通道分段按钮
        self.plot_channel_buttons = []
        self.plot_view_buttons = []
        self.popup_plot_channel_buttons = []
        self.latest_plot_data = None
        self.latest_result_context = None
        self.btn_export_report = None
        self.delay_fig = None
        self.delay_ax = None
        self.delay_canvas = None
        self.conf_fig = None
        self.conf_ax = None
        self.conf_canvas = None
        self.plot_stack = None
        self.plot_light_placeholder = None
        self.chart_window = None
        self.popup_notebook = None
        self.popup_delay_fig = None
        self.popup_delay_ax = None
        self.popup_delay_canvas = None
        self.popup_delay_toolbar = None
        self.popup_conf_fig = None
        self.popup_conf_ax = None
        self.popup_conf_canvas = None
        self.popup_conf_toolbar = None
        self.popup_plot_interactions = {}
        self.popup_status_var = None
        self.logo_image = None
        self._window_icon_image = None
        self._canvas_draw_after_ids = {}
        self._build_ui()

    def _get_tk_text(self, ctk_textbox):
        # customtkinter.CTkTextbox 内部封装了 tkinter.Text
        return getattr(ctk_textbox, "_textbox", ctk_textbox)

    def _load_logo_image(self):
        path = _bundled_resource_path(LOGO_PNG_RELATIVE_PATH)
        if not os.path.isfile(path):
            return None
        try:
            if HAS_PIL and HAS_CTK:
                img = Image.open(path)
                return ctk.CTkImage(light_image=img, dark_image=img, size=(40, 40))
            return tk.PhotoImage(file=path)
        except Exception:
            return None

    def _apply_window_icon(self, window):
        applied = False
        ico_path = _bundled_resource_path(LOGO_ICO_RELATIVE_PATH)
        if os.path.isfile(ico_path):
            try:
                window.iconbitmap(ico_path)
                applied = True
            except Exception:
                pass

        png_path = _bundled_resource_path(LOGO_REPORT_RELATIVE_PATH)
        if not os.path.isfile(png_path):
            png_path = _bundled_resource_path(LOGO_PNG_RELATIVE_PATH)
        if not os.path.isfile(png_path):
            return applied
        try:
            icon_image = tk.PhotoImage(file=png_path)
            window.iconphoto(True, icon_image)
            if window is self.root:
                self._window_icon_image = icon_image
            else:
                window._window_icon_image = icon_image
            applied = True
        except Exception:
            pass
        return applied

    def _set_text_state(self, ctk_textbox, state: str):
        """确保对内部 tk.Text 设置 state，避免 CTk 封装差异导致 tag 无效。"""
        t = self._get_tk_text(ctk_textbox)
        try:
            t.configure(state=state)
        except Exception:
            try:
                ctk_textbox.configure(state=state)
            except Exception:
                pass

    def _ensure_text_tags(self, ctk_textbox):
        t = self._get_tk_text(ctk_textbox)
        try:
            t.tag_configure("bw", foreground=ACCENT)
            t.tag_configure("section_hdr", foreground=TEXT_SEC)
            t.tag_configure("delay_pos", foreground=ACCENT)
            t.tag_configure("delay_neg", foreground="#FF3B30")  # 红
            t.tag_configure("delay_zero", foreground=TEXT_SEC)
            t.tag_configure("ok", foreground="#34C759")  # 绿
            t.tag_configure("warn", foreground="#FF9500")  # 橙
            t.tag_configure("conf_low", foreground="#FF3B30")
        except Exception:
            pass

    def _insert_line(self, ctk_textbox, line, tag=None):
        t = self._get_tk_text(ctk_textbox)
        if tag:
            try:
                t.insert("end", line + "\n", tag)
                return
            except Exception:
                pass
        t.insert("end", line + "\n")

    def _render_colored_output(self, ctk_textbox, msg, add_end_marker=False):
        """
        将 msg 按行渲染到 textbox，并对关键行做高亮：
        - 带宽判定行：蓝色
        - delay 列表：正/负/零分色
        - 置信度摘要：高/中/低分色
        - ratio_total / 截幅结论：OK 绿色，疑似填充/截幅 橙色
        """
        self._ensure_text_tags(ctk_textbox)
        lines = msg.splitlines()
        if len(lines) > MAX_RENDER_LINES:
            # 避免极端长文本导致 UI 渲染卡顿
            tail = lines[-MAX_RENDER_LINES:]
            lines = [
                f"⚠ 输出过长，已截断显示最后 {MAX_RENDER_LINES} 行（总计 {len(msg.splitlines())} 行）。",
                "",
            ] + tail

        in_delay = False
        for line in lines:
            s = line.strip()

            if s.startswith("带宽判定:"):
                self._insert_line(ctk_textbox, line, "bw")
                continue

            if s.startswith("各通道相对参考的 delay_samples"):
                in_delay = True
                self._insert_line(ctk_textbox, line, "section_hdr")
                continue

            if s.startswith("各通道 delay 置信度摘要"):
                self._insert_line(ctk_textbox, line, "section_hdr")
                continue

            if in_delay and s.startswith("ch") is False and s.startswith("ch0") is False and s.startswith("ch1") is False:
                # delay 区域结束的一个粗略判断：遇到空行或进入其它段落
                if s == "" or s.startswith("数字截幅"):
                    in_delay = False

            # delay 每行：形如 "ch0: +14.5  (0.91 ms)"
            if s.startswith("ch") and ":" in s and ("ms)" in s or "ms）" in s):
                # 取冒号后第一个数的符号
                try:
                    after = s.split(":", 1)[1].strip()
                    num = after.split()[0]  # +14.5
                    if num.startswith("+") and float(num) != 0.0:
                        tag = "delay_pos"
                    elif num.startswith("-") and float(num) != 0.0:
                        tag = "delay_neg"
                    else:
                        tag = "delay_zero"
                    self._insert_line(ctk_textbox, line, tag)
                    continue
                except Exception:
                    pass

            if s.startswith("ch") and ":" in s and "可靠性:" in s:
                try:
                    after = s.split(":", 1)[1].strip()
                    conf = float(after.split()[0])
                    if conf >= CONFIDENCE_OK:
                        tag = "ok"
                    elif conf >= CONFIDENCE_WARN:
                        tag = "warn"
                    else:
                        tag = "conf_low"
                    self._insert_line(ctk_textbox, line, tag)
                    continue
                except Exception:
                    pass

            if "ratio_total=" in s:
                if "未检测到明显数字截幅" in s and "0.0000%" in s:
                    self._insert_line(ctk_textbox, line, "ok")
                elif "疑似填充/丢帧" in s or "短平顶截幅" in s:
                    self._insert_line(ctk_textbox, line, "warn")
                else:
                    self._insert_line(ctk_textbox, line)
                continue

            # 其它“节标题”
            if s.startswith("数字截幅") or s.startswith("分段:") or s.startswith("参考通道:"):
                self._insert_line(ctk_textbox, line, "section_hdr")
                continue

            self._insert_line(ctk_textbox, line)

        if add_end_marker:
            self._insert_line(ctk_textbox, "")
            self._insert_line(ctk_textbox, "END OF OUTPUT", "section_hdr")

    def _set_light_mode(self, enabled: bool):
        """拖动/缩放窗口期间隐藏重绘开销大的 Textbox，减少卡顿。"""
        if enabled == self._in_light_mode:
            return
        self._in_light_mode = enabled

        # 左侧结果框
        if self.result_text is not None and self.result_placeholder is not None:
            try:
                if enabled:
                    self.result_text.grid_remove()
                    self.result_placeholder.grid()
                else:
                    self.result_placeholder.grid_remove()
                    self.result_text.grid()
            except Exception:
                pass

        # 右侧 Log 框
        if self.log_textbox is not None and self.log_placeholder is not None:
            try:
                if enabled:
                    self.log_textbox.pack_forget()
                    self.log_placeholder.pack(fill="both", expand=True, padx=12, pady=(0, 12))
                else:
                    self.log_placeholder.pack_forget()
                    self.log_textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            except Exception:
                pass

        # Matplotlib canvas 在窗口 resize 时开销较大；拖动期间先用占位层替代。
        if self.plot_stack is not None and self.plot_light_placeholder is not None:
            try:
                if enabled:
                    self.plot_stack.grid_remove()
                    self.plot_light_placeholder.grid(row=5, column=0, sticky="nsew")
                else:
                    self.plot_light_placeholder.grid_remove()
                    self.plot_stack.grid()
                    if HAS_MPL:
                        self.root.after_idle(self._refresh_embedded_plot_view)
            except Exception:
                pass

    def _on_root_configure(self, event):
        # 只处理 root 的尺寸变化，避免子控件触发过多
        if event.widget is not self.root:
            return
        # resize 高频触发：进入轻量模式 + debounce 恢复
        self._set_light_mode(True)
        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.root.after(180, self._on_resize_idle)

    def _on_resize_idle(self):
        self._resize_after_id = None
        # 如果正在拖动 sash，就先不退出轻量模式
        if self._paned_dragging:
            self._resize_after_id = self.root.after(180, self._on_resize_idle)
            return
        self._set_light_mode(False)

    def _build_ui(self):
        # 主区域使用普通 Frame，避免窗口变高时出现大片空白；
        # 需要滚动时由结果框/Log 框自身提供滚动即可。
        main = ctk.CTkFrame(self.main_area, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=16)

        # 标题行：左侧标题 + 右侧蓝色「README」与「Log」（按钮样式，增加辨识度）
        title_f = ctk.CTkFrame(main, fg_color="transparent")
        title_f.pack(fill="x", pady=(0, 10))
        left_f = ctk.CTkFrame(title_f, fg_color="transparent")
        left_f.pack(side="left")
        title_row = ctk.CTkFrame(left_f, fg_color="transparent")
        title_row.pack(anchor="w")
        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            ctk.CTkLabel(title_row, image=self.logo_image, text="", width=40, height=40).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_row, text=APP_NAME, font=ctk.CTkFont(size=22, weight="bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(left_f, text="GCC-PHAT 多段统计, 以选定通道为参考", font=ctk.CTkFont(size=12), text_color=TEXT_SEC).pack(anchor="w")
        right_f = ctk.CTkFrame(title_f, fg_color="transparent")
        right_f.pack(side="right")
        self.version_badge = ctk.CTkLabel(
            right_f,
            text=f"Version {APP_VERSION}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ACCENT,
            fg_color="#eaf3ff",
            corner_radius=14,
            padx=12,
            pady=5,
        )
        self.version_badge.pack(side="right", padx=(8, 0))
        self.btn_history = ctk.CTkButton(
            right_f,
            text="Log",
            command=self._toggle_history_panel,
            width=64,
            height=30,
            corner_radius=BTN_RADIUS,
            fg_color=INPUT_BG,
            hover_color="#e0e0e5",
            border_width=1,
            border_color="#d1d1d6",
            text_color=TEXT,
            font=ctk.CTkFont(size=13),
        )
        self.btn_history.pack(side="right", padx=(8, 0))
        self.btn_chart = ctk.CTkButton(
            right_f,
            text="Chart",
            command=self._open_chart_window,
            width=64,
            height=30,
            corner_radius=BTN_RADIUS,
            fg_color=INPUT_BG,
            hover_color="#e0e0e5",
            border_width=1,
            border_color="#d1d1d6",
            text_color=TEXT,
            font=ctk.CTkFont(size=13),
        )
        self.btn_chart.pack(side="right", padx=(8, 0))
        self.btn_readme = ctk.CTkButton(
            right_f,
            text="README",
            command=self._show_readme_window,
            width=84,
            height=30,
            corner_radius=BTN_RADIUS,
            fg_color="transparent",
            hover_color="#e0e0e5",
            border_width=0,
            text_color=ACCENT,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_readme.pack(side="right")

        # ——— 卡片 1：输入文件（圆角） ———
        card1 = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=CORNER_RADIUS, border_width=0)
        card1.pack(fill="x", pady=(0, 8))
        inner1 = ctk.CTkFrame(card1, fg_color="transparent")
        inner1.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(inner1, text="输入文件", font=ctk.CTkFont(size=13), text_color=TEXT_SEC).pack(anchor="w", pady=(0, 6))
        row1 = ctk.CTkFrame(inner1, fg_color="transparent")
        row1.pack(fill="x")
        self.entry_path = ctk.CTkEntry(
            row1, textvariable=self.file_path, placeholder_text="选择 WAV 或 PCM 文件",
            height=36, corner_radius=INPUT_RADIUS, fg_color=INPUT_BG, border_width=0,
            font=ctk.CTkFont(size=13),
        )
        self.entry_path.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.btn_browse = ctk.CTkButton(
            row1, text="选择文件", command=self._on_browse, width=96, height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=BTN_RADIUS,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_browse.pack(side="right")

        ctk.CTkLabel(inner1, text="格式", font=ctk.CTkFont(size=13), text_color=TEXT_SEC).pack(anchor="w", pady=(10, 4))
        fmt_f = ctk.CTkFrame(inner1, fg_color="transparent")
        fmt_f.pack(fill="x")
        ctk.CTkRadioButton(
            fmt_f, text="WAV (自动识别采样率与通道数)", variable=self.is_wav, value=True,
            command=self._on_format_change, font=ctk.CTkFont(size=13), fg_color=ACCENT,
        ).pack(anchor="w")
        ctk.CTkRadioButton(
            fmt_f, text="PCM (需填写下方参数)", variable=self.is_wav, value=False,
            command=self._on_format_change, font=ctk.CTkFont(size=13), fg_color=ACCENT,
        ).pack(anchor="w")

        # PCM 参数卡片（圆角，与基准/分段卡片同风格：标签在上、圆角输入在下）
        self.pcm_frame = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=CORNER_RADIUS, border_width=0)
        inner_pcm = ctk.CTkFrame(self.pcm_frame, fg_color="transparent")
        inner_pcm.pack(fill="x", padx=12, pady=12)
        ctk.CTkLabel(inner_pcm, text="PCM 参数", font=ctk.CTkFont(size=13), text_color=TEXT_SEC).pack(anchor="w", pady=(0, 6))
        row_pcm = ctk.CTkFrame(inner_pcm, fg_color="transparent")
        row_pcm.pack(fill="x")
        for label, var, w in [("采样率 (Hz)", self.pcm_sr, 100), ("位深", self.pcm_bits, 70), ("通道数", self.pcm_ch, 70)]:
            col = ctk.CTkFrame(row_pcm, fg_color="transparent")
            col.pack(side="left", padx=(0, 24))
            ctk.CTkLabel(col, text=label, font=ctk.CTkFont(size=12), text_color=TEXT_SEC).pack(anchor="w")
            entry = ctk.CTkEntry(col, textvariable=var, width=w, height=36, corner_radius=INPUT_RADIUS, fg_color=INPUT_BG, border_width=0)
            entry.pack(anchor="w", pady=(6, 0))
            if var == self.pcm_ch:
                self.entry_pcm_ch = entry
        self.pcm_ch.trace_add("write", lambda *a: self._update_ref_combo())

        # ——— 卡片 2：基准与分段（圆角） ———
        self.ref_frame = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=CORNER_RADIUS, border_width=0)
        self.ref_frame.pack(fill="x", pady=(0, 8))
        inner2 = ctk.CTkFrame(self.ref_frame, fg_color="transparent")
        inner2.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(inner2, text="基准信号", font=ctk.CTkFont(size=13), text_color=TEXT_SEC).pack(anchor="w", pady=(0, 6))
        row_ref = ctk.CTkFrame(inner2, fg_color="transparent")
        row_ref.pack(fill="x", pady=(0, 10))
        col_ref = ctk.CTkFrame(row_ref, fg_color="transparent")
        col_ref.pack(side="left")
        ctk.CTkLabel(col_ref, text="参考通道", font=ctk.CTkFont(size=12), text_color=TEXT_SEC).pack(anchor="w")
        self.ref_btn_frame = ctk.CTkFrame(col_ref, fg_color="transparent")
        self.ref_btn_frame.pack(anchor="w", pady=(6, 0))
        self._build_ref_channel_buttons(1)

        ctk.CTkLabel(inner2, text="分段参数(秒)", font=ctk.CTkFont(size=13), text_color=TEXT_SEC).pack(anchor="w", pady=(0, 6))
        row_seg = ctk.CTkFrame(inner2, fg_color="transparent")
        row_seg.pack(fill="x")
        for label, var in [("每段", self.segment_s), ("步长", self.step_s), ("起始", self.start_s)]:
            col = ctk.CTkFrame(row_seg, fg_color="transparent")
            col.pack(side="left", padx=(0, 24))
            ctk.CTkLabel(col, text=label, font=ctk.CTkFont(size=12), text_color=TEXT_SEC).pack(anchor="w")
            ctk.CTkEntry(col, textvariable=var, width=80, height=36, corner_radius=INPUT_RADIUS, fg_color=INPUT_BG, border_width=0).pack(anchor="w", pady=(6, 0))

        # 计算按钮（蓝色圆角、全宽）
        btn_f = ctk.CTkFrame(main, fg_color="transparent")
        btn_f.pack(fill="x", pady=(6, 10))
        self.run_btn = ctk.CTkButton(
            btn_f, text="计算 Delay", command=self._on_run, height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=BTN_RADIUS,
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.run_btn.pack(fill="x")
        self.btn_export_report = ctk.CTkButton(
            btn_f,
            text="导出报告图",
            command=self._export_report_image,
            height=38,
            fg_color=INPUT_BG,
            hover_color="#e8e8ec",
            border_width=1,
            border_color="#d1d1d6",
            text_color=TEXT,
            corner_radius=BTN_RADIUS,
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
        )
        self.btn_export_report.pack(fill="x", pady=(8, 0))

        # ——— 卡片 3：结果（圆角，自适应窗口高度） ———
        card3 = ctk.CTkFrame(main, fg_color=CARD_BG, corner_radius=CORNER_RADIUS, border_width=0)
        card3.pack(fill="both", expand=True, pady=(0, 0))
        inner3 = ctk.CTkFrame(card3, fg_color="transparent")
        inner3.pack(fill="both", expand=True, padx=12, pady=12)

        # 用 grid 让结果区随窗口自适应拉伸，同时保证图表区域有可读的最小高度
        inner3.grid_columnconfigure(0, weight=1)
        inner3.grid_rowconfigure(1, weight=0, minsize=220)
        inner3.grid_rowconfigure(5, weight=1, minsize=420)

        ctk.CTkLabel(
            inner3,
            text="结果(各通道相对参考的 DELAY_SAMPLES)",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SEC,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.result_text = ctk.CTkTextbox(
            inner3,
            corner_radius=INPUT_RADIUS,
            fg_color=INPUT_BG,
            border_width=0,
            height=220,
            # Segoe UI 兼顾中文与 emoji；并让控件随 grid 自适应高度
            font=ctk.CTkFont(family="Segoe UI", size=12),
            wrap="word",
        )
        self.result_text.grid(row=1, column=0, sticky="nsew")

        # resize/拖动期间的轻量占位
        self.result_placeholder = ctk.CTkLabel(
            inner3,
            text="调整窗口中…",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC,
        )
        self.result_placeholder.grid(row=1, column=0, sticky="nsew")
        self.result_placeholder.grid_remove()

        ctk.CTkLabel(
            inner3,
            text="Charts (Delay Drift / Confidence)",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SEC,
        ).grid(row=2, column=0, sticky="w", pady=(12, 6))

        self.plot_channel_frame = ctk.CTkFrame(inner3, fg_color="transparent")
        self.plot_channel_frame.grid(row=3, column=0, sticky="w", pady=(0, 8))
        self._build_plot_channel_buttons(1, ref_ch=0)

        self.plot_view_frame = ctk.CTkFrame(inner3, fg_color="transparent")
        self.plot_view_frame.grid(row=4, column=0, sticky="w", pady=(0, 8))
        self._build_plot_view_buttons()

        self.plot_stack = ctk.CTkFrame(inner3, fg_color="transparent", height=420)
        self.plot_stack.grid(row=5, column=0, sticky="nsew")
        self.plot_stack.grid_columnconfigure(0, weight=1)
        self.plot_stack.grid_rowconfigure(0, weight=1)

        self.plot_light_placeholder = ctk.CTkFrame(inner3, fg_color=INPUT_BG, corner_radius=INPUT_RADIUS, height=420)
        ctk.CTkLabel(
            self.plot_light_placeholder,
            text="调整窗口中…",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC,
        ).pack(fill="both", expand=True, padx=12, pady=12)
        self.plot_light_placeholder.grid(row=5, column=0, sticky="nsew")
        self.plot_light_placeholder.grid_remove()

        self.delay_plot_host = ctk.CTkFrame(self.plot_stack, fg_color=INPUT_BG, corner_radius=INPUT_RADIUS)
        self.delay_plot_host.grid(row=0, column=0, sticky="nsew")
        self.conf_plot_host = ctk.CTkFrame(self.plot_stack, fg_color=INPUT_BG, corner_radius=INPUT_RADIUS)
        self.conf_plot_host.grid(row=0, column=0, sticky="nsew")

        self._init_plot_widgets()
        self._show_plot_host(self.plot_view.get())
        self._refresh_plot_views()

        self._on_format_change()

    def _build_plot_channel_buttons(self, n, ref_ch=0):
        for w in self.plot_channel_frame.winfo_children():
            w.destroy()
        self.plot_channel_buttons.clear()
        n = max(1, min(int(n), 24))
        self._normalize_plot_channel_selection(n)

        items = [("all", "All")]
        items.extend((str(i), f"通道 {i}") for i in range(n))
        for idx, (value, label) in enumerate(items):
            is_selected = self._is_plot_channel_selected(value, n)
            is_ref = value == str(ref_ch)
            suffix = "*" if is_ref else ""
            btn = ctk.CTkButton(
                self.plot_channel_frame,
                text=f"{label}{suffix}",
                width=72 if value == "all" else 80,
                height=32,
                corner_radius=BTN_RADIUS,
                font=ctk.CTkFont(size=12),
                fg_color=INPUT_BG,
                text_color=TEXT,
                hover_color="#e8e8ec",
                command=(lambda v=value: self._on_plot_channel_click(v)),
            )
            btn.grid(row=idx // 7, column=idx % 7, padx=(0, 8), pady=(0, 6), sticky="w")
            self.plot_channel_buttons.append((value, btn))
            self._apply_plot_channel_button_style(btn, value, is_selected)

    def _channel_plot_color(self, channel_value):
        try:
            return PLOT_COLORS[int(channel_value) % len(PLOT_COLORS)]
        except Exception:
            return ACCENT

    def _apply_plot_channel_button_style(self, btn, value, is_selected):
        if value == "all":
            if is_selected:
                btn.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT_HOVER)
            else:
                btn.configure(fg_color=INPUT_BG, text_color=TEXT, hover_color="#e8e8ec")
            return

        channel_color = self._channel_plot_color(value)
        if is_selected:
            btn.configure(fg_color=channel_color, text_color="white", hover_color=channel_color)
        else:
            btn.configure(
                fg_color=INPUT_BG,
                text_color=channel_color,
                hover_color="#e8e8ec",
                border_width=1,
                border_color=channel_color,
            )
            return

        btn.configure(border_width=0, border_color=channel_color)

    def _refresh_plot_channel_buttons_style(self):
        n = self.plot_channel_count
        for value, btn in self.plot_channel_buttons:
            self._apply_plot_channel_button_style(btn, value, self._is_plot_channel_selected(value, n))
        self._refresh_popup_plot_channel_buttons_style()

    def _on_plot_channel_click(self, value):
        self._toggle_plot_channel_selection(value)
        self._refresh_plot_channel_buttons_style()
        self._refresh_plot_views()

    def _normalize_plot_channel_selection(self, n):
        self.plot_channel_count = max(1, int(n))
        valid = {str(i) for i in range(self.plot_channel_count)}
        self.plot_channel_selection = {value for value in self.plot_channel_selection if value in valid}

    def _is_plot_channel_selected(self, value, n=None):
        if n is None:
            n = self.plot_channel_count
        if value == "all":
            return len(self.plot_channel_selection) == max(1, int(n))
        return value in self.plot_channel_selection

    def _toggle_plot_channel_selection(self, value):
        self._normalize_plot_channel_selection(self.plot_channel_count)
        valid = {str(i) for i in range(self.plot_channel_count)}
        if value == "all":
            if len(self.plot_channel_selection) == len(valid):
                self.plot_channel_selection = set()
            else:
                self.plot_channel_selection = set(valid)
            return

        if value in self.plot_channel_selection:
            self.plot_channel_selection.remove(value)
        else:
            self.plot_channel_selection.add(value)

    def _build_plot_view_buttons(self):
        for w in self.plot_view_frame.winfo_children():
            w.destroy()
        self.plot_view_buttons.clear()
        for idx, (value, label) in enumerate((("delay", "Delay Drift"), ("confidence", "Confidence"))):
            is_selected = self.plot_view.get() == value
            btn = ctk.CTkButton(
                self.plot_view_frame,
                text=label,
                width=104,
                height=32,
                corner_radius=BTN_RADIUS,
                font=ctk.CTkFont(size=12),
                fg_color=ACCENT if is_selected else INPUT_BG,
                text_color="white" if is_selected else TEXT,
                hover_color=ACCENT_HOVER if is_selected else "#e8e8ec",
                command=(lambda v=value: self._on_plot_view_click(v)),
            )
            btn.grid(row=0, column=idx, padx=(0, 8), pady=(0, 0), sticky="w")
            self.plot_view_buttons.append((value, btn))

    def _refresh_plot_view_buttons_style(self):
        cur = self.plot_view.get()
        for value, btn in self.plot_view_buttons:
            if value == cur:
                btn.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT_HOVER)
            else:
                btn.configure(fg_color=INPUT_BG, text_color=TEXT, hover_color="#e8e8ec")

    def _show_plot_host(self, view_name):
        if view_name == "confidence":
            self.conf_plot_host.tkraise()
        else:
            self.delay_plot_host.tkraise()

    def _on_plot_view_click(self, value):
        self.plot_view.set(value)
        self._refresh_plot_view_buttons_style()
        self._show_plot_host(value)
        self._refresh_embedded_plot_view()

    def _init_plot_widgets(self):
        if HAS_MPL:
            self.delay_fig = Figure(figsize=(7.2, 4.2), dpi=100, facecolor=INPUT_BG)
            self.delay_ax = self.delay_fig.add_subplot(111)
            self.delay_canvas = FigureCanvasTkAgg(self.delay_fig, master=self.delay_plot_host)
            self.delay_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

            self.conf_fig = Figure(figsize=(7.2, 4.2), dpi=100, facecolor=INPUT_BG)
            self.conf_ax = self.conf_fig.add_subplot(111)
            self.conf_canvas = FigureCanvasTkAgg(self.conf_fig, master=self.conf_plot_host)
            self.conf_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
            return

        self.delay_fallback = ctk.CTkLabel(
            self.delay_plot_host,
            text="matplotlib is not available, so the delay drift chart cannot be shown.\nInstall the dependencies from requirements_ui.txt and try again.",
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
        )
        self.delay_fallback.pack(fill="both", expand=True, padx=12, pady=12)
        self.conf_fallback = ctk.CTkLabel(
            self.conf_plot_host,
            text="matplotlib is not available, so the confidence chart cannot be shown.\nInstall the dependencies from requirements_ui.txt and try again.",
            text_color=TEXT_SEC,
            font=ctk.CTkFont(size=12),
        )
        self.conf_fallback.pack(fill="both", expand=True, padx=12, pady=12)

    def _draw_canvas_throttled(self, canvas, delay_ms=33):
        if canvas is None:
            return
        key = id(canvas)
        if key in self._canvas_draw_after_ids:
            return

        try:
            widget = canvas.get_tk_widget()
        except Exception:
            canvas.draw_idle()
            return

        def draw_later():
            self._canvas_draw_after_ids.pop(key, None)
            try:
                if widget.winfo_exists():
                    canvas.draw_idle()
            except Exception:
                pass

        try:
            self._canvas_draw_after_ids[key] = widget.after(delay_ms, draw_later)
        except Exception:
            canvas.draw_idle()

    def _style_plot_axis(self, ax, title, ylabel):
        ax.clear()
        ax.set_title(title, fontsize=11, color=TEXT)
        ax.set_xlabel("Time (s)", fontsize=10, color=TEXT_SEC)
        ax.set_ylabel(ylabel, fontsize=10, color=TEXT_SEC)
        ax.set_facecolor("#fbfbfc")
        ax.grid(True, color="#e5e5ea", linewidth=0.8, alpha=0.9)
        ax.tick_params(axis="both", colors=TEXT_SEC, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#d1d1d6")

    def _draw_plot_placeholder(self, ax, canvas, title, ylabel, message, ylim=None):
        self._style_plot_axis(ax, title, ylabel)
        if ylim is not None:
            ax.set_ylim(*ylim)
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes, color=TEXT_SEC, fontsize=11)
        canvas.draw_idle()

    def _plot_selected_channels(self):
        if not self.latest_plot_data:
            return []
        n_ch = len(self.latest_plot_data["per_channel_delays"])
        self._normalize_plot_channel_selection(n_ch)
        selected = []
        for value in sorted(self.plot_channel_selection, key=lambda item: int(item)):
            try:
                ch = int(value)
            except ValueError:
                continue
            if 0 <= ch < n_ch:
                selected.append(ch)
        return selected

    def _render_delay_plot(self, ax, canvas):
        if not self.latest_plot_data or not self.latest_plot_data.get("times_s"):
            self._draw_plot_placeholder(
                ax,
                canvas,
                "Delay Drift",
                "delay_samples",
                "Run an analysis to display the delay drift over time.",
            )
            return

        times_s = self.latest_plot_data["times_s"]
        per_delays = self.latest_plot_data["per_channel_delays"]
        selected_channels = self._plot_selected_channels()
        if not selected_channels:
            self._draw_plot_placeholder(
                ax,
                canvas,
                "Delay Drift",
                "delay_samples",
                "No channels selected. Click All or choose one or more channels above.",
            )
            return

        self._style_plot_axis(ax, "Delay Drift", "delay_samples")
        for ch in selected_channels:
            color = self._channel_plot_color(ch)
            y = per_delays[ch]
            ax.plot(times_s, y, marker="o", markersize=4, linewidth=1.6, color=color, label=f"ch{ch}")
            if y:
                median = sorted(y)[len(y) // 2]
                ax.axhline(median, color=color, linestyle="--", linewidth=1.0, alpha=0.35)
        if selected_channels:
            ax.legend(loc="best", fontsize=9, frameon=False)
        canvas.draw_idle()

    def _render_conf_plot(self, ax, canvas):
        if not self.latest_plot_data or not self.latest_plot_data.get("times_s"):
            self._draw_plot_placeholder(
                ax,
                canvas,
                "Confidence (|rho|)",
                "|rho|",
                "Run an analysis to display the normalized correlation over time.",
                ylim=(0.0, 1.05),
            )
            return

        times_s = self.latest_plot_data["times_s"]
        per_conf = self.latest_plot_data["per_channel_confidences"]
        selected_channels = self._plot_selected_channels()
        if not selected_channels:
            self._draw_plot_placeholder(
                ax,
                canvas,
                "Confidence (|rho|)",
                "|rho|",
                "No channels selected. Click All or choose one or more channels above.",
                ylim=(0.0, 1.05),
            )
            return

        self._style_plot_axis(ax, "Confidence (normalized correlation |rho|)", "|rho|")
        ax.set_ylim(0.0, 1.05)
        ax.axhline(CONFIDENCE_OK, color="#34C759", linestyle="--", linewidth=1.0, alpha=0.6)
        ax.axhline(CONFIDENCE_WARN, color="#FF9500", linestyle="--", linewidth=1.0, alpha=0.6)
        for ch in selected_channels:
            color = self._channel_plot_color(ch)
            y = per_conf[ch]
            ax.plot(times_s, y, marker="o", markersize=4, linewidth=1.6, color=color, label=f"ch{ch}")
        if selected_channels:
            ax.legend(loc="best", fontsize=9, frameon=False)
        canvas.draw_idle()

    def _refresh_plot_views(self):
        if not HAS_MPL:
            return
        self._refresh_embedded_plot_view()
        self._refresh_popup_plot_views()

    def _refresh_embedded_plot_view(self):
        if not HAS_MPL or self._in_light_mode:
            return
        if self.plot_view.get() == "confidence":
            self._render_conf_plot(self.conf_ax, self.conf_canvas)
        else:
            self._render_delay_plot(self.delay_ax, self.delay_canvas)

    def _set_plot_data(self, details, ref_ch):
        self.latest_plot_data = {
            "times_s": list(details.get("times_s", [])),
            "per_channel_delays": [list(x) for x in details.get("per_channel_delays", [])],
            "per_channel_confidences": [list(x) for x in details.get("per_channel_confidences", [])],
            "ref_ch": int(ref_ch),
        }
        n_ch = len(self.latest_plot_data["per_channel_delays"])
        self._normalize_plot_channel_selection(n_ch)
        if not self.plot_channel_selection:
            self.plot_channel_selection = {str(i) for i in range(n_ch)}
        self._build_plot_channel_buttons(n_ch, ref_ch=ref_ch)
        self._refresh_plot_channel_buttons_style()
        self._refresh_plot_views()

    def _clear_plot_data(self):
        self.latest_plot_data = None
        self.plot_channel_selection = set()
        self._normalize_plot_channel_selection(1)
        self._build_plot_channel_buttons(1, ref_ch=0)
        self._refresh_plot_channel_buttons_style()
        self._refresh_plot_views()

    def _build_popup_plot_channel_buttons(self, host, n, ref_ch=0):
        for w in host.winfo_children():
            w.destroy()
        self.popup_plot_channel_buttons.clear()
        self._normalize_plot_channel_selection(n)
        items = [("all", "All")]
        items.extend((str(i), f"Ch {i}{'*' if i == ref_ch else ''}") for i in range(max(1, n)))
        for idx, (value, label) in enumerate(items):
            is_selected = self._is_plot_channel_selected(value, n)
            btn = ctk.CTkButton(
                host,
                text=label,
                width=84 if value == "all" else 92,
                height=32,
                corner_radius=BTN_RADIUS,
                font=ctk.CTkFont(size=12),
                fg_color=INPUT_BG,
                text_color=TEXT,
                hover_color="#e8e8ec",
                command=(lambda v=value: self._on_plot_channel_click(v)),
            )
            btn.grid(row=idx // 8, column=idx % 8, padx=(0, 8), pady=(0, 6), sticky="w")
            self.popup_plot_channel_buttons.append((value, btn))
            self._apply_plot_channel_button_style(btn, value, is_selected)

    def _refresh_popup_plot_channel_buttons_style(self):
        n = self.plot_channel_count
        for value, btn in self.popup_plot_channel_buttons:
            self._apply_plot_channel_button_style(btn, value, self._is_plot_channel_selected(value, n))

    def _refresh_popup_plot_views(self):
        if not HAS_MPL or self.chart_window is None or not self.chart_window.winfo_exists():
            return
        if self._selected_popup_plot_view() == "confidence":
            self._render_conf_plot(self.popup_conf_ax, self.popup_conf_canvas)
        else:
            self._render_delay_plot(self.popup_delay_ax, self.popup_delay_canvas)
        self._reset_popup_interaction_rectangles()

    def _selected_popup_plot_view(self):
        try:
            if self.popup_notebook is not None and self.popup_notebook.index("current") == 1:
                return "confidence"
        except Exception:
            pass
        return "delay"

    def _current_plot_bounds(self, kind):
        if not self.latest_plot_data or not self.latest_plot_data.get("times_s"):
            return None

        times_s = list(self.latest_plot_data["times_s"])
        if not times_s:
            return None

        selected_channels = self._plot_selected_channels()
        x_min = min(times_s)
        x_max = max(times_s)
        if x_min == x_max:
            x_min -= 1.0
            x_max += 1.0
        x_pad = max((x_max - x_min) * 0.03, 1.0)

        if kind == "delay":
            series = []
            for ch in selected_channels:
                series.extend(self.latest_plot_data["per_channel_delays"][ch])
            if not series:
                series = [0.0]
            y_min = min(series)
            y_max = max(series)
            if y_min == y_max:
                y_min -= 1.0
                y_max += 1.0
            y_pad = max((y_max - y_min) * 0.08, 1.0)
            return (x_min - x_pad, x_max + x_pad), (y_min - y_pad, y_max + y_pad)

        return (x_min - x_pad, x_max + x_pad), (0.0, 1.05)

    def _reset_axis_view(self, ax, kind, canvas):
        bounds = self._current_plot_bounds(kind)
        if bounds is None:
            return
        xlim, ylim = bounds
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        canvas.draw_idle()

    def _reset_popup_interaction_rectangles(self):
        for state in self.popup_plot_interactions.values():
            rect = state.get("rect")
            if rect is not None:
                try:
                    rect.remove()
                except Exception:
                    pass
                state["rect"] = None

    def _set_popup_status(self, text):
        if self.popup_status_var is not None:
            try:
                self.popup_status_var.set(text)
            except Exception:
                pass

    def _sync_popup_status(self):
        if self.chart_window is None or not self.chart_window.winfo_exists():
            return

        status = "Mode: Normal | Double-click: Reset | Left drag: Zoom | Middle drag: Pan | Wheel: Zoom"
        for state in self.popup_plot_interactions.values():
            toolbar = state.get("toolbar")
            toolbar_mode = ""
            try:
                toolbar_mode = (getattr(toolbar, "mode", "") or "").strip()
            except Exception:
                toolbar_mode = ""

            if toolbar_mode:
                if "PAN" in toolbar_mode.upper():
                    status = "Mode: Pan (toolbar)"
                elif "ZOOM" in toolbar_mode.upper():
                    status = "Mode: Zoom (toolbar)"
                else:
                    status = f"Mode: {toolbar_mode}"
                break

            mode = state.get("mode")
            if mode == "pan":
                status = "Mode: Pan"
                break
            if mode == "zoom":
                status = "Mode: Zoom"
                break

        self._set_popup_status(status)
        try:
            self.chart_window.after(120, self._sync_popup_status)
        except Exception:
            pass

    def _install_direct_plot_interactions(self, figure, canvas, ax, kind, toolbar):
        state = {
            "kind": kind,
            "canvas": canvas,
            "ax": ax,
            "toolbar": toolbar,
            "mode": None,
            "press": None,
            "rect": None,
        }
        self.popup_plot_interactions[ax] = state

        def _toolbar_active():
            try:
                return bool(getattr(toolbar, "mode", ""))
            except Exception:
                return False

        def _on_press(event):
            if event.inaxes is not ax:
                return
            if _toolbar_active():
                return
            if getattr(event, "dblclick", False):
                state["mode"] = None
                state["press"] = None
                self._reset_axis_view(ax, kind, canvas)
                self._set_popup_status("Mode: Normal")
                return
            if event.button == 1 and event.xdata is not None and event.ydata is not None:
                state["mode"] = "zoom"
                state["press"] = {
                    "x": float(event.xdata),
                    "y": float(event.ydata),
                }
                rect = state.get("rect")
                if rect is not None:
                    try:
                        rect.remove()
                    except Exception:
                        pass
                rect = Rectangle(
                    (event.xdata, event.ydata),
                    0.0,
                    0.0,
                    fill=False,
                    edgecolor=ACCENT,
                    linewidth=1.2,
                    linestyle="--",
                    alpha=0.9,
                )
                ax.add_patch(rect)
                state["rect"] = rect
                self._set_popup_status("Mode: Zoom")
                canvas.draw_idle()
            elif event.button == 2 and event.xdata is not None and event.ydata is not None:
                state["mode"] = "pan"
                state["press"] = {
                    "x": float(event.xdata),
                    "y": float(event.ydata),
                    "xlim": ax.get_xlim(),
                    "ylim": ax.get_ylim(),
                }
                self._set_popup_status("Mode: Pan")

        def _on_motion(event):
            if event.inaxes is not ax:
                return
            if _toolbar_active():
                return
            press = state.get("press")
            if not press:
                return

            if state.get("mode") == "pan" and event.xdata is not None and event.ydata is not None:
                dx = press["x"] - float(event.xdata)
                dy = press["y"] - float(event.ydata)
                xlim = press["xlim"]
                ylim = press["ylim"]
                ax.set_xlim(xlim[0] + dx, xlim[1] + dx)
                ax.set_ylim(ylim[0] + dy, ylim[1] + dy)
                self._draw_canvas_throttled(canvas)
            elif state.get("mode") == "zoom" and event.xdata is not None and event.ydata is not None:
                rect = state.get("rect")
                if rect is None:
                    return
                rect.set_x(min(press["x"], float(event.xdata)))
                rect.set_y(min(press["y"], float(event.ydata)))
                rect.set_width(abs(float(event.xdata) - press["x"]))
                rect.set_height(abs(float(event.ydata) - press["y"]))
                self._draw_canvas_throttled(canvas)

        def _on_release(event):
            if _toolbar_active():
                state["mode"] = None
                state["press"] = None
                self._set_popup_status("Mode: Normal")
                return
            press = state.get("press")
            if not press:
                return

            if state.get("mode") == "zoom":
                rect = state.get("rect")
                if rect is not None:
                    try:
                        rect.remove()
                    except Exception:
                        pass
                    state["rect"] = None
                if event.inaxes is ax and event.xdata is not None and event.ydata is not None:
                    x0, x1 = press["x"], float(event.xdata)
                    y0, y1 = press["y"], float(event.ydata)
                    if abs(x1 - x0) > 1e-6 and abs(y1 - y0) > 1e-6:
                        ax.set_xlim(min(x0, x1), max(x0, x1))
                        ax.set_ylim(min(y0, y1), max(y0, y1))
            state["mode"] = None
            state["press"] = None
            self._set_popup_status("Mode: Normal")
            canvas.draw_idle()

        figure.canvas.mpl_connect("button_press_event", _on_press)
        figure.canvas.mpl_connect("motion_notify_event", _on_motion)
        figure.canvas.mpl_connect("button_release_event", _on_release)

    def _install_scroll_zoom(self, figure, canvas):
        def _on_scroll(event):
            ax = event.inaxes
            if ax is None:
                return

            try:
                step = event.step
            except Exception:
                step = 1 if getattr(event, "button", None) == "up" else -1

            scale = 1 / 1.15 if step > 0 else 1.15
            x_min, x_max = ax.get_xlim()
            y_min, y_max = ax.get_ylim()
            xdata = event.xdata if event.xdata is not None else (x_min + x_max) * 0.5
            ydata = event.ydata if event.ydata is not None else (y_min + y_max) * 0.5

            new_x_min = xdata - (xdata - x_min) * scale
            new_x_max = xdata + (x_max - xdata) * scale
            new_y_min = ydata - (ydata - y_min) * scale
            new_y_max = ydata + (y_max - ydata) * scale

            ax.set_xlim(new_x_min, new_x_max)
            ax.set_ylim(new_y_min, new_y_max)
            self._draw_canvas_throttled(canvas)

        figure.canvas.mpl_connect("scroll_event", _on_scroll)

    def _open_chart_window(self):
        if not HAS_MPL:
            messagebox.showwarning("Prompt", "matplotlib is not available, so the chart window cannot be shown.")
            return

        if self.chart_window is not None and self.chart_window.winfo_exists():
            self.chart_window.deiconify()
            self.chart_window.lift()
            self._refresh_popup_plot_views()
            return

        win = ctk.CTkToplevel(self.root)
        win.title(f"{APP_NAME} Charts")
        self._apply_window_icon(win)
        win.geometry("1180x900")
        win.minsize(980, 760)
        win.transient(self.root)
        self.chart_window = win

        def _on_close():
            try:
                win.destroy()
            finally:
                self.chart_window = None
                self.popup_notebook = None
                self.popup_plot_channel_buttons = []
                self.popup_plot_interactions = {}
                self.popup_status_var = None
                self.popup_delay_fig = None
                self.popup_delay_ax = None
                self.popup_delay_canvas = None
                self.popup_delay_toolbar = None
                self.popup_conf_fig = None
                self.popup_conf_ax = None
                self.popup_conf_canvas = None
                self.popup_conf_toolbar = None

        win.protocol("WM_DELETE_WINDOW", _on_close)

        outer = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=CORNER_RADIUS)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            outer,
            text="Delay Drift / Confidence Charts",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", padx=12, pady=(12, 8))

        popup_btns = ctk.CTkFrame(outer, fg_color="transparent")
        popup_btns.pack(fill="x", padx=12, pady=(0, 8))
        n_ch = len(self.latest_plot_data["per_channel_delays"]) if self.latest_plot_data else 1
        ref_ch = self.latest_plot_data.get("ref_ch", 0) if self.latest_plot_data else 0
        self._build_popup_plot_channel_buttons(popup_btns, n_ch, ref_ch)

        hint = ctk.CTkLabel(
            outer,
            text="Note: the upper chart shows delay drift and the lower chart shows normalized correlation |rho|. Switch channels to inspect them.",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC,
        )
        hint.pack(anchor="w", padx=12, pady=(0, 8))

        tabs_host = ctk.CTkFrame(outer, fg_color="transparent")
        tabs_host.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        style = ttk.Style(win)
        try:
            style.theme_use("default")
        except Exception:
            pass
        style.configure("DelayCharts.TNotebook", background=BG, borderwidth=0)
        style.configure("DelayCharts.TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10))

        notebook = ttk.Notebook(tabs_host, style="DelayCharts.TNotebook")
        notebook.pack(fill="both", expand=True)
        self.popup_notebook = notebook

        delay_tab = ctk.CTkFrame(notebook, fg_color=CARD_BG, corner_radius=0)
        conf_tab = ctk.CTkFrame(notebook, fg_color=CARD_BG, corner_radius=0)
        notebook.add(delay_tab, text="Delay Drift")
        notebook.add(conf_tab, text="Confidence")

        delay_host = ctk.CTkFrame(delay_tab, fg_color=INPUT_BG, corner_radius=INPUT_RADIUS)
        delay_host.pack(fill="both", expand=True, padx=4, pady=4)
        conf_host = ctk.CTkFrame(conf_tab, fg_color=INPUT_BG, corner_radius=INPUT_RADIUS)
        conf_host.pack(fill="both", expand=True, padx=4, pady=4)

        delay_toolbar_host = ctk.CTkFrame(delay_host, fg_color="transparent")
        delay_toolbar_host.pack(fill="x", padx=8, pady=(8, 0))
        delay_canvas_host = ctk.CTkFrame(delay_host, fg_color="transparent")
        delay_canvas_host.pack(fill="both", expand=True, padx=8, pady=8)

        conf_toolbar_host = ctk.CTkFrame(conf_host, fg_color="transparent")
        conf_toolbar_host.pack(fill="x", padx=8, pady=(8, 0))
        conf_canvas_host = ctk.CTkFrame(conf_host, fg_color="transparent")
        conf_canvas_host.pack(fill="both", expand=True, padx=8, pady=8)

        self.popup_delay_fig = Figure(figsize=(9.0, 3.8), dpi=100, facecolor=INPUT_BG)
        self.popup_delay_ax = self.popup_delay_fig.add_subplot(111)
        self.popup_delay_canvas = FigureCanvasTkAgg(self.popup_delay_fig, master=delay_canvas_host)
        self.popup_delay_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.popup_delay_toolbar = NavigationToolbar2Tk(self.popup_delay_canvas, delay_toolbar_host, pack_toolbar=False)
        self.popup_delay_toolbar.update()
        self.popup_delay_toolbar.pack(side="left", fill="x")
        self._install_scroll_zoom(self.popup_delay_fig, self.popup_delay_canvas)
        self._install_direct_plot_interactions(
            self.popup_delay_fig,
            self.popup_delay_canvas,
            self.popup_delay_ax,
            "delay",
            self.popup_delay_toolbar,
        )

        self.popup_conf_fig = Figure(figsize=(9.0, 3.8), dpi=100, facecolor=INPUT_BG)
        self.popup_conf_ax = self.popup_conf_fig.add_subplot(111)
        self.popup_conf_canvas = FigureCanvasTkAgg(self.popup_conf_fig, master=conf_canvas_host)
        self.popup_conf_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.popup_conf_toolbar = NavigationToolbar2Tk(self.popup_conf_canvas, conf_toolbar_host, pack_toolbar=False)
        self.popup_conf_toolbar.update()
        self.popup_conf_toolbar.pack(side="left", fill="x")
        self._install_scroll_zoom(self.popup_conf_fig, self.popup_conf_canvas)
        self._install_direct_plot_interactions(
            self.popup_conf_fig,
            self.popup_conf_canvas,
            self.popup_conf_ax,
            "confidence",
            self.popup_conf_toolbar,
        )

        self.popup_status_var = tk.StringVar(value="Mode: Normal | Double-click: Reset | Left drag: Zoom | Middle drag: Pan | Wheel: Zoom")
        status_bar = ctk.CTkLabel(
            outer,
            textvariable=self.popup_status_var,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_SEC,
            anchor="w",
        )
        status_bar.pack(fill="x", padx=12, pady=(0, 10))

        notebook.bind("<<NotebookTabChanged>>", lambda _event: self._refresh_popup_plot_views())
        self._refresh_popup_plot_channel_buttons_style()
        self._refresh_popup_plot_views()
        self._sync_popup_status()

    def _show_readme_window(self):
        """显示一份适合人类阅读的计算说明（不依赖 Markdown 渲染）。"""
        content = (
            f"【{APP_NAME} 计算说明】\n"
            "\n"
            "1. 基本概念\n"
            "   - 工具计算的是各通道相对“参考通道”的时间差。\n"
            "   - 结果以 delay_samples 表示，单位是“采样点数”。\n"
            "   - 如果采样率为 fs（例如 16000 Hz），那么：\n"
            "       delay_time(秒) = delay_samples / fs\n"
            "       delay_time(毫秒) = delay_samples / fs * 1000\n"
            "   - delay_samples > 0：该通道比参考通道“晚到”（滞后）。\n"
            "   - delay_samples < 0：该通道比参考通道“早到”（超前）。\n"
            "\n"
            "2. 单段时延估计（GCC‑PHAT）\n"
            "   - 取一小段音频，记参考通道为 x[n]，待测通道为 y[n]。\n"
            "   - 在频域计算互功率谱：Rxy(k) = X(k) * conj(Y(k))。\n"
            "   - 做 PHAT 加权：只保留相位，幅度全部归一化。\n"
            "   - 反变换回时域得到互相关序列 rxy[τ]。\n"
            "   - 在 ±最大时延范围内（约 ±0.2 秒）寻找 |rxy[τ]| 的最大值，对应的 τ 就是该段的 delay_samples。\n"
            "\n"
            "3. 多段统计（提高稳定性）\n"
            "   - 整段音频会按“每段长度 segment_s”“步长 step_s”“起始时间 start_s”切成多段。\n"
            "   - 每一段都执行一次上面的 GCC‑PHAT，得到这一段的 delay_samples。\n"
            "   - 对同一个通道，在所有有效段上的 delay_samples 取“中位数”，作为最终结果。\n"
            "   - 这样可以减弱个别段静音、噪声或异常导致的偏差，让整体时延更稳定。\n"
            "\n"
            "4. 漂移与置信度视图\n"
            "   - Delay 漂移图：显示每个有效分段上的 delay_samples，可用来观察 delay 是否稳定、是否随时间漂移。\n"
            "   - 置信度图：显示每个有效分段上的 |rho|（归一化相关系数绝对值），越接近 1 说明该段 delay 结果越可靠。\n"
            "   - 若某些分段的 |rho| 长时间偏低，通常表示该段静音较多、噪声较大，或两路信号相关性不足。\n"
            "\n"
            "5. 结果如何用来对齐通道\n"
            "   - 以某一路作为参考通道（例如 ch4），它的 delay 一定是 0。\n"
            "   - 若某通道 delay_samples = -80（fs = 16000），说明它比参考通道早到约 5 ms。\n"
            "   - 对齐到参考通道时，可以在该通道前面补 80 个采样点的延时，让两路信号在时间轴上对齐。\n"
            "\n"
            "6. 其它说明\n"
            "   - WAV 模式下自动读取采样率和通道数；PCM 模式下需要手动填写。\n"
            "   - 当前仅支持 16 bit 线性 PCM；如果参数填写与实际文件不一致，结果会不可靠。\n"
        )

        win = ctk.CTkToplevel(self.root)
        win.title("README")
        self._apply_window_icon(win)
        win.geometry("720x640")
        win.minsize(520, 480)
        win.transient(self.root)

        frame = ctk.CTkFrame(win, fg_color=CARD_BG, corner_radius=CORNER_RADIUS)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            frame, text="README", font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT
        ).pack(anchor="w", pady=(4, 8), padx=12)

        text_box = ctk.CTkTextbox(
            frame,
            fg_color=INPUT_BG,
            border_width=0,
            corner_radius=INPUT_RADIUS,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        text_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        text_box.insert("1.0", content)
        text_box.configure(state="disabled")

        btn_close = ctk.CTkButton(
            frame,
            text="关闭",
            command=win.destroy,
            height=32,
            width=80,
            corner_radius=BTN_RADIUS,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=12),
        )
        btn_close.pack(anchor="e", padx=12, pady=(0, 4))

    def _on_format_change(self):
        if self.is_wav.get():
            self.pcm_frame.pack_forget()
            self._update_ref_from_file()
        else:
            self.pcm_frame.pack(fill="x", pady=(0, 8), before=self.ref_frame)
            self._update_ref_combo()

    def _ref_ch_to_index(self):
        try:
            return int(self.ref_ch.get().strip())
        except ValueError:
            return 0

    # 参考通道按钮每行个数，多通道时自动换行，避免单行挤满
    REF_CHANNEL_COLS = 6

    def _build_ref_channel_buttons(self, n):
        for w in self.ref_btn_frame.winfo_children():
            w.destroy()
        self.ref_ch_buttons.clear()
        n = max(1, min(n, 24))
        cur = self._ref_ch_to_index()
        if cur >= n:
            cur = 0
            self.ref_ch.set("0")
        for i in range(n):
            btn = ctk.CTkButton(
                self.ref_btn_frame, text=f"通道 {i}", width=64, height=36,
                corner_radius=BTN_RADIUS, font=ctk.CTkFont(size=13),
                fg_color=ACCENT if cur == i else INPUT_BG,
                text_color="white" if cur == i else TEXT,
                hover_color=ACCENT_HOVER if cur == i else "#e8e8ec",
                command=(lambda idx=i: self._on_ref_channel_click(idx)),
            )
            row, col = i // self.REF_CHANNEL_COLS, i % self.REF_CHANNEL_COLS
            btn.grid(row=row, column=col, padx=(0, 8), pady=(0, 6), sticky="w")
            self.ref_ch_buttons.append(btn)

    def _on_ref_channel_click(self, idx):
        self.ref_ch.set(str(idx))
        self._refresh_ref_buttons_style()

    def _refresh_ref_buttons_style(self):
        cur = self._ref_ch_to_index()
        for i, btn in enumerate(self.ref_ch_buttons):
            if i == cur:
                btn.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT_HOVER)
            else:
                btn.configure(fg_color=INPUT_BG, text_color=TEXT, hover_color="#e8e8ec")

    def _update_ref_from_file(self):
        path = self.file_path.get().strip()
        if not path or not path.lower().endswith(".wav"):
            self._build_ref_channel_buttons(1)
            self.ref_ch.set("0")
            return
        if not os.path.isfile(path):
            return
        info = get_wav_info(path)
        if info:
            sr, nch = info
            self._build_ref_channel_buttons(nch)
            cur = self._ref_ch_to_index()
            if cur >= nch:
                self.ref_ch.set("0")
                self._refresh_ref_buttons_style()
        else:
            self._build_ref_channel_buttons(1)
            self.ref_ch.set("0")

    def _update_ref_combo(self):
        if self.is_wav.get():
            return
        try:
            n = max(1, int(self.pcm_ch.get()))
        except ValueError:
            n = 1
        self._build_ref_channel_buttons(n)
        cur = self._ref_ch_to_index()
        if cur >= n:
            self.ref_ch.set("0")
            self._refresh_ref_buttons_style()

    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="选择 WAV 或 PCM 文件",
            filetypes=[
                ("WAV / PCM", "*.wav;*.pcm"),
                ("WAV", "*.wav"),
                ("PCM", "*.pcm"),
                ("全部", "*.*"),
            ],
        )
        if path:
            self.file_path.set(path)
            if path.lower().endswith(".wav"):
                self.is_wav.set(True)
                self._on_format_change()
            else:
                self.is_wav.set(False)
                self._on_format_change()

    def _on_run(self):
        # 计算前先做一次兜底清理
        self._cleanup_log_dir_now()
        path = self.file_path.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("提示", "请先选择有效的输入文件。")
            return

        ref_ch = self._ref_ch_to_index()
        try:
            segment_s = float(self.segment_s.get())
            step_s = float(self.step_s.get())
            start_s = float(self.start_s.get())
        except ValueError:
            messagebox.showwarning("提示", "分段参数请填写数字。")
            return

        is_wav = self.is_wav.get()
        pcm_sr = 16000
        pcm_bits = 16
        pcm_ch = 6
        if not is_wav:
            try:
                pcm_sr = int(self.pcm_sr.get())
                pcm_bits = int(self.pcm_bits.get())
                pcm_ch = int(self.pcm_ch.get())
            except ValueError:
                messagebox.showwarning("提示", "PCM 参数请填写整数。")
                return
            if pcm_ch < 1 or ref_ch >= pcm_ch:
                messagebox.showwarning("提示", "参考通道号应小于通道数。")
                return

        # 按钮本身显示计算状态
        self.run_btn.configure(state="disabled", text="计算中…")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", "正在计算，请稍候…\n")
        self._clear_plot_data()
        self.latest_result_context = None
        if self.btn_export_report is not None:
            self.btn_export_report.configure(state="disabled")

        def done(ok, msg, delays_list, n_segs, details):
            self.root.after(0, lambda: self._done(ok, msg, delays_list, n_segs, details))

        thread = threading.Thread(
            target=run_calculation,
            args=(path, is_wav, pcm_sr, pcm_bits, pcm_ch, ref_ch, segment_s, step_s, start_s, done),
            daemon=True,
        )
        thread.start()

    def _cleanup_log_dir_now(self):
        try:
            _cleanup_empty_log_dir(self.app_base_dir)
            _relocate_exe_log_dir(self.app_base_dir, self.app_runtime_dir)
        except Exception:
            pass

    def _periodic_cleanup_log_dir(self):
        self._cleanup_log_dir_now()
        try:
            self.root.after(1200, self._periodic_cleanup_log_dir)
        except Exception:
            pass

    def _done(self, ok, msg, delays_list, n_segs, details):
        # 恢复按钮文本与状态
        self.run_btn.configure(state="normal", text="计算 Delay")
        self.result_text.delete("1.0", "end")
        details = details or {}
        if ok:
            # 写入当前结果（带颜色）
            self._render_colored_output(self.result_text, msg, add_end_marker=True)
            ref_ch = int(details.get("ref_ch", self._ref_ch_to_index()))
            delay_source = delays_list if delays_list is not None else details.get("delays", [])
            delays_clean = [float(x) for x in delay_source]
            self.latest_result_context = {
                "message": msg,
                "delays": delays_clean,
                "n_segs": int(n_segs),
                "details": details,
                "path": details.get("source_path", self.file_path.get().strip()),
                "ref_ch": ref_ch,
            }
            if self.btn_export_report is not None:
                self.btn_export_report.configure(state="normal")
            self._set_plot_data(details, ref_ch)
            self._open_chart_window()

            log_entry = "✅ 计算成功\n" + msg.strip("\n") + "\n"
            self.history.append(log_entry)
            # 限制 Log 条数，避免越用越卡
            if len(self.history) > MAX_LOG_ENTRIES:
                self.history = self.history[-MAX_LOG_ENTRIES:]

            # 如果 log 面板已展开，则追加显示
            if self.log_textbox is not None:
                # 如果达到上限，直接重绘（更简单且性能稳定）
                self._render_log_panel_from_history()
        else:
            self._clear_plot_data()
            self.latest_result_context = None
            if self.btn_export_report is not None:
                self.btn_export_report.configure(state="disabled")
            self.result_text.insert("end", f"计算出错:\n{msg}")
            messagebox.showerror("错误", msg)

    def _export_report_image(self):
        if not HAS_MPL:
            messagebox.showwarning("提示", "当前环境缺少 matplotlib，无法导出报告图。")
            return
        if not self.latest_result_context:
            messagebox.showwarning("提示", "请先完成一次成功计算，再导出报告图。")
            return

        source_path = self.latest_result_context.get("path") or "DelayScope"
        base_name = os.path.splitext(os.path.basename(source_path))[0] or "DelayScope"
        safe_name = "".join("_" if ch in '<>:"/\\|?*' else ch for ch in base_name).strip() or "DelayScope"
        out_path = filedialog.asksaveasfilename(
            title="导出报告图",
            defaultextension=".png",
            initialfile=f"{safe_name}_DelayScope_report.png",
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")],
        )
        if not out_path:
            return

        try:
            self._save_report_image(out_path)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return

        messagebox.showinfo("导出完成", f"报告图已保存到:\n{out_path}")

    def _save_report_image(self, out_path):
        if not HAS_MPL:
            raise RuntimeError("matplotlib is not available")
        if not self.latest_result_context:
            raise RuntimeError("No calculation result is available")

        context = self.latest_result_context
        details = context.get("details") or {}
        plot_data = self.latest_plot_data or {
            "times_s": list(details.get("times_s", [])),
            "per_channel_delays": [list(x) for x in details.get("per_channel_delays", [])],
            "per_channel_confidences": [list(x) for x in details.get("per_channel_confidences", [])],
            "ref_ch": int(details.get("ref_ch", context.get("ref_ch", 0))),
        }

        delay_source = context.get("delays")
        if delay_source is None:
            delay_source = details.get("delays", [])
        delays = list(delay_source)
        per_delays = [list(x) for x in plot_data.get("per_channel_delays", [])]
        per_conf = [list(x) for x in plot_data.get("per_channel_confidences", [])]
        n_ch = int(details.get("channels") or len(delays) or len(per_delays) or len(per_conf) or 0)
        sr = int(details.get("sample_rate") or 1)
        ref_ch = int(details.get("ref_ch", context.get("ref_ch", plot_data.get("ref_ch", 0))))
        n_segs = int(context.get("n_segs", 0))
        source_path = context.get("path") or details.get("source_path") or ""
        source_name = os.path.basename(source_path) if source_path else "未命名音频"
        duration_s = float(details.get("duration_s") or 0.0)
        segment_s = details.get("segment_s", "")
        step_s = details.get("step_s", "")
        start_s = details.get("start_s", "")
        confidence_threshold = float(details.get("confidence_threshold") or 0.0)
        min_confident_segments = int(details.get("min_confident_segments") or 0)
        summary_conf = list(details.get("summary_confidences", []))
        confident_counts = list(details.get("confident_segment_counts", []))
        used_filter = list(details.get("used_confidence_filter", []))
        raw_delays = list(details.get("raw_delays", delays))
        bandwidth = details.get("bandwidth") or {}
        format_name = details.get("source_format") or ("WAV" if self.is_wav.get() else "PCM")

        def seq_get(seq, idx, default=0):
            try:
                return seq[idx]
            except Exception:
                return default

        def fmt_num(value, digits=2, signed=False):
            try:
                value = float(value)
                prefix = "+" if signed else ""
                return f"{value:{prefix}.{digits}f}"
            except Exception:
                return "-"

        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        fig = Figure(figsize=(14, 8.75), dpi=160, facecolor="#f4f7fb")
        FigureCanvasAgg(fig)

        def add_panel(x, y, w, h):
            fig.patches.append(
                Rectangle(
                    (x, y),
                    w,
                    h,
                    transform=fig.transFigure,
                    facecolor="#ffffff",
                    edgecolor="#dbe3ef",
                    linewidth=1.0,
                    zorder=-10,
                )
            )

        add_panel(0.035, 0.825, 0.93, 0.13)
        add_panel(0.035, 0.105, 0.445, 0.695)
        add_panel(0.505, 0.44, 0.46, 0.36)
        add_panel(0.505, 0.105, 0.46, 0.305)

        logo_path = _bundled_resource_path(LOGO_REPORT_RELATIVE_PATH)
        if not os.path.isfile(logo_path):
            logo_path = _bundled_resource_path(LOGO_PNG_RELATIVE_PATH)
        if HAS_PIL and os.path.isfile(logo_path):
            try:
                logo_ax = fig.add_axes([0.055, 0.855, 0.07, 0.075])
                logo_ax.imshow(Image.open(logo_path))
                logo_ax.axis("off")
            except Exception:
                pass

        fig.text(0.14, 0.91, "DelayScope Report", fontsize=24, weight="bold", color=TEXT, ha="left", va="center")
        fig.text(0.14, 0.875, "音频通道延迟分析报告", fontsize=12, color=TEXT_SEC, ha="left", va="center")
        fig.text(0.94, 0.91, datetime.now().strftime("%Y-%m-%d %H:%M"), fontsize=10, color=TEXT_SEC, ha="right", va="center")

        meta_ax = fig.add_axes([0.14, 0.83, 0.805, 0.04])
        meta_ax.axis("off")
        bw_label = bandwidth.get("label", "-")
        bw_desc = "宽带(WB)" if bw_label == "WB" else ("窄带(NB)" if bw_label == "NB" else "-")
        meta_text = (
            f"文件: {source_name}    格式: {format_name}    采样率: {sr} Hz    "
            f"通道: {n_ch}    时长: {duration_s:.2f}s    带宽: {bw_desc}\n"
            f"参考通道: ch{ref_ch}    分段: {segment_s}s / 步长 {step_s}s / 起始 {start_s}s    "
            f"有效段数: {n_segs}    置信阈值: |rho| >= {confidence_threshold:.2f}, min={min_confident_segments}"
        )
        meta_ax.text(0.0, 0.95, meta_text, fontsize=9.2, color=TEXT_SEC, ha="left", va="top", linespacing=1.5)

        table_ax = fig.add_axes([0.055, 0.13, 0.405, 0.635])
        table_ax.axis("off")
        table_ax.text(0.0, 1.02, "通道结果", fontsize=14, weight="bold", color=TEXT, ha="left", va="bottom")

        rows = []
        row_verdicts = []
        for ch in range(n_ch):
            delay_value = float(seq_get(delays, ch, 0.0))
            conf_value = float(seq_get(summary_conf, ch, 1.0 if ch == ref_ch else 0.0))
            count_value = int(seq_get(confident_counts, ch, n_segs if ch == ref_ch else 0))
            used_value = bool(seq_get(used_filter, ch, True if ch == ref_ch else False))
            raw_value = float(seq_get(raw_delays, ch, delay_value))
            verdict, _reason = classify_delay_reliability(ch, ref_ch, conf_value, count_value, n_segs, used_value)
            if ch == ref_ch:
                recommendation = "参考"
            elif verdict == "可信":
                recommendation = "推荐"
            elif verdict == "存疑":
                recommendation = "复核"
            else:
                recommendation = "慎用"
            rows.append(
                [
                    f"ch{ch}",
                    fmt_num(delay_value, 1, signed=True),
                    fmt_num(delay_value / sr * 1000.0, 2, signed=True),
                    fmt_num(conf_value, 3),
                    f"{count_value}/{n_segs}",
                    recommendation,
                ]
            )
            row_verdicts.append(verdict)

        if rows:
            row_font = max(6.4, min(8.8, 10.2 - max(0, len(rows) - 8) * 0.16))
            table = table_ax.table(
                cellText=rows,
                colLabels=["Ch", "Samples", "ms", "|rho|", "Segs", "建议"],
                cellLoc="center",
                colLoc="center",
                loc="upper left",
                colWidths=[0.11, 0.20, 0.18, 0.16, 0.17, 0.18],
                bbox=[0.0, 0.0, 1.0, 0.965],
            )
            table.auto_set_font_size(False)
            table.set_fontsize(row_font)
            for (row, col), cell in table.get_celld().items():
                cell.set_edgecolor("#e5e7eb")
                cell.set_linewidth(0.7)
                if row == 0:
                    cell.set_facecolor("#eef4ff")
                    cell.set_text_props(color=TEXT, weight="bold")
                    continue
                verdict = row_verdicts[row - 1]
                if verdict == "可信":
                    bg = "#f0fbf4"
                elif verdict == "存疑":
                    bg = "#fff8ea"
                else:
                    bg = "#fff1f0"
                if row - 1 == ref_ch:
                    bg = "#eef4ff"
                cell.set_facecolor(bg if col == 5 else "#ffffff")
                cell.set_text_props(color=TEXT if col != 5 else "#1f2937")
        else:
            table_ax.text(0.5, 0.5, "没有可导出的通道结果", fontsize=11, color=TEXT_SEC, ha="center", va="center")

        def style_report_axis(ax, title, ylabel, ylim=None):
            ax.set_title(title, fontsize=12, color=TEXT, pad=8)
            ax.set_xlabel("Time (s)", fontsize=9, color=TEXT_SEC)
            ax.set_ylabel(ylabel, fontsize=9, color=TEXT_SEC)
            ax.set_facecolor("#ffffff")
            ax.grid(True, color="#e5e7eb", linewidth=0.8, alpha=0.9)
            ax.tick_params(axis="both", colors=TEXT_SEC, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#d1d5db")
            if ylim is not None:
                ax.set_ylim(*ylim)

        times_s = list(plot_data.get("times_s", []))
        plot_channels = list(range(max(len(per_delays), len(per_conf))))

        delay_ax = fig.add_axes([0.535, 0.485, 0.395, 0.265])
        style_report_axis(delay_ax, "Delay Drift", "delay_samples")
        delay_has_data = bool(times_s and per_delays)
        if delay_has_data:
            for ch in plot_channels:
                y = list(seq_get(per_delays, ch, []))
                if not y:
                    continue
                x = times_s[: len(y)] if times_s else list(range(len(y)))
                color = self._channel_plot_color(ch)
                delay_ax.plot(x, y, marker="o", markersize=2.5, linewidth=1.15, color=color, label=f"ch{ch}")
                if y:
                    median = sorted(y)[len(y) // 2]
                    delay_ax.axhline(median, color=color, linestyle="--", linewidth=0.75, alpha=0.25)
            if plot_channels:
                delay_ax.legend(loc="best", fontsize=7, frameon=False, ncol=2 if len(plot_channels) > 5 else 1)
        else:
            delay_ax.text(0.5, 0.5, "暂无分段漂移数据", fontsize=10, color=TEXT_SEC, ha="center", va="center", transform=delay_ax.transAxes)

        conf_ax = fig.add_axes([0.535, 0.15, 0.395, 0.215])
        style_report_axis(conf_ax, "Confidence", "|rho|", ylim=(0.0, 1.05))
        conf_ax.axhline(CONFIDENCE_OK, color="#34C759", linestyle="--", linewidth=1.0, alpha=0.75)
        conf_ax.axhline(CONFIDENCE_WARN, color="#FF9500", linestyle="--", linewidth=1.0, alpha=0.75)
        conf_has_data = bool(times_s and per_conf)
        if conf_has_data:
            for ch in plot_channels:
                y = list(seq_get(per_conf, ch, []))
                if not y:
                    continue
                x = times_s[: len(y)] if times_s else list(range(len(y)))
                conf_ax.plot(x, y, marker="o", markersize=2.5, linewidth=1.15, color=self._channel_plot_color(ch), label=f"ch{ch}")
            if plot_channels:
                conf_ax.legend(loc="lower right", fontsize=7, frameon=False, ncol=2 if len(plot_channels) > 5 else 1)
        else:
            conf_ax.text(0.5, 0.5, "暂无置信度曲线数据", fontsize=10, color=TEXT_SEC, ha="center", va="center", transform=conf_ax.transAxes)

        fig.text(
            0.055,
            0.065,
            "说明: delay_samples 为各通道相对参考通道的延迟；正数表示该通道滞后于参考。建议结合 |rho| 和达标分段数判断结果是否可直接采用。",
            fontsize=9,
            color=TEXT_SEC,
            ha="left",
            va="center",
        )
        fig.text(0.94, 0.065, f"Generated by {APP_NAME} {APP_VERSION}", fontsize=9, color=TEXT_SEC, ha="right", va="center")

        fig.savefig(out_path, dpi=160, facecolor=fig.get_facecolor())

    def _render_log_panel_from_history(self):
        if self.log_textbox is None:
            return
        self._set_text_state(self.log_textbox, "normal")
        t = self._get_tk_text(self.log_textbox)
        t.delete("1.0", "end")
        if not self.history:
            self._ensure_text_tags(self.log_textbox)
            self._insert_line(self.log_textbox, "ℹ️ 当前会话还没有任何计算记录。", "section_hdr")
            self._insert_line(self.log_textbox, "")
            self._insert_line(self.log_textbox, "每次点击「计算 Delay」成功后，这里会追加一条 Log，方便回溯。", "section_hdr")
        else:
            for idx, item in enumerate(self.history):
                if idx > 0:
                    t.insert("end", "\n")
                self._render_colored_output(self.log_textbox, item.strip("\n"), add_end_marker=False)
        self._set_text_state(self.log_textbox, "disabled")
        try:
            t.see("end")
        except Exception:
            pass

    def _toggle_history_panel(self):
        """右侧 log 面板展开/收起（保持一个窗口）。"""
        # 如果 log 面板已存在，则收起
        if self.history_panel is not None:
            # 从 PanedWindow 中移除，再销毁
            try:
                self.paned.forget(self.history_panel)
            except Exception:
                pass
            self.history_panel.destroy()
            self.history_panel = None
            self.btn_history.configure(fg_color=INPUT_BG, text_color=TEXT, hover_color="#e0e0e5")
            # 收起时尽量恢复窗口宽度（不小于基础宽度）
            try:
                cur_w = self.root.winfo_width()
                cur_h = self.root.winfo_height()
                new_w = max(self.base_width, cur_w - self.log_panel_width)
                self.root.geometry(f"{int(new_w)}x{int(cur_h)}")
            except Exception:
                pass
            return

        # 展开前记录当前主区域宽度，用于固定主区域、不被挤压
        try:
            main_w = self.main_area.winfo_width()
        except Exception:
            main_w = None

        # 创建右侧 log 面板，并加入 PanedWindow（即使暂无记录也先展开）
        self.history_panel = ctk.CTkFrame(self.paned, fg_color=CARD_BG, corner_radius=0)
        self.paned.add(self.history_panel, minsize=220)

        self.btn_history.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT_HOVER)

        # 展开时优先加宽整体窗口，避免压缩主界面区域
        try:
            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            new_w = cur_w + self.log_panel_width
            self.root.geometry(f"{int(new_w)}x{int(cur_h)}")
            self.root.update_idletasks()
            # 调整分割条位置：左侧宽度保持为展开前的 main_w
            if main_w is not None:
                self.paned.sash_place(0, int(main_w), 0)
        except Exception:
            pass

        header = ctk.CTkLabel(
            self.history_panel,
            text="Log 记录（本次打开期间）",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        )
        header.pack(anchor="w", pady=(12, 8), padx=12)

        # Log 面板拖动优化：拖动中隐藏重绘，松手后恢复
        def _on_paned_press(_e):
            self._paned_dragging = True
            self._set_light_mode(True)

        def _on_paned_release(_e):
            self._paned_dragging = False
            # 稍后恢复（避免立刻抖动）
            try:
                self.root.after(120, lambda: self._set_light_mode(False))
            except Exception:
                pass

        # 绑定到 panedwindow，拖动 sash 时也会触发
        self.paned.bind("<ButtonPress-1>", _on_paned_press, add="+")
        self.paned.bind("<ButtonRelease-1>", _on_paned_release, add="+")

        text_box = ctk.CTkTextbox(
            self.history_panel,
            fg_color=INPUT_BG,
            border_width=0,
            corner_radius=INPUT_RADIUS,
            # Log 里包含 emoji，使用支持 emoji 的字体避免方块
            font=ctk.CTkFont(family="Segoe UI", size=11),
            wrap="word",
        )
        text_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log_textbox = text_box

        # resize/拖动期间的轻量占位
        self.log_placeholder = ctk.CTkLabel(
            self.history_panel,
            text="调整窗口中…",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SEC,
        )

        # 初次展开渲染
        self._render_log_panel_from_history()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DelayCalcApp()
    app.run()
