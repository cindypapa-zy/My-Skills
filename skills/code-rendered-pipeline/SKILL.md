---
name: code-rendered-pipeline
description: 一键把 Canvas 2D 逐帧动画（花叔 huashu-art-motion 引擎）做成可发飞书的成片。当用户说"手搓一条视频""按上次那套出片""把这个动画做成视频""渲染+字幕+BGM+片头片尾一条龙"时用。覆盖渲染→字幕→BGM混音→片头片尾→飞书压缩五步，本机 brew ffmpeg 无 libass 特化，跨平台通用。
---

# 一键出片流水线（基于花叔引擎）

把「纯代码 Canvas 动画」一路推到「能发飞书的终版」。地基是花叔 `huashu-art-motion` 引擎 + 各 film 工程自带的 `render.py`（逐帧渲染器，接口 `window.prepare(t)`+`window.renderFrame(t)`，就绪标志 `window.__ready`/`__bootFailed`，画布 `window.__canvas`），本 skill **不重写渲染器**——那是花叔/工程自己的活，本 skill 补齐渲染之后、且咱们环境特有（brew ffmpeg 无 libass）的三步包装：**字幕 → 片头片尾 → 飞书压缩交付**，外加 BGM 混音模块（assemble.py）。

2026-10-08《月球矩阵》v1→v5 全程实测，每个数字背后都是一次翻车返工。别凭感觉改参数。

## 何时用

- 已有/要做一个 Canvas 2D 逐帧动画（`SCENES['id']={draw(c,lt,t)}`），想出带字幕、BGM、片头片尾的成片。
- 已有无声 HTML 动画，想配音 + 配乐 + 字幕 + 包装成可发飞书的终版。

不适用：AI 生图/生视频路线（走 seedance/guizang-material-seedream）；纯静态 PPT（走 baoyu-slide-deck）。

## 五步流水线（一键串联，也可单步重跑）

**渲染（步 0）用工程自带 render.py，本 skill 从步 1 开始包装。** 各步脚本在 `scripts/`，每步输出下一步的入口提示。

| 步 | 用谁 | 干什么 | 核心防线（踩过的坑） |
|---|---|---|---|
| 0 | **工程自带** `render.py` | Playwright 逐帧渲染 + 口播合成 | 接口 `prepare(t)`+`renderFrame(t)`；就绪 `__ready`/`__bootFailed`；分段渲防 OOM。本 skill 不管这步 |
| 1 | `scripts/assemble.py` | BGM 混音（多段口播已合成时）| Suno VBR 假时长；aloop 循环；过度闪避 ratio≥8 无声 |
| 2 | `scripts/subtitle_pipeline.py --video <mp4> --srt <srt>` | PIL 字幕条 + overlay 定时烧录 | **无 libass**：ass/drawtext 是死路，PIL 唯一解；全帧 PNG 卡死 overlay，只画 1920×140 底部条 |
| 3 | `scripts/title_cards.py --video <mp4> --title X --credits A,B,C` | 独立片头/尾片段拼接 | 不透明整卡（透明卡撞车）；时长变长，抽帧按新时间轴 |
| 4 | `scripts/compress.py --in <mp4>` | CRF 迭代压到飞书 30MB 内 | 硬限 31,457,280B；1080p 长片 CRF 27 起步 |

```bash
# 步 0：渲染（在 film 工程目录，用它自己的 render.py）
uv run --with playwright python render.py --out 成片.mp4 --film <名> [--audio 口播.wav]
# 步 1-4：本 skill 包装（字幕 → 片头片尾 → 压缩）
python3 <skill>/scripts/subtitle_pipeline.py --video 成片.mp4 --srt 口播.srt
python3 <skill>/scripts/title_cards.py --video 字幕版.mp4 --title 月球矩阵 --credits 感谢收看,出品：示例团队
python3 <skill>/scripts/compress.py --in 片头片尾版.mp4
```

**单步重跑**：改字幕只重跑 2；改片头片尾只重跑 3；只是要发飞书只重跑 4。BGM 混音（assemble.py）独立成模块，多段口播合成后调用。

## 渲染器契约（工程自带 render.py，本 skill 不实现）

