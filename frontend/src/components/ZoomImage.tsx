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
