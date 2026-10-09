#!/usr/bin/env python3
"""
title_cards.py — 独立片头/片尾片段 + 原片拼接(默认路线,时长变长)
用户说「加到原视频开头/结尾」走这条。卡片段 = 不透明底整卡 + 静音 + 淡入淡出。
(另一条"叠在原画面上"路线见 references/端到端流水线.md 路线 B,非默认不展开)
用法:
  python3 title_cards.py --video <mp4> --title <片头文字> \
      --credits "感谢收看,出品：示例团队" [--head-sec 4] [--tail-sec 5]
"""
import argparse, subprocess
from pathlib import Path

W, H = 1920, 1080
def _pick_font():
    """跨平台中文字体探测:优先本机 Noto CJK(Linux),回退 macOS 系统字体。"""
    import glob
    cands = [
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    cands += sorted(glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True))
    cands += sorted(glob.glob("/usr/share/fonts/**/*CJK*.tt[cf]", recursive=True))
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
BG = (251, 251, 251, 255)      # 不透明!与白板底一致;透明卡会跟画面自身文字撞车
INK = (10, 5, 3, 255)

def render_card(lines, sizes, out_png):
    """lines: 文本行列表;sizes: 对应字号;整卡不透明底,深色居中"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)
    n = len(lines)
    y = 1080 // 2 - (sum(sizes) + (n - 1) * 60) // 2
    for text, sz in zip(lines, sizes):
        try: f = ImageFont.truetype(FONT, sz, index=0)
        except Exception: f = ImageFont.truetype(FONT, sz)
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=INK)
        y += sz + 60
    img.save(out_png)

def silent_card_segment(png, dur, out_mp4):
    """卡片段:loop 图 + anullsrc 静音 + fade,参数对齐原片(yuv420p/30fps/48kHz)"""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", str(dur),
                    "-i", png, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-vf", f"fps=30,format=yuv420p,fade=t=in:st=0:d=0.5,fade=t=out:st={dur-0.5}:d=0.5",
                    "-c:v", "libx264", "-crf", "21", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", out_mp4], check=True)

def concat(parts, out):
    # ⚠️ concat 列表里必须写绝对路径——ffmpeg 以 list 文件所在目录解析相对路径，
    #    写 /tmp 会找不到主片，只告警不报错，产出空壳(2026-10-08 原机作者实测 bug2)
    abs_parts = [str(Path(p).resolve()) for p in parts]
    lst = Path("/tmp/_tc_list.txt"); lst.write_text(
        "".join(f"file '{p}'\n" for p in abs_parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart", out], check=True)
    # concat 后强制时长核验:拼接结果与原片+卡片时长偏差 >0.5s 说明有段没拼上,拒交付
    _verify_concat(out, parts)

def _verify_concat(out, parts):
    import subprocess as _sp
    def _dur(f):
        r = _sp.run(["ffprobe","-v","error","-show_entries","format=duration",
                     "-of","csv=p=0",str(f)],capture_output=True,text=True)
        try: return float(r.stdout.strip())
        except: return -1
    got = _dur(out)
    expect = sum(max(0,_dur(p)) for p in parts)
    if got < 0 or abs(got - expect) > 0.5:
        raise SystemExit(f"[cards] ✗ 拼接时长异常:实际{got:.1f}s 期望≈{expect:.1f}s"
                         f"(有段没拼上?检查 concat 列表路径)")
    print(f"[cards] 拼接时长核验 OK {got:.1f}s ≈ 期望 {expect:.1f}s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--title", help="片头标题(一行),可空")
    ap.add_argument("--credits", help="片尾多行,逗号分隔,如 '感谢收看,出品：X,协助制作：Y'")
    ap.add_argument("--head-sec", type=float, default=4)
    ap.add_argument("--tail-sec", type=float, default=5)
    ap.add_argument("--out", help="默认 <video>-片头片尾版.mp4")
    args = ap.parse_args()
    video = Path(args.video)
    out = Path(args.out) if args.out else video.with_name(video.stem + "_片头片尾版.mp4")
    tmp = []; parts = []

    if args.title:
        tpng = "/tmp/_tc_title.png"
        render_card([args.title], [150], tpng)
        thead = "/tmp/_tc_head.mp4"; silent_card_segment(tpng, args.head_sec, thead)
        parts.append(thead); tmp.append(thead)
    parts.append(str(video))
    if args.credits:
        lines = args.credits.split(",")
        sizes = [96] + [52] * (len(lines) - 1)   # 首行大,副行小
        cpng = "/tmp/_tc_credits.png"
        render_card(lines, sizes, cpng)
        ttail = "/tmp/_tc_tail.mp4"; silent_card_segment(cpng, args.tail_sec, ttail)
        parts.append(ttail); tmp.append(ttail)

    concat(parts, str(out))
    print(f"[cards] 片头片尾版 → {out}")
    added = (args.head_sec if args.title else 0) + (args.tail_sec if args.credits else 0)
    print(f"[cards] 时长 = 原片 + {added}s(抽帧按新时间轴算:片尾卡在 原片长+片头长 之后)")
    print("[next] 压缩交付 → python3 " + str(Path(__file__).parent / "compress.py") + f" --in {out}")

if __name__ == "__main__":
    main()
