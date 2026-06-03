# Phase 2：前端 SPA（React + Vite + TypeScript）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `E:\OCR-Work-platform\frontend` 建一個 React + Vite + TS 單頁前端，串接 Phase 1 的 FastAPI 後端（:8000），完整重現兩步驟流程：選檔→縮圖預覽確認→非同步辨識（顯示進度、完成自動跳轉）→原圖對照＋線上編輯→下載同名 .txt。

**Architecture:** 薄前端：`api.ts` 包後端 6 端點（dev 走 Vite proxy `/api`→:8000）；純函式 `lib/combine.ts`（同名 .txt 組裝）與 `state.ts`（useReducer）做 TDD；UI 拆成 `StepNav`/`Step1Upload`/`Step2Edit`/`ZoomImage`。對應 spec：`docs/superpowers/specs/2026-06-03-frontend-backend-split-design.md`（§6 前端）。

**Tech Stack:** React 18/19、Vite、TypeScript（strict）、Vitest＋jsdom＋@testing-library/react。

> **環境備註：**
> - 工作目錄 `E:\OCR-Work-platform`（git 倉庫）。前端在 `frontend\`。
> - 需要 Node.js / npm（已安裝）。`npm install` / `npm create` 需網路：用 Bash tool 並設 `dangerouslyDisableSandbox=true`。
> - 指令從 `E:\OCR-Work-platform\frontend` 執行。`npm run build`＝型別檢查＋打包（gate）；`npm test`＝`vitest run`。
> - 後端 API 契約（已實作）：`POST /api/jobs`(multipart `file`→JobMeta)、`GET /api/jobs/{id}/pages/{n}/image`(PNG)、`POST /api/jobs/{id}/recognize`(→{job_id,status})、`GET /api/jobs/{id}`(JobStatus)、`DELETE /api/jobs/{id}`(204)。
> - 不要提交 `node_modules`、`dist`（Task 1 會補 .gitignore）。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `frontend/` (Vite react-ts 樣板) | package.json、tsconfig、index.html、src/main.tsx |
| `frontend/vite.config.ts` | react plugin、dev proxy `/api`→:8000、vitest（jsdom）設定 |
| `frontend/src/types.ts` | `JobMeta` / `Progress` / `JobStatus` 型別 |
| `frontend/src/lib/combine.ts` | `combinePages()`（同名 .txt 組裝，純函式） |
| `frontend/src/api.ts` | 後端 6 端點的 typed client |
| `frontend/src/state.ts` | `AppState` / `Action` / `reducer` / `initialState`（純） |
| `frontend/src/components/StepNav.tsx` | 兩步驟分頁列（可控、完成才可進步驟2） |
| `frontend/src/components/ZoomImage.tsx` | 滾輪縮放／拖曳／雙擊還原的原圖 |
| `frontend/src/components/Step1Upload.tsx` | 選檔／縮圖預覽／辨識／輪詢／自動跳轉 |
| `frontend/src/components/Step2Edit.tsx` | 原圖對照／線上編輯／下載／重置 |
| `frontend/src/App.tsx` + `App.css` | 組裝、標題、依 step 顯示 |
| `frontend/src/*.test.ts(x)` | Vitest 測試 |
| `frontend/run_frontend.bat` | 啟動 dev（:5173） |

---

## Task 1：Vite React-TS 腳手架＋測試環境＋設定＋型別

**Files:** Create `frontend/`（樣板）、`frontend/vite.config.ts`（覆寫）、`frontend/src/types.ts`、`frontend/.gitignore` 確認

- [ ] **Step 1: 建立 Vite 樣板**（Bash，dangerouslyDisableSandbox=true）

Run: `cd /d E:\OCR-Work-platform && npm create vite@latest frontend -- --template react-ts`
Expected: 在 `E:\OCR-Work-platform\frontend` 產生樣板（package.json、src/main.tsx、src/App.tsx 等）。

- [ ] **Step 2: 安裝相依（含測試）**（Bash，dangerouslyDisableSandbox=true）

Run: `cd /d E:\OCR-Work-platform\frontend && npm install && npm install -D vitest jsdom @testing-library/react @testing-library/dom`
Expected: 安裝成功。

- [ ] **Step 3: 加 test script**

把 `frontend/package.json` 的 `"scripts"` 區塊改為包含 test（保留樣板既有的 dev/build/preview/lint，僅新增 `"test"`）：
```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run"
}
```

- [ ] **Step 4: 覆寫 `frontend/vite.config.ts`**

```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
```

- [ ] **Step 5: 建立 `frontend/src/types.ts`**

```ts
export interface JobMeta {
  job_id: string
  file_name: string
  n_pages: number
  is_born_digital: boolean
  status: string
}

export interface Progress {
  message: string
  percent: number
}

export interface JobStatus {
  job_id: string
  file_name: string
  n_pages: number
  is_born_digital: boolean
  status: 'created' | 'running' | 'done' | 'error'
  progress: Progress | null
  mode: string | null
  pages: Record<string, string> | null
  error: string | null
}
```

- [ ] **Step 6: 確認 `frontend/.gitignore` 含 node_modules 與 dist**

Vite 樣板已產生 `frontend/.gitignore`（含 `node_modules`、`dist`）。用 Read 確認；若缺，補上 `node_modules` 與 `dist` 兩行。

- [ ] **Step 7: 型別檢查＋打包通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功（tsc 無錯、vite build 產出 dist）。

- [ ] **Step 8: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend
git commit -m "feat(web): scaffold React+Vite+TS frontend + vitest + proxy + types"
```
（`node_modules`/`dist` 已被 frontend/.gitignore 忽略，不會進版控。）

---

## Task 2：combinePages（同名 .txt 組裝，純函式 TDD）

**Files:** Create `frontend/src/lib/combine.ts`、`frontend/src/lib/combine.test.ts`

- [ ] **Step 1: 寫失敗測試 `frontend/src/lib/combine.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { combinePages } from './combine'

describe('combinePages', () => {
  it('single page returns plain text', () => {
    expect(combinePages({ 1: 'hello' })).toBe('hello')
  })
  it('multi page adds headers', () => {
    const out = combinePages({ 1: 'a', 2: 'b' })
    expect(out).toContain('===== 第 1 頁 =====')
    expect(out).toContain('===== 第 2 頁 =====')
    expect(out).toContain('a')
    expect(out).toContain('b')
  })
  it('empty returns empty string', () => {
    expect(combinePages({})).toBe('')
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（找不到 `./combine`）

- [ ] **Step 3: 實作 `frontend/src/lib/combine.ts`**

```ts
/** {pageNo: text} → 下載用全文。單頁回純文字；多頁加 '===== 第 N 頁 ====='。 */
export function combinePages(pages: Record<number, string>): string {
  const keys = Object.keys(pages).map(Number).sort((a, b) => a - b)
  if (keys.length === 0) return ''
  if (keys.length === 1) return pages[keys[0]]
  return keys.map((k) => `===== 第 ${k} 頁 =====\n${pages[k]}`).join('\n\n')
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/lib/combine.ts frontend/src/lib/combine.test.ts
git commit -m "feat(web): combinePages (same-name txt assembly)"
```

---

## Task 3：API client（typed，mock fetch TDD）

**Files:** Create `frontend/src/api.ts`、`frontend/src/api.test.ts`

- [ ] **Step 1: 寫失敗測試 `frontend/src/api.test.ts`**

```ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import * as api from './api'

afterEach(() => { vi.restoreAllMocks() })

describe('api', () => {
  it('createJob posts multipart and returns meta', async () => {
    const meta = { job_id: 'x', file_name: 'f.pdf', n_pages: 1, is_born_digital: true, status: 'created' }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => meta })
    vi.stubGlobal('fetch', fetchMock)
    const f = new File([new Uint8Array([1])], 'f.pdf', { type: 'application/pdf' })
    const res = await api.createJob(f)
    expect(res).toEqual(meta)
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs', expect.objectContaining({ method: 'POST' }))
  })

  it('getStatus fetches job by id', async () => {
    const st = { job_id: 'x', status: 'done' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => st }))
    const res = await api.getStatus('x')
    expect(res.status).toBe('done')
  })

  it('pageImageUrl builds url', () => {
    expect(api.pageImageUrl('x', 2)).toBe('/api/jobs/x/pages/2/image')
  })

  it('createJob throws on http error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }))
    const f = new File([new Uint8Array([1])], 'f.pdf')
    await expect(api.createJob(f)).rejects.toThrow()
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（找不到 `./api`）

- [ ] **Step 3: 實作 `frontend/src/api.ts`**

```ts
import type { JobMeta, JobStatus } from './types'

const BASE = '/api'

export async function createJob(file: File): Promise<JobMeta> {
  const fd = new FormData()
  fd.append('file', file)
  const r = await fetch(`${BASE}/jobs`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error(`上傳失敗 (${r.status})`)
  return r.json()
}

export async function startRecognize(jobId: string): Promise<{ job_id: string; status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/recognize`, { method: 'POST' })
  if (!r.ok) throw new Error(`辨識啟動失敗 (${r.status})`)
  return r.json()
}

