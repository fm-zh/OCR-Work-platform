import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, Dispatch } from 'react'
import type { AppState, Action } from '../state'
import * as api from '../api'
import { parseRange, formatRange } from '../lib/pageRange'

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
      await api.startRecognize(meta.job_id, state.selected)
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
        accept=".pdf,.jpg,.jpeg,.png"
        onChange={onFile}
        disabled={busy || recognizing}
      />
      <p className="hint">
        支援格式：PDF、JPG、PNG　·　單檔上限 {api.MAX_UPLOAD_MB}MB
      </p>
      {err && <p className="error">❌ {err}</p>}
      {meta && (
        <>
          <p className="info">
            {meta.is_born_digital
              ? `🔎 內含文字層（born-digital）→ 直接擷取文字層（${meta.n_pages} 頁）。`
              : `🔎 掃描影像／截圖 → PaddleOCR（自動轉正）＋ 幾何重建表格（${meta.n_pages} 頁）。`}
          </p>

          <div className="selbar">
            <label>
              選擇頁碼：
              <input
                type="text"
                placeholder="例如 3,5,8-10"
                value={formatRange(state.selected)}
                onChange={(e) =>
                  dispatch({ type: 'SET_SELECTED',
                             pages: parseRange(e.target.value, meta.n_pages) })}
                disabled={recognizing}
              />
            </label>
            <button type="button" onClick={() => dispatch({ type: 'SELECT_ALL' })}
                    disabled={recognizing}>全選</button>
            <button type="button" onClick={() => dispatch({ type: 'CLEAR_SELECTED' })}
                    disabled={recognizing}>全不選</button>
            <span className="count">已選 {state.selected.length} / {meta.n_pages} 頁</span>
          </div>

          <div className="thumbgrid">
            {Array.from({ length: meta.n_pages }, (_, i) => i + 1).map((n) => {
              const on = state.selected.includes(n)
              return (
                <button
                  key={n}
                  type="button"
                  className={on ? 'thumbcell on' : 'thumbcell'}
                  onClick={() => dispatch({ type: 'TOGGLE_PAGE', page: n })}
                  disabled={recognizing}
                >
                  <img src={api.pageImageUrl(meta.job_id, n)} alt={`第 ${n} 頁`} />
                  <span className="pno">{n}</span>
                  {on && <span className="tick">✓</span>}
                </button>
              )
            })}
          </div>

          <button className="primary" onClick={onRecognize}
                  disabled={recognizing || state.selected.length === 0}>
            {recognizing ? '辨識中…' : '✅ 開始辨識（已選 ' + state.selected.length + ' 頁）'}
          </button>
          {state.selected.length === 0 && !recognizing && (
            <p className="hint">請至少選擇一頁</p>
          )}
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
