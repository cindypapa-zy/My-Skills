#!/usr/bin/env python3
"""
compress.py — 飞书 30MB 限内压缩交付(CRF 迭代,锚点已实测)
硬限 31,457,280 字节(超限报 file exceeds limit)。实测锚点:
  123.6s 1080p30 → CRF 24≈44MB(超) / CRF 27≈29.3MB(达标) / CRF 30 更保险
  30s  720p      → CRF 21≈8.9MB
规则:从 CRF 24 起,超限 +3 重压;1080p 长片直接 CRF 27 起步;音频 -c:a copy 不损混音。
用法:
  python3 compress.py --in <mp4> [--crf 27] [--out <mp4>]
"""
import argparse, subprocess, os
from pathlib import Path

LIMIT = 31_457_280          # 飞书单附件硬限(字节)

def size_of(p): return os.path.getsize(p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--crf", type=int, default=27, help="1080p 长片 27 起步,720p 短片可 21")
    ap.add_argument("--out", help="默认 <in>-飞书版.mp4")
    args = ap.parse_args()
    src = Path(args.inp)
    out = Path(args.out) if args.out else src.with_name(src.stem + "_飞书版.mp4")

    # 探分辨率定步进(720p 用 crf-3 起步)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=height", "-of", "csv=p=0", str(src)],
                       capture_output=True, text=True)
    # 注意：部分 ffprobe 版本 csv=p=0 会输出尾逗号（如 "720,"），直接取 [-1] 会得到空串。
    # 统一过滤空字段再取最后一个。
    parts = [p for p in r.stdout.strip().split(",") if p.strip()]
    if not parts:
        raise SystemExit(f"[compress] ❌ 无法探测分辨率（ffprobe 输出={r.stdout!r}），中止以免误压")
    h = int(parts[-1])
    crf = args.crf if h >= 1080 else max(18, args.crf - 3)

    for attempt in range(4):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                        "-c:a", "copy", str(out)], check=True)
        sz = size_of(out)
        print(f"[compress] CRF {crf} → {sz/1e6:.1f}MB", end="")
        # 异常小体积预警:成品通常 >1MB,0 点几 MB 多半是上游丢了主片(concat bug2)产出空壳
        if sz < 1_000_000:
            print(f"\n[compress] ⚠️ 警告:输出仅 {sz}B,异常小——上游可能丢了主片"
                  f"(检查 title_cards concat),别急着当达标发出去")
        if sz <= LIMIT:
            print(f"  ✅ 达标(限 {LIMIT/1e6:.1f}MB)")
            print(f"[deliver] message 发 {out}(一次只带 1 个 attachment)")
            return
        print("  超限,加压"); crf += 3
    raise SystemExit(f"[compress] 4 次仍超 {LIMIT}B,需手动降分辨率")

if __name__ == "__main__":
    main()
