#!/usr/bin/env node
/**
 * probe.mjs — 解析 film main.js 的总时长与分段清单（不渲染，只探测元信息）
 * 用法: node probe.mjs <main.js>
 * 输出 JSON: {"total": <秒>, "scenes": ["id1","id2",...]}
 * 要求 main.js 在浏览器环境设置 window.__total 与 window.__sceneList；
 * 这里用 vm 沙箱模拟最小 window 对象跑一遍顶层代码拿这两个值。
 */
import { readFileSync } from 'fs'
import vm from 'vm'

const mainPath = process.argv[2]
if (!mainPath) { console.error('usage: node probe.mjs <main.js>'); process.exit(1) }

const src = readFileSync(mainPath, 'utf-8')
const sandbox = {
  window: {},
  document: { getElementById: () => null, createElement: () => ({ getContext: () => null }) },
  console,
}
sandbox.window = sandbox
vm.createContext(sandbox)
try {
  vm.runInContext(src, sandbox, { filename: mainPath })
} catch (e) {
  // 顶层可能依赖 canvas/DOM，忽略运行错误，只要 __total/__sceneList 被赋值即可
}

const total = sandbox.__total
let scenes = sandbox.__sceneList
// 兼容:SCENES 对象键值对但没显式 __sceneList → 退化为 Object.keys(SCENES)
if (!scenes && sandbox.SCENES) scenes = Object.keys(sandbox.SCENES)
if (typeof total !== 'number' || total <= 0) {
  console.error(JSON.stringify({ error: 'main.js 未设置 window.__total(秒) 或值为非法', got: total }))
  process.exit(2)
}
if (!Array.isArray(scenes) || scenes.length === 0) {
  console.error(JSON.stringify({ error: 'main.js 未设置 window.__sceneList 数组(渲染顺序)', got: scenes }))
  process.exit(3)
}
console.log(JSON.stringify({ total, scenes }))
