# -*- coding: utf-8 -*-
"""
Generate a short DelayScope tutorial video.

The script creates 16:9 slide images with Pillow, builds a PowerPoint deck,
and asks PowerPoint to export the deck as MP4. It is intentionally local and
reproducible: no network service or online video generator is required.
"""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import win32com.client


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "branding"
DOC_IMAGES = ROOT / "docs" / "images"
OUT_DIR = ROOT / "docs" / "videos"
FRAME_DIR = ROOT / "build" / "video_frames"

W, H = 1280, 720

BG = "#f4f7fb"
CARD = "#ffffff"
TEXT = "#101828"
TEXT_MUTED = "#667085"
BLUE = "#007AFF"
BLUE_DARK = "#0b3b91"
CYAN = "#5AC8FA"
GREEN = "#34C759"
ORANGE = "#FF9500"
RED = "#FF3B30"
PURPLE = "#5856D6"


def color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


F_TITLE = font(52, True)
F_H1 = font(40, True)
F_H2 = font(30, True)
F_BODY = font(24)
F_BODY_B = font(24, True)
F_SMALL = font(18)
F_SMALL_B = font(18, True)
F_CODE = font(22)


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue

        current = ""
        for ch in para:
            candidate = current + ch
            if text_size(draw, candidate, fnt)[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fnt: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 8,
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=color(fill))
        y += text_size(draw, line or " ", fnt)[1] + line_gap
    return y


def rounded(draw: ImageDraw.ImageDraw, box, radius=24, fill=CARD, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=color(fill), outline=color(outline) if outline else None, width=width)


