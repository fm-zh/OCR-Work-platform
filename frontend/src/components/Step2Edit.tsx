import { useEffect, useRef, useState } from 'react'
import type { Dispatch } from 'react'
import type { AppState, Action } from '../state'
import type { Sheet } from '../types'
import * as api from '../api'
import { ZoomImage } from './ZoomImage'

export function Step2Edit({ state, dispatch }: { state: AppState; dispatch: Dispatch<Action> }) {
  const { meta, status } = state
  const [excelBusy, setExcelBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const structuring = status?.structure_status ?? 'idle'

  // 進入步驟2 自動觸發表格整理 + 輪詢
  useEffect(() => {
    if (!meta) return
    if (structuring === 'done' || structuring === 'error') return
    async function run() {
      try {
        if (structuring === 'idle') {
          await api.startStructure(meta!.job_id)
        }
        timer.current = window.setInterval(async () => {
          const s = await api.getStatus(meta!.job_id)
          dispatch({ type: 'SET_STATUS', status: s })
          if (s.structure_status === 'done' && s.tables) {
            const t: Record<number, Sheet> = {}
            for (const k of Object.keys(s.tables)) t[Number(k)] = s.tables[k]
            dispatch({ type: 'SET_TABLES', tables: t })
            if (timer.current) window.clearInterval(timer.current)
          } else if (s.structure_status === 'error') {
            setErr(s.structure_error ?? '表格整理失敗')
            if (timer.current) window.clearInterval(timer.current)
          }
        }, 700)
      } catch (ex) {
        setErr(String(ex))
      }
    }
    run()
    return () => { if (timer.current) window.clearInterval(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.job_id])

  if (!status) {
    return (
      <section className="step">
        <p>尚無辨識結果，請回步驟 1。</p>
      </section>
    )
  }
  const pnos = status.pages ? Object.keys(status.pages).map(Number).sort((a, b) => a - b) : []
  const page = pnos.includes(state.curPage) ? state.curPage : (pnos[0] ?? 1)
  const table = state.tables[page]
  const tableReady = structuring === 'done' && !!table

  async function downloadExcel() {
    setErr(null)
    setExcelBusy(true)
    try {
      const sheets: Record<string, Sheet> = {}
      for (const p of pnos) {
        const t = state.tables[p]
        if (t) sheets[String(p)] = t
      }
      const blob = await api.exportExcel(meta?.file_name ?? 'result', sheets)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = (meta?.file_name?.replace(/\.[^.]+$/, '') || 'result') + '.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (ex) {
      setErr(String(ex))
    } finally {
      setExcelBusy(false)
    }
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
      <div className="viewtabs">
        <button
          className={state.view === 'text' ? 'vtab active' : 'vtab'}
          onClick={() => dispatch({ type: 'SET_VIEW', view: 'text' })}
        >
          文字（唯讀）
        </button>
        <button
          className={state.view === 'table' ? 'vtab active' : 'vtab'}
          onClick={() => dispatch({ type: 'SET_VIEW', view: 'table' })}
        >
          表格
        </button>
      </div>
      {err && <p className="error">❌ {err}</p>}
      <div className="compare">
        <div className="left">
          {meta && <ZoomImage src={api.pageImageUrl(meta.job_id, page)} alt={`第 ${page} 頁`} />}
        </div>
        <div className="right">
          {state.view === 'text' ? (
            <textarea readOnly value={status.pages?.[String(page)] ?? ''} />
          ) : !tableReady ? (
            <p className="progress">表格整理中…（DeepSeek）</p>
          ) : (
            <div className="tablewrap">
              <table className="grid">
                {table.columns.length > 0 && (
                  <thead>
                    <tr>
                      {table.columns.map((c, ci) => (
                        <th key={ci}>
                          <input value={c} onChange={(e) => dispatch({ type: 'EDIT_HEADER', page, col: ci, value: e.target.value })} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {table.rows.map((r, ri) => (
                    <tr key={ri}>
                      {r.map((cell, ci) => (
                        <td key={ci}>
                          <input value={cell} onChange={(e) => dispatch({ type: 'EDIT_CELL', page, row: ri, col: ci, value: e.target.value })} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      <div className="actions">
        <button className="primary" onClick={downloadExcel} disabled={excelBusy || structuring !== 'done'}>
          {excelBusy ? '產生 Excel 中…' : '⬇ 下載 Excel'}
        </button>
        <button onClick={reset}>🔄 辨識新檔案</button>
      </div>
    </section>
  )
}
