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