film 工程的 `render.py` 是渲染唯一入口，接口（月球矩阵 2026-10-07 实测）：
- 逐帧钩子：`window.prepare(t)` 准备 → `window.renderFrame(t)` 画到 `window.__canvas`
- 就绪/报错：`window.__ready===true` 可渲；`window.__bootFailed` 非空则拒渲染
- 选段：`--film <名>` 读 `eras_<名>.js`；`--solo <id>` 只渲某段（段本地时间）；`--spec clip.json` 参数化片段
- 出片：`-f image2pipe` 逐帧 PNG 送 ffmpeg `-c:v libx264 -crf 14`；`--audio 口播.wav` 自动合音轨；`--stills t1,t2` 出静帧
- 每段口播独立 `音频/s*.wav`，逐段渲逐段合（不是单 voiceover.mp3）

film 作者只管写画段（`SCENES`/`draw`），渲染器由工程/花叔维护。**本 skill 的 render_video.py 是早期接口假设版（`__seek`/`__booted`/`getElementById('c')`），与上述真实接口不符，未在真实工程验证，不要用**——渲染一律走工程自带 render.py。

## 四条铁律（改任何参数前重读）

1. **字幕只走 PIL 字幕条**（步 2）。本机 ffmpeg 无 libass/drawtext，`ass`/`subtitles`/`drawtext` 滤镜全不存在，别试。全帧 PNG 多路 overlay 实测卡死——只画底部 1920×140 一条。深色画面用白字黑边（dark 样式），白板浅底用深字白边（light 样式），`--style auto` 按首帧亮度猜。

2. **BGM 信真实时长，不信文件头**（步 1 assemble）。Suno 等 VBR mp3 头会虚报（标 163.7s 实际 22.7s），`ffprobe format=duration` 直接读 mp3 被骗——必须先解码到 wav 再量。短于成片一律 `aloop` 循环铺满（先循环后裁剪），绝不中途 EOF 留白尾（用户会当 bug 报"28 秒后没音乐"）。

3. **sidechain 闪避别过度**（步 1 assemble）。`ratio≥8` 或 `threshold<0.01` 会把 BGM 压到约 -45dB 实质无声。已验证安全区：`threshold=0.02:ratio=3:attack=20:release=500:makeup=1`。

4. **片头片尾走独立片段拼接，卡必须不透明**（步 3）。「加到开头结尾」= 独立卡片段 + 原片拼接（时长变长，默认）；只有用户明确要"叠在原画面上"才走叠加。不透明底整卡——透明卡叠在自带文字的场景上会撞车（实测标题压火柴人、片尾糊在结尾大字上）。

## 关键实测数值锚点（月球矩阵 123.6s 1080p30）

| 项 | 值 | 来源 |
|---|---|---|
| BGM 预压目标 RMS | -28dBFS 起步（-22 嫌响） | 用户连续两轮调轻 |
| BGM 预压 volume（成品曲 RMS -16dB） | 0.20~0.35（0.5 嫌响） | 同上 |
| 真实时长（Suno） | educational 22.7s / -alt 41.3s / tutorial 43.0s | 头标 163/185/230s 全虚报 |
| 混音链 | `aloop→atrim→afade(in0.3/out3s)→volume→sidechain(th0.02:r3)→amix normalize=0` | 三次返工定版 |
| 飞书压缩 | 1080p 长片 CRF 27≈29.3MB；CRF 24=44MB 超限；硬限 31,457,280B | video-subtitle-burn |
| 卡片段 | 4s 片头 + 5s 片尾，anullsrc 静音，fade 0.5，参数对齐 yuv420p/30fps/48kHz | v5 终版 |

## 验收（缺一层不交付）

- **步 1 后**：`assemble.verify_mix` 三层——①BGM 每 10s 窗口 RMS 在位（抓半路 EOF）②语音空隙段混音 RMS 比纯口播高 2-6dB（BGM 可闻）③全片峰值 ≤ -3dB（防削波）。
- **步 2/3 后**：view_image 抽帧核——字幕清晰不压画面、片头片尾卡文字完整无撞车、原片内容未被卡片误盖。
- **步 5 后**：`size_of ≤ 31,457,280`；message 一次只带 1 个 attachment。

