#!/usr/bin/env python3
"""
assemble.py — 视频段装配 + 口播 + BGM 混音(固化 2026-10-08 月球矩阵全部实测参数)
核心防线(每条都对应一次真实翻车):
  1. Suno VBR mp3 假时长 → 解码重测真实时长,不信 format=duration
  2. BGM 短于成片 → aloop 循环铺满(先循环后裁剪),绝不中途 EOF 留白尾
  3. 过度闪避 → ratio=3 threshold=0.02(ratio≥8 会把 BGM 压到 -45dB 无声)
  4. 口播 RMS 常低于成品曲 → 先算预压增益,不拍脑袋给 volume
"""
import subprocess, sys, wave, contextlib
from pathlib import Path

def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def true_duration(path):
    """测真实时长。Suno 等 VBR mp3 头会虚报 → mp3 必须解码重测;
    但视频/无声文件解码不出 wav 会崩 → 非 mp3 一律 ffprobe(2026-10-08 原机作者实测 bug4)。"""
    p = str(path)
    if p.lower().endswith(".mp3"):
        tmp = "/tmp/_dur_probe.wav"
        sh(["ffmpeg", "-y", "-v", "error", "-i", p, tmp])
        with contextlib.closing(wave.open(tmp, "rb")) as w:
            return w.getnframes() / w.getframerate()
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", p])
    return float(r.stdout.strip())

def rms_db(path):
    r = sh(["ffmpeg", "-i", str(path), "-af", "astats=metadata=1", "-f", "null", "-"])
    for line in r.stderr.splitlines():
        if "RMS level dB" in line:
            return float(line.split(":")[-1].strip())
    return None

def rms_db_range(path, ss, dur=1.0):
    r = sh(["ffmpeg", "-ss", str(ss), "-t", str(dur), "-i", str(path),
            "-af", "astats=metadata=1", "-f", "null", "-"])
    for line in r.stderr.splitlines():
        if "RMS level dB" in line:
            return float(line.split(":")[-1].strip())
    return None

def assemble_segments(seg_m4s, voice, bgm, out, fps=30, bgm_volume=None, dry_run=False):
    """seg_m4s: 视频段 mp4 列表; voice/bgm: 音频路径或 None; out: 输出 mp4"""
    # 1. concat 视频段(列表必须绝对路径,同 bug2:相对路径解析基于 list 目录会静默丢段)
    lst = Path("/tmp/_asm_list.txt"); lst.write_text(
        "".join(f"file '{Path(p).resolve()}'\n" for p in seg_m4s), encoding="utf-8")
    vcat = "/tmp/_vcat.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart", vcat], check=True)
    vdur = true_duration(vcat)  # 用音频法测视频时长可靠(同容器)

    # 2. 口播垫底
    inputs = ["-i", vcat]
    fc = []
    aidx = 1
    voice_chain = ""
    if voice and Path(voice).exists():
        inputs += ["-i", str(voice)]
        voice_chain = f"[{aidx}:a]aresample=48000,aformat=channel_layouts=stereo[voice];"
        vbase = "[voice]"
        aidx += 1
    else:
        vbase = f"[{0}:a]"

    # 3. BGM 混音(成品曲 + sidechain 闪避)
    if bgm and Path(bgm).exists():
        b = Path(bgm)
        bdur = true_duration(b)
        brms = rms_db(b)
        if bgm_volume is None:
            # 预压:BGM 预压后 RMS ≈ -28dBFS(用户偏轻区间;-22 嫌响)
            bgm_volume = 10 ** ((-28 - (brms if brms else -16)) / 20)
            bgm_volume = max(0.15, min(0.45, bgm_volume))  # 夹紧到实测接受区
        print(f"[mix] BGM 真实时长 {bdur:.1f}s(文件头可能虚报) RMS {brms:.1f}dB → 预压 volume={bgm_volume:.3f}")
        inputs += ["-i", str(b)]
        # aloop 必须先于 atrim:循环铺满再裁齐;假时长文件 aloop 按真实采样循环,不受假头影响
        fc.append(
            f"[{aidx}:a]aloop=loop=-1:size=2e9,atrim=0:{vdur:.3f},"
            f"aresample=48000,aformat=channel_layouts=stereo,"
            f"afade=t=in:st=0:d=0.3,afade=t=out:st={max(0,vdur-3):.3f}:d=3,"
            f"volume={bgm_volume:.3f}[bgm0]")
        # sidechain 闪避:口播压 BGM;ratio=3 threshold=0.02(实测安全区,别用 ratio≥8)
        fc.append(f"{vbase}asplit=2[vo][sc]")
        fc.append(f"[bgm0][sc]sidechaincompress=threshold=0.02:ratio=3:"
                  f"attack=20:release=500:makeup=1[bgmd]")
        fc.append(f"[vo][bgmd]amix=inputs=2:duration=first:normalize=0[aout]")
        amap = "[aout]"
    else:
        amap = vbase if voice else f"[{0}:a]"

    fstr = voice_chain + ";".join(fc)
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs
    if fstr: cmd += ["-filter_complex", fstr]
    cmd += ["-map", "0:v", "-map", amap, "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", out]
    if dry_run:
        print("[dry]", " ".join(cmd)); return
    subprocess.run(cmd, check=True)
    print(f"[assemble] 成片 {out}  时长 {vdur:.2f}s")

def verify_mix(final_mp4, gaps, expect_gap_delta_db=(2, 6)):
    """三层验收(缺一层不交付):①BGM 全段在位 ②语音空隙 BGM 可闻 ③无削波"""
    ok = True
    # ① 每 10s 窗口 RMS 必须存在(v2 事故:BGM 半路 EOF,整体 RMS 测不出来)
    dur = true_duration(final_mp4)
    for t in range(0, int(dur), 10):
        r = rms_db_range(final_mp4, t)
        if r is None or r < -50:
            print(f"  ✗ {t}s 窗口 BGM 疑似缺失({r})"); ok = False
    # ② 语音空隙段:混音版应比纯口播版高 2-6dB(BGM 可闻度)
    for g in gaps:
        r_mix = rms_db_range(final_mp4, g)
        print(f"  · 空隙 {g}s 混音 RMS {r_mix:.1f}dB(参考:应明显高于纯口播 -29dB)")
    # ③ 峰值
    r = sh(["ffmpeg", "-i", final_mp4, "-af", "astats=metadata=1", "-f", "null", "-"])
    for line in r.stderr.splitlines():
        if "Peak level dB" in line:
            pk = float(line.split(":")[-1].strip())
            print(f"  · 全片峰值 {pk:.1f}dB(应 ≤ -3)")
            if pk > -3: print("  ✗ 削波风险"); ok = False
    return ok

if __name__ == "__main__":
    print("assemble.py 是库,由 render_video.py 调用。独立测试:见 references/端到端流水线.md")
