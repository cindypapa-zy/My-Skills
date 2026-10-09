#!/usr/bin/env python3
"""
render_video.py — 一键出片流水线主控（基于花叔 huashu-art-motion 引擎）
渲染 Canvas 2D 逐帧动画 → 分段截图 → ffmpeg 装配成片（含口播音轨 + BGM 混音）
用法:
  python3 render_video.py --film <film_dir> [--fps 30] [--out <mp4>] [--no-bgm]
film_dir 下需有:
  main.js         # SCENES['id'] = {draw(c,lt,t)} 画段；window.__total 总时长；__bootErrors 拒启
  voiceover.mp3   # 口播（可选，无则出无声片）
  bgm.mp3         # BGM（可选，默认用花叔曲库 educational）
"""
import argparse, subprocess, sys, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 工程目录 = film_dir
SKILL_SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(SKILL_SCRIPTS))
from assemble import assemble_segments               # ffmpeg 装配 + 混音

def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd)); sys.stdout.flush()
    return subprocess.run(cmd, check=True, **kw)

def render_segment(seg_name, film_js, out_mp4, fps, width=1920, height=1080):
    """单段:playwright 逐帧截图 → libx264。返回 None 成功,或抛异常。"""
    # 引用花叔引擎 lib(paint/rig/U) + 本段 main.js
    lib = SKILL_SCRIPTS / "lib"
    page_js = (lib / "page_template.js").read_text(encoding="utf-8")
    main = (ROOT / film_js).read_text(encoding="utf-8")
    html = f"""<!doctype html><html><head><meta charset=utf-8>
<style>html,body{{margin:0;background:#000}}canvas{{display:block}}</style></head>
<body><canvas id=c width={width} height={height}></canvas>
<script>{page_js}</script>
<script>{main}</script>
<script>window.__film='{seg_name}';window.__fps={fps};window.__boot();</script>
</body></html>"""
    tmp_html = Path("/tmp/_rv_" + seg_name + ".html"); tmp_html.write_text(html, encoding="utf-8")
    # node 截图服务(花叔 analyze 思路:CDP 批量截帧)
    srv = subprocess.Popen(["node", str(SKILL_SCRIPTS / "capture.mjs"),
                            str(tmp_html), out_mp4, str(fps), seg_name],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = []
    for line in srv.stdout: tail.append(line); print(line.rstrip())
    srv.wait()
    if srv.returncode != 0:
        raise RuntimeError(f"段 {seg_name} 截图失败,末行: {tail[-3:] if tail else '无输出'}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True, help="film 工程目录(含 main.js)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", help="输出 mp4(默认 <film>/output/成片.mp4)")
    ap.add_argument("--no-bgm", action="store_true", help="跳过 BGM 混音(纯口播)")
    args = ap.parse_args()
    global ROOT; ROOT = Path(args.film).resolve()
    fps = args.fps
    out = Path(args.out) if args.out else ROOT / "output" / "成片.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    # 1. 解析总时长与分段清单(main.js 需 set window.__total 且 __sceneList=['id1','id2',...])
    probe = subprocess.run(["node", str(SKILL_SCRIPTS / "probe.mjs"),
                            str(ROOT / "main.js")], capture_output=True, text=True)
    meta = json.loads(probe.stdout)
    total, segs = meta["total"], meta["scenes"]
    print(f"[render] 总时长 {total:.2f}s / {len(segs)} 段: {segs}")

    # 2. 逐段渲染(串行,避免 OOM;每段独立进程)
    seg_m4s = []
    for i, seg in enumerate(segs):
        sm4 = ROOT / "output" / f"seg_{i:02d}_{seg}.mp4"
        sm4.parent.mkdir(parents=True, exist_ok=True)
        if sm4.exists(): sm4.unlink()
        print(f"\n=== 段 {i+1}/{len(segs)}: {seg} ===")
        render_segment(seg, "main.js", str(sm4), fps)
        seg_m4s.append(sm4)

    # 3. 装配:concat 视频 + 口播 + BGM 混音
    voice = ROOT / "voiceover.mp3"
    bgm = None if args.no_bgm else (ROOT / "bgm.mp3")
    assemble_segments(seg_m4s, voice if voice.exists() else None,
                      bgm, str(out), fps)
    print(f"\n[done] 成片 → {out}  用时 {time.time()-t0:.0f}s")
    print("[next] 字幕 → python3 " + str(SKILL_SCRIPTS / "subtitle_pipeline.py") +
          f" --video {out} --srt <口播.srt>")

if __name__ == "__main__":
    main()
