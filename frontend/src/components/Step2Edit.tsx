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
