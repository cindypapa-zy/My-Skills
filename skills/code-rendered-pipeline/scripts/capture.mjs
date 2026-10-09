#!/usr/bin/env node
/**
 * capture.mjs — Playwright 逐帧截图服务（render_video.py 的核心渲染引擎）
 * 用法: node capture.mjs <html> <out_mp4> <fps> <segment_id>
 * 流程:
 *   1. 启动 chromium headless,加载含 Canvas 动画的 HTML
 *   2. 读取 window.__bootErrors(非空则拒启动,退出 2)
 *   3. 读 window.__total(该段总秒)→ 算总帧数
 *   4. 逐帧:for(t=0; t<total; t+=1/fps) 调 window.__seek(t) 定位 → canvas.toDataURL('image/png') 截图
 *      (用 __seek 而非 rAF 自驱,保证逐帧确定性、可重现、不受机器快慢影响)
 *   5. 每帧 PNG 落盘 /tmp/_cap_<seg>_NNNNNN.png
 *   6. 调 ffmpeg -framerate <fps> -i /tmp/_cap_<seg>_%06d.png -c:v libx264 → out_mp4
 * 依赖: playwright(chromium)、ffmpeg。帧 PNG 尺寸大,分段渲染防 OOM(月球矩阵实测)。
 */
import { chromium } from 'playwright'
import { execFileSync } from 'child_process'
import { writeFileSync, unlinkSync, existsSync } from 'fs'
import { join } from 'path'

const [htmlPath, outMp4, fpsArg, segId] = process.argv.slice(2)
const FPS = parseInt(fpsArg || '30', 10)
if (!htmlPath || !outMp4) { console.error('usage: node capture.mjs <html> <out_mp4> <fps> <seg_id>'); process.exit(1) }

const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu'] })
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
  page.on('console', m => { if (m.type() === 'error') console.error('[page]', m.text()) })
  page.on('pageerror', e => console.error('[pageerror]', e.message))

  await page.goto('file://' + htmlPath, { waitUntil: 'load' })
  await page.waitForFunction('window.__booted === true || window.__bootErrors', { timeout: 15000 })

  const boot = await page.evaluate('window.__bootErrors || null')
  if (boot && boot.length) { console.error('BOOT_ERRORS', JSON.stringify(boot)); process.exit(2) }

  const total = await page.evaluate('window.__total')
  if (typeof total !== 'number' || total <= 0) { console.error('window.__total 非法:', total); process.exit(3) }
  const nFrames = Math.round(total * FPS)
  console.log(`[capture] 段 ${segId} 总时长 ${total}s / ${nFrames} 帧 @${FPS}fps`)

  const tmpPattern = `/tmp/_cap_${segId}`
  // 逐帧 __seek + 截图(确定性时序,比 rAF 自驱稳)
  for (let i = 0; i < nFrames; i++) {
    const t = i / FPS
    await page.evaluate(`window.__seek && window.__seek(${t})`)
    const png = await page.evaluate(`document.getElementById('c').toDataURL('image/png')`)
    writeFileSync(`${tmpPattern}_${String(i).padStart(6, '0')}.png`, Buffer.from(png.split(',')[1], 'base64'))
    if (i % 60 === 0) console.log(`[capture] ${segId} ${i}/${nFrames}`)
  }

  // 装配成 mp4
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-framerate', String(FPS),
    '-i', `${tmpPattern}_%06d.png`, '-c:v', 'libx264', '-crf', '21',
    '-preset', 'medium', '-pix_fmt', 'yuv420p', outMp4], { stdio: 'inherit' })

  // 清帧 PNG(不留垃圾)
  for (let i = 0; i < nFrames; i++) { const f = `${tmpPattern}_${String(i).padStart(6, '0')}.png`; if (existsSync(f)) unlinkSync(f) }
  console.log(`[capture] 段 ${segId} 完成 → ${outMp4}`)
} finally {
  await browser.close()
}
