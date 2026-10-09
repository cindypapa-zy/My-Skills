#!/usr/bin/env python3
"""
subtitle_pipeline.py — PIL 字幕条 + ffmpeg overlay 烧录(无 libass 环境专用)
本机 brew ffmpeg 8.0.1 无 libass/drawtext,ass 路线是死路;唯一已验证路线:
  PIL 渲底部字幕条 PNG(1920×140) → ffmpeg overlay enable=between 定时烧录
用法:
  python3 subtitle_pipeline.py --video <mp4> --srt <口播.srt> [--style auto|dark|light]
"""
import argparse, re, subprocess, sys
from pathlib import Path

W, H = 1920, 140          # 字幕条尺寸(全帧 PNG 会卡死 overlay,只画底部一条)

def _pick_font():
    """跨平台中文字体探测:优先本机 Noto CJK(Linux),回退 macOS 系统字体。"""
    import glob
    cands = [
        # Linux (本机本机)
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    cands += sorted(glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True))
    cands += sorted(glob.glob("/usr/share/fonts/**/*CJK*.tt[cf]", recursive=True))
    # macOS（原机）
    cands += [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    return ""

FONT = _pick_font()
# 双样式:深色画面段用白字黑边;浅底(白板)段用深字白边。auto 按首帧亮度猜。
STYLES = {
    "dark":  {"fill": (255, 255, 255, 255), "stroke": (10, 5, 3, 255), "size": 54, "sw": 3},
    "light": {"fill": (10, 5, 3, 255),       "stroke": (251, 251, 251, 255), "size": 54, "sw": 3},
}

def parse_srt(path):
    txt = Path(path).read_text(encoding="utf-8")
    events = []
    for block in re.split(r"\n\s*\n", txt.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2: continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", lines[1])
        if not m: continue
        def sec(g): return int(g[0])*3600 + int(g[1])*60 + int(g[2]) + int(g[3])/1000
        events.append((sec(m.groups()[:4]), sec(m.groups()[4:]), "".join(lines[2:])))
    return events

def render_bar(text, style, out_png):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not FONT:
        raise SystemExit("未找到可用中文字体,请安装 fonts-noto-cjk 或设置 FONT")
    try: f = ImageFont.truetype(FONT, style["size"], index=0)
    except Exception: f = ImageFont.truetype(FONT, style["size"])
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, (H - style["size"]) / 2), text, font=f,
           fill=style["fill"], stroke_width=style["sw"], stroke_fill=style["stroke"])
    img.save(out_png)

def guess_style(video):
    """抽首帧测平均亮度:亮底→light 样式(深字),暗底→dark 样式(白字)"""
    import numpy as np
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-frames:v", "1", "/tmp/_sub_probe.png"], check=True)
    from PIL import Image
    a = np.asarray(Image.open("/tmp/_sub_probe.png").convert("L"), dtype=float)
    return "light" if a.mean() > 140 else "dark"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--srt", required=True)
    ap.add_argument("--style", default="auto", choices=["auto", "dark", "light"])
    ap.add_argument("--out", help="默认 <video>-字幕版.mp4")
    args = ap.parse_args()
    video = Path(args.video); srt = Path(args.srt)
    out = Path(args.out) if args.out else video.with_name(video.stem + "_字幕版.mp4")
    style = guess_style(str(video)) if args.style == "auto" else args.style
    events = parse_srt(srt)
    if not events:
        raise SystemExit(f"[sub] 错误:{srt} 没解析出任何字幕事件(检查 SRT 格式)")
    print(f"[sub] {len(events)} 条字幕,样式={style}(白字黑边=dark / 深字白边=light)")

    # 逐条渲字幕条 → 单图多 overlay 会卡死,改"每图一路"合成一条 filter_complex
    overlays = []
    inputs = ["-i", str(video)]
    for i, (t0, t1, text) in enumerate(events):
        png = f"/tmp/_sub_{i:03d}.png"
        render_bar(text, STYLES[style], png)
        inputs += ["-i", png]
        # 短输入用默认 repeat(每帧重读当前帧)。
        # ⚠️ 绝不能用 eof_action=pass——单帧 PNG 输入 t≈0 就 EOF，pass 让主画面在首条
        #    enable 窗口内直通，首条字幕被吞(2026-10-08 原机作者实测 bug1)；repeat 无尾部等待副作用。
        src = "[0:v]" if i == 0 else f"[v{i-1}]"
        overlays.append(
            f"{src}[{i+1}:v]overlay=0:H-140:enable='between(t,{t0:.2f},{t1:.2f})'[v{i}]"
        )
    fc = ";".join(overlays)
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", fc, "-map", f"[v{len(events)-1}]", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "21", "-preset", "medium", "-c:a", "copy", str(out)]
    subprocess.run(cmd, check=True)
    print(f"[sub] 字幕版 → {out}")
    print("[next] 片头片尾 → python3 " + str(Path(__file__).parent / "title_cards.py") +
          f" --video {out} --title <片头字> --credits <片尾三行,逗号分隔>")

if __name__ == "__main__":
    main()