export async function getStatus(jobId: string): Promise<JobStatus> {
  const r = await fetch(`${BASE}/jobs/${jobId}`)
  if (!r.ok) throw new Error(`查詢失敗 (${r.status})`)
  return r.json()
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${BASE}/jobs/${jobId}`, { method: 'DELETE' })
}

export function pageImageUrl(jobId: string, page: number): string {
  return `${BASE}/jobs/${jobId}/pages/${page}/image`
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（combine 3 ＋ api 4 = 7 passed）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(web): typed API client"
```

---

## Task 4：App 狀態（reducer，純函式 TDD）

**Files:** Create `frontend/src/state.ts`、`frontend/src/state.test.ts`

- [ ] **Step 1: 寫失敗測試 `frontend/src/state.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { reducer, initialState } from './state'
import type { JobMeta } from './types'

const META: JobMeta = { job_id: 'j', file_name: 'f.pdf', n_pages: 2, is_born_digital: false, status: 'created' }

describe('reducer', () => {
  it('SET_META stores meta and resets page/edited/status', () => {
    const s = reducer({ ...initialState, curPage: 3, edited: { 1: 'x' } }, { type: 'SET_META', meta: META })
    expect(s.meta).toEqual(META)
    expect(s.curPage).toBe(1)
    expect(s.edited).toEqual({})
    expect(s.status).toBeNull()
  })
  it('EDIT updates one page', () => {
    const s = reducer(initialState, { type: 'EDIT', page: 2, text: 'hi' })
    expect(s.edited[2]).toBe('hi')
  })
  it('GO switches step', () => {
    expect(reducer(initialState, { type: 'GO', step: 2 }).step).toBe(2)
  })
  it('RESET returns initial', () => {
    const dirty = reducer(initialState, { type: 'EDIT', page: 1, text: 'x' })
    expect(reducer(dirty, { type: 'RESET' })).toEqual(initialState)
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（找不到 `./state`）

- [ ] **Step 3: 實作 `frontend/src/state.ts`**

```ts
import type { JobMeta, JobStatus } from './types'

export interface AppState {
  step: 1 | 2
  meta: JobMeta | null
  status: JobStatus | null
  curPage: number
  edited: Record<number, string>
}

export type Action =
  | { type: 'SET_META'; meta: JobMeta | null }
  | { type: 'SET_STATUS'; status: JobStatus | null }
  | { type: 'SET_PAGE'; page: number }
  | { type: 'EDIT'; page: number; text: string }
  | { type: 'GO'; step: 1 | 2 }
  | { type: 'RESET' }

export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, edited: {},
}

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'SET_META':
      return { ...s, meta: a.meta, status: null, edited: {}, curPage: 1 }
    case 'SET_STATUS':
      return { ...s, status: a.status }
    case 'SET_PAGE':
      return { ...s, curPage: a.page }
    case 'EDIT':
      return { ...s, edited: { ...s.edited, [a.page]: a.text } }
    case 'GO':
      return { ...s, step: a.step }
    case 'RESET':
      return initialState
  }
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（7 ＋ 4 = 11 passed）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/state.ts frontend/src/state.test.ts
git commit -m "feat(web): app reducer/state"
```

---

## Task 5：UI 元件（StepNav / ZoomImage / Step1Upload / Step2Edit）

**Files:** Create `frontend/src/components/StepNav.tsx`、`ZoomImage.tsx`、`Step1Upload.tsx`、`Step2Edit.tsx`

- [ ] **Step 1: `frontend/src/components/StepNav.tsx`**

```tsx
import type { Dispatch } from 'react'
import type { AppState, Action } from '../state'