def fit_image(img: Image.Image, box: tuple[int, int, int, int], cover: bool = False) -> Image.Image:
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    iw, ih = img.size
    scale = max(bw / iw, bh / ih) if cover else min(bw / iw, bh / ih)
    resized = img.resize((int(iw * scale), int(ih * scale)), Image.Resampling.LANCZOS)
    if cover:
        left = max(0, (resized.width - bw) // 2)
        top = max(0, (resized.height - bh) // 2)
        resized = resized.crop((left, top, left + bw, top + bh))
    canvas = Image.new("RGBA", (bw, bh), (255, 255, 255, 0))
    canvas.alpha_composite(resized.convert("RGBA"), ((bw - resized.width) // 2, (bh - resized.height) // 2))
    return canvas


def paste_fit(base: Image.Image, img: Image.Image, box: tuple[int, int, int, int], cover=False):
    fitted = fit_image(img, box, cover=cover)
    base.alpha_composite(fitted, (box[0], box[1]))


def crop_ratio(img: Image.Image, left: float, top: float, right: float, bottom: float) -> Image.Image:
    w, h = img.size
    return img.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))


def new_slide(title: str | None = None, subtitle: str | None = None) -> Image.Image:
    img = Image.new("RGBA", (W, H), color(BG) + (255,))
    draw = ImageDraw.Draw(img)
    # Soft brand accent kept outside the text area.
    for r in range(280, 40, -8):
        alpha = int(20 * (r / 280))
        draw.ellipse((W - r // 2, -r // 2, W + r // 2, r // 2), fill=color(BLUE) + (alpha,))
    if title:
        draw.text((64, 44), title, font=F_H1, fill=color(TEXT))
    if subtitle:
        draw.text((66, 94), subtitle, font=F_SMALL, fill=color(TEXT_MUTED))
    return img


def add_logo(draw_img: Image.Image, x: int, y: int, size: int):
    logo = Image.open(ASSETS / "delayscope-logo.png").convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    draw_img.alpha_composite(logo, (x, y))


def add_footer(draw: ImageDraw.ImageDraw, text: str = "DelayScope · 多通道音频时延分析"):
    draw.text((64, H - 48), text, font=F_SMALL, fill=color(TEXT_MUTED))


def slide_title() -> Image.Image:
    img = new_slide()
    draw = ImageDraw.Draw(img)
    add_logo(img, 88, 116, 170)
    draw.text((300, 142), "DelayScope", font=F_TITLE, fill=color(TEXT))
    draw.text((304, 210), "让多通道音频时延看得见", font=F_H2, fill=color(BLUE_DARK))
    draw_wrapped(
        draw,
        (304, 278),
        "用于通道间时延估计、Delay Drift 可视化、置信度判断和输入音频质量诊断。",
        F_BODY,
        TEXT_MUTED,
        760,
        10,
    )
    chips = ["WAV / PCM", "GCC-PHAT", "Delay Drift", "Confidence", "Clipping Check"]
    x = 304
    for chip in chips:
        tw, th = text_size(draw, chip, F_SMALL_B)
        rounded(draw, (x, 408, x + tw + 30, 448), 20, fill="#eaf3ff")
        draw.text((x + 15, 418), chip, font=F_SMALL_B, fill=color(BLUE))
        x += tw + 44
    add_footer(draw)
    return img


def slide_problem() -> Image.Image:
    img = new_slide("为什么需要 DelayScope？", "多通道音频里，几十个采样点的差异也会影响工程结果")
    draw = ImageDraw.Draw(img)
    cards = [
        ("通道固定延迟", "采集卡、DSP、链路缓冲可能让某些通道提前或滞后。", BLUE),
        ("时延漂移", "采样率偏差或时钟不同步，会让 delay 随时间缓慢变化。", ORANGE),
        ("异常片段", "静音、噪声、截幅、填充或丢帧会干扰单次估计。", RED),
        ("结果可信度", "只看一个 delay 数字不够，还需要知道它是否可靠。", GREEN),
    ]
    for i, (head, body, accent) in enumerate(cards):
        x = 70 + (i % 2) * 575
        y = 170 + (i // 2) * 190
        rounded(draw, (x, y, x + 520, y + 140), 26, fill=CARD)
        draw.ellipse((x + 28, y + 34, x + 82, y + 88), fill=color(accent))
        draw.text((x + 108, y + 30), head, font=F_BODY_B, fill=color(TEXT))
        draw_wrapped(draw, (x + 108, y + 70), body, F_SMALL, TEXT_MUTED, 360, 6)
    add_footer(draw)
    return img


def slide_usage(main: Image.Image) -> Image.Image:
    img = new_slide("如何使用", "选择文件、设置参考通道和分段参数，然后点击计算")
    draw = ImageDraw.Draw(img)
    steps = [
        ("1", "选择 WAV / PCM 文件"),
        ("2", "选择参考通道"),
        ("3", "设置 segment / step / start"),
        ("4", "点击“计算 Delay”"),
    ]
    y = 170
    for num, text in steps:
        draw.ellipse((72, y, 116, y + 44), fill=color(BLUE))
        draw.text((88, y + 7), num, font=F_SMALL_B, fill=(255, 255, 255))
        draw.text((132, y + 7), text, font=F_BODY, fill=color(TEXT))
        y += 82

    rounded(draw, (520, 130, 1208, 626), 28, fill="#d9e6f7")
    shot = crop_ratio(main, 0.0, 0.0, 1.0, 0.62)
    paste_fit(img, shot, (540, 150, 1188, 606), cover=False)
    add_footer(draw)
    return img


def slide_results(main: Image.Image) -> Image.Image:
    img = new_slide("如何读结果", "最终 delay、毫秒换算、置信度和质量提示集中展示")
    draw = ImageDraw.Draw(img)
    rounded(draw, (64, 136, 770, 634), 28, fill=CARD)
    draw.text((98, 170), "结果摘要", font=F_H2, fill=color(TEXT))
    draw.text((100, 220), "文件: demo/delaycalc_demo.wav", font=F_SMALL, fill=color(TEXT_MUTED))
    draw.text((100, 252), "采样率: 16000 Hz    通道数: 6    有效段数: 12", font=F_SMALL, fill=color(TEXT_MUTED))
    draw.text((100, 294), "各通道相对参考的 delay_samples", font=F_BODY_B, fill=color(BLUE_DARK))
    rows = [
        ("ch0", "+0.0", "0.00 ms", "|rho|=1.000", "#667085"),
        ("ch1", "-32.0", "-2.00 ms", "|rho|=0.998", RED),
        ("ch2", "+47.0", "2.94 ms", "|rho|=0.998", BLUE),
        ("ch3", "-83.0", "-5.19 ms", "|rho|=0.998", RED),
    ]
    y0 = 340
    for ch, delay, ms, rho, accent in rows:
        rounded(draw, (100, y0, 724, y0 + 54), 16, fill="#f6f8fb")
        draw.text((124, y0 + 14), ch, font=F_SMALL_B, fill=color(TEXT))
        draw.text((220, y0 + 14), delay, font=F_SMALL_B, fill=color(accent))
        draw.text((338, y0 + 14), ms, font=F_SMALL, fill=color(TEXT_MUTED))
        draw.text((456, y0 + 14), rho, font=F_SMALL, fill=color(GREEN))
        draw.text((590, y0 + 14), "可信", font=F_SMALL_B, fill=color(GREEN))
        y0 += 66
    bullets = [
        ("delay_samples", "采样点级时延，正负号表示相对参考通道的先后。"),
        ("delay_time_ms", "按采样率换算成毫秒，更适合工程沟通。"),
        ("confidence", "用 |rho| 观察结果是否可信。"),
        ("quality checks", "辅助判断截幅、填充、丢帧和频带异常。"),
    ]
    y = 164
    for head, body in bullets:
        rounded(draw, (820, y, 1190, y + 82), 18, fill=CARD)
        draw.text((842, y + 14), head, font=F_SMALL_B, fill=color(BLUE_DARK))
        draw_wrapped(draw, (842, y + 40), body, F_SMALL, TEXT_MUTED, 305, 4)
        y += 104
    add_footer(draw)
    return img


def slide_chart(chart: Image.Image) -> Image.Image:
    img = new_slide("Delay Drift：看时延是否稳定", "不只看最终值，还要看每个分段上的轨迹")
    draw = ImageDraw.Draw(img)
    rounded(draw, (64, 124, 880, 630), 28, fill="#d9e6f7")
    paste_fit(img, chart, (84, 144, 860, 610), cover=True)
    points = [
        ("水平稳定", "说明通道间固定延迟基本稳定"),
        ("缓慢漂移", "可能存在时钟或采样率偏差"),
        ("突发跳变", "可能是异常片段、丢帧或噪声影响"),
    ]
    y = 176
    for label, body in points:
        draw.ellipse((930, y + 8, 950, y + 28), fill=color(GREEN if label == "水平稳定" else ORANGE if label == "缓慢漂移" else RED))
        draw.text((966, y), label, font=F_BODY_B, fill=color(TEXT))
        draw_wrapped(draw, (966, y + 36), body, F_SMALL, TEXT_MUTED, 230, 6)
        y += 136
    add_footer(draw)
    return img


def slide_principle() -> Image.Image:
    img = new_slide("核心原理：GCC-PHAT", "利用相位信息估计两个通道之间的相对时延")
    draw = ImageDraw.Draw(img)
    pipeline = [
        ("x[n], y[n]", "输入两路信号"),
        ("FFT", "转到频域"),
        ("X(k)Y*(k)", "互功率谱"),
        ("PHAT", "只保留相位"),
        ("IFFT", "回到相关函数"),
        ("Peak", "峰值位置即 delay"),
    ]
    x = 68
    y = 170
    for i, (head, body) in enumerate(pipeline):
        rounded(draw, (x, y, x + 170, y + 100), 22, fill=CARD)
        draw.text((x + 22, y + 22), head, font=F_BODY_B, fill=color(BLUE_DARK))
        draw.text((x + 22, y + 58), body, font=F_SMALL, fill=color(TEXT_MUTED))
        if i < len(pipeline) - 1:
            draw.line((x + 178, y + 50, x + 216, y + 50), fill=color(BLUE), width=4)
            draw.polygon([(x + 216, y + 50), (x + 202, y + 42), (x + 202, y + 58)], fill=color(BLUE))
        x += 202

    formula = "G_phat(k) = X(k)Y*(k) / (|X(k)Y*(k)| + eps)"
    rounded(draw, (124, 342, 1156, 438), 24, fill="#eef6ff")
    draw.text((164, 374), formula, font=F_CODE, fill=color(BLUE_DARK))

    draw_wrapped(
        draw,
        (126, 494),
        "GCC-PHAT 对幅度差异更不敏感，更关注两路信号的相位一致性。DelayScope 会在给定最大时延范围内寻找相关峰值，得到每个分段的 delay_samples。",
        F_BODY,
        TEXT_MUTED,
        1020,
        10,
    )
    add_footer(draw)
    return img


def slide_statistics() -> Image.Image:
    img = new_slide("为什么结果更稳", "多段统计 + 置信度过滤，降低异常片段影响")
    draw = ImageDraw.Draw(img)
    # segmented timeline
    start_x, start_y = 96, 192
    for i in range(12):
        x = start_x + i * 82
        fill = GREEN if i not in (3, 8) else RED
        rounded(draw, (x, start_y, x + 58, start_y + 58), 12, fill=fill)
        draw.text((x + 19, start_y + 17), str(i + 1), font=F_SMALL_B, fill=(255, 255, 255))
    draw.text((96, 270), "把长音频切成多个 segment，逐段估计 delay", font=F_BODY, fill=color(TEXT))

    cards = [
        ("中位数汇总", "比平均值更抗异常段，不容易被少数错误估计拖偏。", BLUE),
        ("|rho| 置信度", "对齐后计算归一化相关，判断该段 delay 是否可信。", GREEN),
        ("质量诊断", "同时检查带宽、截幅、填充或丢帧，帮助解释异常。", ORANGE),
    ]
    for i, (head, body, accent) in enumerate(cards):
        x = 110 + i * 370
        y = 390
        rounded(draw, (x, y, x + 320, y + 160), 24, fill=CARD)
        draw.rectangle((x, y, x + 320, y + 8), fill=color(accent))
        draw.text((x + 24, y + 32), head, font=F_BODY_B, fill=color(TEXT))
        draw_wrapped(draw, (x + 24, y + 76), body, F_SMALL, TEXT_MUTED, 260, 6)
    add_footer(draw)
    return img


def slide_close() -> Image.Image:
    img = new_slide()
    draw = ImageDraw.Draw(img)
    add_logo(img, 104, 112, 150)
    draw.text((290, 136), "DelayScope", font=F_TITLE, fill=color(TEXT))
    draw.text((294, 206), "面向多通道音频工程分析的轻量工具", font=F_H2, fill=color(BLUE_DARK))
    draw_wrapped(
        draw,
        (294, 286),
        "适合麦克风阵列、AEC、采集设备校准、多通道同步、音频质量排查和算法前处理验证。",
        F_BODY,
        TEXT_MUTED,
        780,
        10,
    )
    rounded(draw, (294, 444, 948, 504), 24, fill="#eaf3ff")
    draw.text((326, 460), "github.com/Viodmian/DelayScope", font=F_BODY_B, fill=color(BLUE_DARK))
    draw.text((294, 568), "让通道时延问题更容易被发现、解释和复现。", font=F_BODY, fill=color(TEXT))
    add_footer(draw, "DelayScope · WAV / PCM · GCC-PHAT · Delay Drift · Confidence")
    return img


def build_slides() -> list[tuple[Image.Image, int]]:
    main = Image.open(DOC_IMAGES / "delaycalc-main.png").convert("RGBA")
    chart = Image.open(DOC_IMAGES / "delaycalc-chart.png").convert("RGBA")
    return [
        (slide_title(), 6),
        (slide_problem(), 9),
        (slide_usage(main), 11),
        (slide_results(main), 11),
        (slide_chart(chart), 11),
        (slide_principle(), 14),
        (slide_statistics(), 11),
        (slide_close(), 8),
    ]


def save_slide_frames(slides: list[tuple[Image.Image, int]]) -> list[Path]:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for idx, (img, _) in enumerate(slides, 1):
        path = FRAME_DIR / f"slide_{idx:02d}.png"
        img.convert("RGB").save(path, quality=95)
        paths.append(path)
    return paths


def build_powerpoint(slide_paths: list[Path], durations: list[int], pptx_path: Path, mp4_path: Path):
    app = win32com.client.Dispatch("PowerPoint.Application")
    app.Visible = True
    presentation = app.Presentations.Add()
    presentation.PageSetup.SlideWidth = W
    presentation.PageSetup.SlideHeight = H

    try:
        for idx, path in enumerate(slide_paths, 1):
            slide = presentation.Slides.Add(idx, 12)  # ppLayoutBlank
            slide.FollowMasterBackground = False
            slide.Shapes.AddPicture(str(path), False, True, 0, 0, W, H)
            slide.SlideShowTransition.AdvanceOnTime = True
            slide.SlideShowTransition.AdvanceTime = durations[idx - 1]

        pptx_path.parent.mkdir(parents=True, exist_ok=True)
        if pptx_path.exists():
            pptx_path.unlink()
        if mp4_path.exists():
            mp4_path.unlink()
        presentation.SaveAs(str(pptx_path))

        # FileName, UseTimingsAndNarrations, DefaultSlideDuration, VertResolution, FramesPerSecond, Quality
        presentation.CreateVideo(str(mp4_path), True, 5, 720, 24, 85)
        deadline = time.time() + 900
        while time.time() < deadline:
            status = presentation.CreateVideoStatus
            if status == 3:  # ppMediaTaskStatusDone
                return
            if status == 4:  # ppMediaTaskStatusFailed
                raise RuntimeError("PowerPoint video export failed")
            time.sleep(2)
        raise TimeoutError("Timed out waiting for PowerPoint video export")
    finally:
        presentation.Close()
        app.Quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", default=str(OUT_DIR / "DelayScope_intro.pptx"))
    parser.add_argument("--mp4", default=str(OUT_DIR / "DelayScope_intro.mp4"))
    parser.add_argument("--frames-only", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slides = build_slides()
    slide_paths = save_slide_frames(slides)
    durations = [duration for _, duration in slides]
    print(f"Generated {len(slide_paths)} slide frames in {FRAME_DIR}")

    if args.frames_only:
        return

    build_powerpoint(slide_paths, durations, Path(args.pptx).resolve(), Path(args.mp4).resolve())
    print(f"Saved PPTX: {Path(args.pptx).resolve()}")
    print(f"Saved MP4:  {Path(args.mp4).resolve()}")


if __name__ == "__main__":
    main()
