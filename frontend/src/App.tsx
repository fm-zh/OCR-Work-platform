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
