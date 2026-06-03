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