const LABELS = ['①　選擇檔案 / 預覽 / 辨識', '②　結果與對照編輯']

export function StepNav({ state, dispatch }: { state: AppState; dispatch: Dispatch<Action> }) {
  const canStep2 = state.status?.status === 'done'
  return (
    <div className="stepnav">
      {[1, 2].map((n) => {
        const cur = state.step === n
        const reachable = n === 1 || canStep2
        return (
          <button
            key={n}
            className={cur ? 'tab active' : 'tab'}
            disabled={!reachable && !cur}
            onClick={() => reachable && !cur && dispatch({ type: 'GO', step: n as 1 | 2 })}
          >
            {LABELS[n - 1]}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: `frontend/src/components/ZoomImage.tsx`**

```tsx
import { useRef, useState } from 'react'
import type { WheelEvent, MouseEvent } from 'react'

export function ZoomImage({ src, alt }: { src: string; alt: string }) {
  const [scale, setScale] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  function onWheel(e: WheelEvent) {
    e.preventDefault()
    const r = box.current!.getBoundingClientRect()
    const mx = e.clientX - r.left
    const my = e.clientY - r.top
    const ns = Math.max(0.5, Math.min(20, scale * (1 - e.deltaY * 0.002)))
    const k = ns / scale
    setPos((p) => ({ x: mx - (mx - p.x) * k, y: my - (my - p.y) * k }))
    setScale(ns)
  }
  function onDown(e: MouseEvent) { drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y } }
  function onMove(e: MouseEvent) {
    if (drag.current) setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y })
  }
  function onUp() { drag.current = null }
  function onDouble() { setScale(1); setPos({ x: 0, y: 0 }) }

  return (
    <div
      ref={box}
      className="zoom"
      onWheel={onWheel}
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={onUp}
      onMouseLeave={onUp}
      onDoubleClick={onDouble}
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        style={{ transform: `translate(${pos.x}px,${pos.y}px) scale(${scale})`, transformOrigin: '0 0' }}
      />
      <span className="zhint">{scale.toFixed(2)}x — 滾輪縮放 · 拖曳 · 雙擊還原</span>
    </div>
  )
}
```

- [ ] **Step 3: `frontend/src/components/Step1Upload.tsx`**

```tsx
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, Dispatch } from 'react'
import type { AppState, Action } from '../state'
import * as api from '../api'

export function Step1Upload({ state, dispatch }: { state: AppState; dispatch: Dispatch<Action> }) {
  const { meta } = state
  const [busy, setBusy] = useState(false)
  const [recognizing, setRecognizing] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setErr(null)
    setBusy(true)
    try {
      const m = await api.createJob(file)
      dispatch({ type: 'SET_META', meta: m })
    } catch (ex) {
      setErr(String(ex))
    } finally {
      setBusy(false)
    }
  }

  async function onRecognize() {
    if (!meta) return
    setErr(null)
    setRecognizing(true)
    try {
      await api.startRecognize(meta.job_id)
    } catch (ex) {
      setErr(String(ex))
      setRecognizing(false)
    }
  }

  useEffect(() => {
    if (!recognizing || !meta) return
    timer.current = window.setInterval(async () => {
      try {
        const s = await api.getStatus(meta.job_id)
        dispatch({ type: 'SET_STATUS', status: s })
        if (s.status === 'done') {
          setRecognizing(false)
          dispatch({ type: 'GO', step: 2 })
        } else if (s.status === 'error') {
          setRecognizing(false)
          setErr(s.error ?? '辨識失敗')
        }
      } catch (ex) {
        setRecognizing(false)
        setErr(String(ex))
      }
    }, 600)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [recognizing, meta, dispatch])

  return (
    <section className="step">
      <h2>步驟 1　選擇檔案 → 預覽確認 → 進行辨識</h2>
      <input
        type="file"
        accept=".pdf,.jpg,.jpeg,.png,.webp"
        onChange={onFile}
        disabled={busy || recognizing}
      />
      {err && <p className="error">❌ {err}</p>}
      {meta && (
        <>
          <p className="info">
            {meta.is_born_digital
              ? `🔎 內含文字層（born-digital）→ 直接擷取文字層（${meta.n_pages} 頁）。`
              : `🔎 掃描影像／截圖 → PaddleOCR ＋ DeepSeek（${meta.n_pages} 頁）。`}
          </p>
          {meta.n_pages > 1 && (
            <label>
              預覽頁碼：
              <select
                value={state.curPage}
                onChange={(e) => dispatch({ type: 'SET_PAGE', page: Number(e.target.value) })}
              >
                {Array.from({ length: meta.n_pages }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
          )}
          <div className="thumb">
            <img src={api.pageImageUrl(meta.job_id, state.curPage)} alt={`第 ${state.curPage} 頁`} />
          </div>
          <button className="primary" onClick={onRecognize} disabled={recognizing}>
            {recognizing ? '辨識中…' : '✅ 確認無誤，開始辨識'}
          </button>
          {recognizing && state.status?.progress && (
            <p className="progress">
              {state.status.progress.message}（{state.status.progress.percent}%）
            </p>
          )}
        </>
      )}
    </section>
  )
}
```

- [ ] **Step 4: `frontend/src/components/Step2Edit.tsx`**

```tsx
import type { Dispatch } from 'react'
import type { AppState, Action } from '../state'
import * as api from '../api'
import { ZoomImage } from './ZoomImage'
import { combinePages } from '../lib/combine'

export function Step2Edit({ state, dispatch }: { state: AppState; dispatch: Dispatch<Action> }) {
  const { meta, status } = state
  if (!status || !status.pages) {
    return (
      <section className="step">
        <p>尚無辨識結果，請回步驟 1。</p>
      </section>
    )
  }
  const pages = status.pages
  const pnos = Object.keys(pages).map(Number).sort((a, b) => a - b)
  const page = pnos.includes(state.curPage) ? state.curPage : pnos[0]
  const cur = state.edited[page] ?? pages[String(page)]

  function download() {
    const final: Record<number, string> = {}
    for (const p of pnos) final[p] = state.edited[p] ?? pages[String(p)]
    const blob = new Blob([combinePages(final)], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = (meta?.file_name?.replace(/\.[^.]+$/, '') || 'result') + '.txt'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function reset() {
    if (meta) await api.deleteJob(meta.job_id)
    dispatch({ type: 'RESET' })
  }

  return (
    <section className="step">
      <h2>步驟 2　辨識結果與對照編輯</h2>
      <p className="info">辨識方式：{status.mode} · {pnos.length} 頁</p>
      {pnos.length > 1 && (
        <label>
          頁碼：
          <select value={page} onChange={(e) => dispatch({ type: 'SET_PAGE', page: Number(e.target.value) })}>
            {pnos.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
      )}
      <div className="compare">
        <div className="left">
          {meta && <ZoomImage src={api.pageImageUrl(meta.job_id, page)} alt={`第 ${page} 頁`} />}
        </div>
        <div className="right">
          <textarea value={cur} onChange={(e) => dispatch({ type: 'EDIT', page, text: e.target.value })} />
        </div>
      </div>
      <div className="actions">
        <button className="primary" onClick={download}>⬇ 下載辨識結果（.txt）</button>
        <button onClick={reset}>🔄 辨識新檔案</button>
      </div>
    </section>
  )
}
```

- [ ] **Step 5: 型別檢查通過（components 還沒被 App 使用，先用 build 檢查語法/型別）**

> 註：此時 `App.tsx` 仍是樣板、尚未 import 這些元件，`vite build` 只會打包被 main→App 參照到的檔案；但 `tsc -b` 會型別檢查整個 src（含這些 .tsx）。

Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功（tsc 對四個元件型別檢查無誤）。

- [ ] **Step 6: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/components
git commit -m "feat(web): UI components (StepNav/ZoomImage/Step1/Step2)"
```

---

## Task 6：組裝 App＋樣式＋渲染測試

**Files:** Create/Modify `frontend/src/App.tsx`、`frontend/src/App.css`、`frontend/src/App.test.tsx`；確認 `frontend/src/main.tsx`

- [ ] **Step 1: 寫 App 渲染冒煙測試 `frontend/src/App.test.tsx`**

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

vi.mock('./api', () => ({
  createJob: vi.fn(),
  startRecognize: vi.fn(),
  getStatus: vi.fn(),
  deleteJob: vi.fn(),
  pageImageUrl: () => 'about:blank',
}))

describe('App', () => {
  it('renders title and step 1', () => {
    render(<App />)
    expect(screen.getByText(/OCR-Work-platform/)).toBeTruthy()
    expect(screen.getByText(/步驟 1/)).toBeTruthy()
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（App 仍是樣板，找不到 `步驟 1` 文字）

- [ ] **Step 3: 覆寫 `frontend/src/App.tsx`**

```tsx
import { useReducer } from 'react'
import { reducer, initialState } from './state'
import { StepNav } from './components/StepNav'
import { Step1Upload } from './components/Step1Upload'
import { Step2Edit } from './components/Step2Edit'
import './App.css'

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState)
  return (
    <div className="app">
      <h1>🛠️ OCR-Work-platform</h1>
      <p className="sub">PaddleOCR ＋ DeepSeek · 原圖對照 · 線上編輯（born-digital PDF 自動走文字層）</p>
      <StepNav state={state} dispatch={dispatch} />
      {state.step === 1 ? (
        <Step1Upload state={state} dispatch={dispatch} />
      ) : (
        <Step2Edit state={state} dispatch={dispatch} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: 覆寫 `frontend/src/App.css`**

```css
.app { max-width: 1100px; margin: 0 auto; padding: 16px 20px; font-family: system-ui, sans-serif; }
h1 { margin: 0; }
.sub { color: #666; margin: 4px 0 14px; }
.stepnav { display: flex; gap: 8px; margin-bottom: 12px; }
.tab { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 6px; background: #f6f6f6; cursor: pointer; }
.tab.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
.tab:disabled { opacity: .5; cursor: not-allowed; }
.step { border: 1px solid #eee; border-radius: 8px; padding: 16px; }
.step h2 { margin-top: 0; font-size: 1.1rem; }
.info { color: #444; }
.error { color: #c00; }
.progress { color: #1f6feb; }
button.primary { background: #1f6feb; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; }
.thumb img { max-width: 400px; max-height: 560px; border: 1px solid #ddd; }
.compare { display: flex; gap: 12px; }
.compare .left, .compare .right { flex: 1; }
.zoom { width: 100%; height: 560px; overflow: hidden; border: 1px solid #ddd; border-radius: 4px; position: relative; cursor: grab; user-select: none; background: #fafafa; }
.zoom img { width: 100%; position: absolute; top: 0; left: 0; pointer-events: none; display: block; }
.zhint { position: absolute; bottom: 6px; right: 8px; background: rgba(0,0,0,.55); color: #fff; font: 11px sans-serif; padding: 2px 6px; border-radius: 3px; }
.right textarea { width: 100%; height: 560px; font-family: monospace; font-size: 13px; }
.actions { margin-top: 12px; display: flex; gap: 10px; }
```

- [ ] **Step 5: 確認 `frontend/src/main.tsx` 仍渲染 `<App />`**

Vite 樣板的 `src/main.tsx` 已 `import App from './App.tsx'` 並渲染。用 Read 確認；若樣板 import 了 `./index.css` 也保留即可（不影響）。

- [ ] **Step 6: 跑測試＋打包確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（combine 3 ＋ api 4 ＋ state 4 ＋ App 1 = 12 passed）
Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功。

- [ ] **Step 7: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/App.tsx frontend/src/App.css frontend/src/App.test.tsx
git commit -m "feat(web): assemble App + styles + render smoke test"
```

---

## Task 7：啟動腳本、README、實機冒煙

**Files:** Create `frontend/run_frontend.bat`、Modify `README.md`

- [ ] **Step 1: `frontend/run_frontend.bat`**

```bat
@echo off
REM 啟動前端 dev（需後端 :8000 先啟動）
cd /d "%~dp0"
npm run dev
```

- [ ] **Step 2: README 補前後端段落**（在 `README.md` 末端新增）

```markdown
## 前後端分離版（backend + frontend）

- 後端 API（FastAPI）：`cd backend && run_api.bat`（或 `python -m uvicorn app.main:app --port 8000`），文件 http://localhost:8000/docs 。
- 前端 SPA（React+Vite）：先啟動後端，再 `cd frontend && run_frontend.bat`（或 `npm run dev`），開 http://localhost:5173 。dev 下 `/api` 由 Vite proxy 轉到 :8000。
```

- [ ] **Step 3: 實機冒煙（前端起得來、能 build）**

Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功（最終型別檢查＋打包）。
（可選 E2E：另開後端 `python -m uvicorn app.main:app --port 8000`，再 `npm run dev`，瀏覽器走一遍上傳→辨識→編輯→下載；非必要步驟。）

- [ ] **Step 4: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/run_frontend.bat README.md
git commit -m "chore(web): frontend launch script + README"
```

---

## 完成後

Phase 2 交付：React+Vite+TS 前端（:5173，dev proxy 串 :8000 後端），完整兩步驟流程＋12 個前端測試。前後端分離 v1 完成；可選後續：production 打包（前端 `dist` 由後端或 nginx 提供）、認證、批次等（皆為原 spec 非目標）。