## ⚙️ 本机适配（本机 · Linux 2026-10-08 实测）

本包原生于 macOS，移植到 Linux 时踩了两个坑，已修：

| 坑 | 现象 | 本机修法 |
|---|---|---|
| **ffmpeg 二进制选错** | PATH 里 `/usr/bin/ffmpeg`（系统自带旧版）**无 libx264**，渲染报 `Encoder not found` | 加了 shim `~/.local/bin/ffmpeg` → `exec /usr/local/bin/ffmpeg`（git-2026-06-01，带 libx264）。确保 `~/.local/bin` 在 PATH 中即可全局生效 |
| **中文字体硬编码 macOS** | `subtitle_pipeline.py`/`title_cards.py` 写死 `/System/Library/Fonts/Hiragino Sans GB.ttc`，Linux 报 `OSError: cannot open resource` | 改为 `_pick_font()` 跨平台探测：先扫 Noto CJK，回退 macOS 字体。本机命中 `/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc` |

**本机 ≠ 原 macOS 机的关键差异**：本机 `/usr/bin/ffmpeg` **有 libass / drawtext / subtitles**（OpenCloudOS 编译带 `--enable-libass`）。所以四条铁律第 1 条「无 libass」在**本机不成立**——ass/drawtext 路线**可用**，但 PIL 字幕条路线已实测通过，沿用即可，不必改。

**本机实测数值（务必替换 SKILL 里的原机锚点）**：

| 项 | 原文档（macOS） | 本机本机（实测 2026-10-08） |
|---|---|---|
| ffmpeg | brew 8.0.1，无 libass | `/usr/local/bin` = git-2026-06-01（libx264 ✅）；`/usr/bin` = 7.0.2（libass ✅ 无 x264） |
| 中文字体 | Hiragino Sans GB | Noto Sans/Serif CJK（60 个 face） |
| 渲染分辨率 | 1920×1080 | 同上（render.py 默认 viewport） |
| 2s/60帧 solo 渲染耗时 | — | ≈ 20 秒（含浏览器启动） |
| PIL / numpy | — | 12.3.0 / 2.4.2 |
| Playwright | Playwright（未记版本） | Python 包已装 + chromium-1208/1217 已下载 ✅ |

五步流水线**本机已逐条打通**：render.py 冒烟（2s 1920×1080 h264 60帧）→ subtitle_pipeline（PIL 字幕条烧录）→ title_cards（片头片尾拼接，时长核验 11.0s≈期望）→ compress（CRF 27 → 1.3MB ✅ 达标）。

## 依赖

- 花叔 `huashu-art-motion` skill（引擎 + lib + 风格配方）——本 skill 的 `scripts/lib` 首次运行时软链过来，勿手改。
- **本机 ffmpeg 走 `/usr/local/bin`（libx264）**，别用 `/usr/bin`。原文档写的 `brew ffmpeg 8.0.1` 是原 macOS 机的情况；Linux 下 libass 反而齐备。
- `node`（Playwright 截图）、`PIL`、`numpy`。
- BGM 曲库：花叔 `huashu-design/assets/bgm-<mood>.mp3`（6 首，MIT，Suno 生成）。

## 已知边界

- **渲染步（步 0）不在本 skill**：各 film 工程自带 render.py（接口见上节），本 skill 专注渲染之后的字幕/片头片尾/压缩包装。render_video.py/capture.mjs/probe.mjs 是接口假设版，与真实工程接口不符，留作参考勿直接用。
- 渲染串行（一段一个进程），未做并行——21 段 123s 片约 15-20 分钟；要更快需防 OOM（实测 21 张大图 PIL 一次性处理被 macOS SIGKILL）。
- 字幕样式只分 dark/light 两档，未做逐句自适应——多数片够用了。
- BGM 循环接缝在低音量 + 闪避掩护下不可闻（v3 实测），若用户明确反感循环声再换长曲或做 crossfade。

## 参考

- `references/端到端流水线.md` — 完整命令序列 + 路线 B（叠加片头片尾）+ 故障排查速查。
- 花叔 `huashu-art-motion` 的 `references/12-口播整片与经验回流.md` — 引擎细节 + 字幕心得原始沉淀。
