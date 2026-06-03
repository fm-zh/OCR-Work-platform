# 辨識後自動表格整理＋表格編輯＋Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 辨識完成後自動用 DeepSeek 把每頁整理成表格（job 第二階段），結果分頁提供「文字（唯讀）／表格（可編輯儲存格）」雙檢視，下載改為從編輯後的表格產生 Excel；移除文字編輯與 .txt 下載。

**Architecture:** 後端把結構化做成 `Job` 的第二階段（`start_structuring` 背景並行 `excel.structure_page`）；`POST /api/jobs/{id}/structure` 觸發、`GET /api/jobs/{id}` 回傳 `structure_status`＋`tables`；`POST /api/excel` 改吃已結構化表格（純 openpyxl）。前端 reducer 改為表格編輯，`Step2Edit` 進場自動觸發整理並輪詢。對應 spec：`docs/superpowers/specs/2026-06-03-auto-table-edit-design.md`。

**Tech Stack:** FastAPI、openpyxl、DeepSeek、pytest；React+TS、Vitest。

> **環境備註：**
> - 後端 `E:\OCR-Work-platform\backend`（`python -m pytest tests -q`）；前端 `E:\OCR-Work-platform\frontend`（`npm test`、`npm run build`）。
> - 後端測試離線：monkeypatch `app.excel.structure_page`；born-digital 檔 `E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf` 走文字層免網路。
> - git 倉庫。前端事件型別從 `react` import（勿用 `React.xxx`）。

---

## File Structure

| 檔案 | 變更 |
|---|---|
| `backend/app/jobs.py` | `Job` 加 `structure_status/tables/structure_error`；`start_structuring`＋`_run_structuring` |
| `backend/app/schemas.py` | 加 `Sheet`；`JobStatus` 加三欄；`ExcelRequest` 改 `sheets` |
| `backend/app/main.py` | `_status` 帶新欄；`POST /api/jobs/{id}/structure`；`/api/excel` 改吃 sheets |
| `backend/tests/test_jobs.py` | `start_structuring` 測試 |
| `backend/tests/test_excel.py` | 端點測試改寫＋結構化端點測試 |
| `frontend/src/types.ts` | `Sheet`；`JobStatus` 加三欄 |
| `frontend/src/state.ts` | 移除 `edited/EDIT`；加 `view/tables`＋四個 action |
| `frontend/src/state.test.ts` | 改寫對應測試 |
| `frontend/src/api.ts` | 加 `startStructure`；`exportExcel` 改吃 sheets |
| `frontend/src/api.test.ts` | 改寫 `exportExcel`、加 `startStructure` |
| `frontend/src/components/Step2Edit.tsx` | 重寫：雙檢視、自動整理輪詢、表格編輯、Excel 下載 |
| `frontend/src/App.css` | 表格／檢視切換樣式 |

---

## Task 1：後端 job 結構化第二階段

**Files:** Modify `backend/app/jobs.py`；Test `backend/tests/test_jobs.py`

- [ ] **Step 1: 加失敗測試**（附加到 `backend/tests/test_jobs.py` 末端）

```python
def test_start_structuring_runs_to_done(monkeypatch):
    from app import excel
    monkeypatch.setattr(excel, "structure_page",
                        lambda text, key, **kw: {"columns": ["c"], "rows": [[text[:2]]]})
    store = JobStore()
    job = store.create("file3.pdf", _data())
    store.start_recognition(job.job_id)
    for _ in range(60):
        if store.get(job.job_id).status in ("done", "error"):
            break
        time.sleep(0.2)
    assert store.get(job.job_id).status == "done"
    s = store.start_structuring(job.job_id)
    assert s.structure_status in ("running", "done")
    for _ in range(60):
        if store.get(job.job_id).structure_status in ("done", "error"):
            break
        time.sleep(0.2)
    cur = store.get(job.job_id)
    assert cur.structure_status == "done"
    assert "1" in cur.tables
    assert cur.tables["1"]["columns"] == ["c"]


def test_start_structuring_before_recognize_stays_idle():
    store = JobStore()
    job = store.create("file3.pdf", _data())  # status == created
    s = store.start_structuring(job.job_id)
    assert s is not None
    assert s.structure_status == "idle"


def test_start_structuring_unknown_returns_none():
    store = JobStore()
    assert store.start_structuring("nope") is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_jobs.py -q`
Expected: FAIL（`Job` 無 `structure_status` / `JobStore` 無 `start_structuring`）

- [ ] **Step 3: 修改 `backend/app/jobs.py`**

把頂端 `from . import engine` 改為：
```python
from . import engine, excel
```
（`ThreadPoolExecutor` 在 jobs.py 頂端已匯入，`_run_structuring` 直接用即可，不需再加 import。）

在 `Job` dataclass 末端（`error` 欄位之後）新增三欄：
```python
    structure_status: str = "idle"   # idle | running | done | error
    tables: Optional[dict] = None     # {"1": {"columns":[...], "rows":[[...]]}}
    structure_error: Optional[str] = None
```

在 `JobStore` 類別末端（`_run` 方法之後）新增兩個方法：
```python
    def start_structuring(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status != "done":
            return job  # 尚未辨識完，不啟動（呼叫端回 409）
        if job.structure_status in ("running", "done"):
            return job
        job.structure_status = "running"
        self._pool.submit(self._run_structuring, job_id)
        return job

    def _run_structuring(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        try:
            key = engine.resolve_deepseek_key()
            items = sorted((job.pages or {}).items(),
                           key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
            tables: dict = {}
            if items:
                with ThreadPoolExecutor(max_workers=min(4, len(items))) as ex:
                    for k, st in ex.map(
                        lambda kv: (kv[0], excel.structure_page(kv[1], key)), items):
                        tables[k] = st
            job.tables = tables
            job.structure_status = "done"
        except Exception as exc:  # noqa: BLE001
            job.structure_error = f"{type(exc).__name__}: {exc}"
            job.structure_status = "error"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_jobs.py -q`
Expected: PASS（原 4 ＋ 新 3 = 7 passed）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/jobs.py backend/tests/test_jobs.py
git commit -m "feat(api): job structuring phase (start_structuring)"
```

---

## Task 2：後端 schemas、端點、/api/excel 改寫

**Files:** Modify `backend/app/schemas.py`、`backend/app/main.py`、`backend/tests/test_excel.py`

- [ ] **Step 1: 改寫端點測試**（編輯 `backend/tests/test_excel.py`）

(a) 在「TestClient 區段」頂端的 import 後，新增 `import time` 與 BORN 常數（若該檔頂端尚無）。具體：把檔案中現有這段：
```python
from fastapi.testclient import TestClient
from app.main import app
from app import excel as _excel

_client = TestClient(app)
```
改為：
```python
import time

from fastapi.testclient import TestClient
from app.main import app
from app import excel as _excel

_client = TestClient(app)
BORN = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"
```

(b) 把舊的 `test_excel_endpoint_builds_xlsx` 與 `test_excel_endpoint_empty_pages_400` 兩個函式整段刪除，換成：
```python
def test_excel_endpoint_builds_xlsx_from_sheets():
    r = _client.post("/api/excel", json={
        "file_name": "財報.pdf",
        "sheets": {"1": {"columns": ["項目"], "rows": [["現金"]]},
                   "2": {"columns": [], "rows": [["x"]]}},
    })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    wb = _openpyxl.load_workbook(_io.BytesIO(r.content))
    assert wb.sheetnames == ["第1頁", "第2頁"]


def test_excel_endpoint_empty_sheets_400():
    r = _client.post("/api/excel", json={"file_name": "x.pdf", "sheets": {}})
    assert r.status_code == 400


def test_structure_endpoint_flow(monkeypatch):
    monkeypatch.setattr(_excel, "structure_page",
                        lambda text, key, **kw: {"columns": ["c"], "rows": [[text[:2]]]})
    with open(BORN, "rb") as f:
        jid = _client.post("/api/jobs",
                           files={"file": ("file3.pdf", f, "application/pdf")}).json()["job_id"]
    assert _client.post(f"/api/jobs/{jid}/structure").status_code == 409
    _client.post(f"/api/jobs/{jid}/recognize")
    for _ in range(60):
        if _client.get(f"/api/jobs/{jid}").json()["status"] in ("done", "error"):
            break
        time.sleep(0.3)
    assert _client.post(f"/api/jobs/{jid}/structure").status_code == 200
    s = None
    for _ in range(60):
        s = _client.get(f"/api/jobs/{jid}").json()
        if s["structure_status"] in ("done", "error"):
            break
        time.sleep(0.3)
    assert s["structure_status"] == "done"
    assert s["tables"]["1"]["columns"] == ["c"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: FAIL（`/api/excel` 還收 pages、無 `/structure` 端點、`JobStatus` 無 `structure_status`）

- [ ] **Step 3: 修改 `backend/app/schemas.py`**

把頂端 `from typing import Dict, Optional` 改為：
```python
from typing import Dict, List, Optional
```

新增 `Sheet`（放在 `Progress` 之前或之後皆可）：
```python
class Sheet(BaseModel):
    columns: List[str]
    rows: List[List[str]]
```

`JobStatus` 末端（`error` 之後）新增三欄：
```python
    structure_status: str = "idle"
    tables: Optional[Dict[str, Sheet]] = None
    structure_error: Optional[str] = None
```

把既有 `ExcelRequest` 整段改為：
```python
class ExcelRequest(BaseModel):
    file_name: str
    sheets: Dict[str, Sheet]
```

- [ ] **Step 4: 修改 `backend/app/main.py`**

(a) `_status` 函式回傳改為帶上新欄位：
```python
def _status(job: Job) -> schemas.JobStatus:
    return schemas.JobStatus(job_id=job.job_id, file_name=job.file_name,
                             n_pages=job.n_pages, is_born_digital=job.is_born_digital,
                             status=job.status, progress=job.progress,
                             mode=job.mode, pages=job.pages, error=job.error,
                             structure_status=job.structure_status,
                             tables=job.tables, structure_error=job.structure_error)
```

(b) 把既有 `export_excel` 路由整段改為（改吃 sheets、不呼叫 DeepSeek）：
```python
@app.post("/api/excel")
def export_excel(req: schemas.ExcelRequest) -> Response:
    if not req.sheets:
        raise HTTPException(status_code=400, detail="sheets 不可為空")
    structured: dict[int, dict] = {}
    for k, sheet in req.sheets.items():
        try:
            page_no = int(k)
        except ValueError:
            continue
        structured[page_no] = {"columns": sheet.columns, "rows": sheet.rows}
    data = excel.build_workbook(structured)
    stem = Path(req.file_name).stem or "result"
    quoted = urllib.parse.quote(f"{stem}.xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
```

(c) 在 `export_excel` 之後新增結構化端點：
```python
@app.post("/api/jobs/{job_id}/structure")
def structure_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    if job.status != "done":
        raise HTTPException(status_code=409, detail="請先完成辨識")
    job = store.start_structuring(job_id)
    return {"job_id": job.job_id, "structure_status": job.structure_status}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: PASS（pure 5 ＋ 端點 3 = 8 passed）

- [ ] **Step 6: 跑後端全部測試**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests -q`
Expected: PASS（jobs 7 ＋ engine 3 ＋ api 7 ＋ excel 8 = 25 passed）

- [ ] **Step 7: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/schemas.py backend/app/main.py backend/tests/test_excel.py
git commit -m "feat(api): /structure endpoint + /api/excel takes sheets"
```

---

## Task 3：前端型別與狀態（reducer）

**Files:** Modify `frontend/src/types.ts`、`frontend/src/state.ts`、`frontend/src/state.test.ts`

- [ ] **Step 1: 以完整內容覆寫 `frontend/src/state.test.ts`**

```ts
import { describe, it, expect } from 'vitest'
import { reducer, initialState } from './state'
import type { JobMeta, Sheet } from './types'

const META: JobMeta = { job_id: 'j', file_name: 'f.pdf', n_pages: 2, is_born_digital: false, status: 'created' }
const SHEET: Sheet = { columns: ['項目', '金額'], rows: [['現金', '100']] }

describe('reducer', () => {
  it('SET_META resets tables/view/page/status', () => {
    const s = reducer({ ...initialState, curPage: 3, view: 'table', tables: { 1: SHEET } }, { type: 'SET_META', meta: META })
    expect(s.meta).toEqual(META)
    expect(s.curPage).toBe(1)
    expect(s.tables).toEqual({})
    expect(s.view).toBe('text')
    expect(s.status).toBeNull()
  })
  it('SET_VIEW switches view', () => {
    expect(reducer(initialState, { type: 'SET_VIEW', view: 'table' }).view).toBe('table')
  })
  it('SET_TABLES loads tables', () => {
    expect(reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } }).tables[1]).toEqual(SHEET)
  })
  it('EDIT_CELL updates one cell immutably', () => {
    const s0 = reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } })
    const s1 = reducer(s0, { type: 'EDIT_CELL', page: 1, row: 0, col: 1, value: '999' })
    expect(s1.tables[1].rows[0][1]).toBe('999')
    expect(SHEET.rows[0][1]).toBe('100')
  })
  it('EDIT_HEADER updates one column', () => {
    const s0 = reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } })
    const s1 = reducer(s0, { type: 'EDIT_HEADER', page: 1, col: 0, value: '科目' })
    expect(s1.tables[1].columns[0]).toBe('科目')
  })
  it('GO switches step', () => {
    expect(reducer(initialState, { type: 'GO', step: 2 }).step).toBe(2)
  })
  it('RESET returns initial', () => {
    const dirty = reducer(initialState, { type: 'SET_VIEW', view: 'table' })
    expect(reducer(dirty, { type: 'RESET' })).toEqual(initialState)
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（`Sheet` 未匯出 / reducer 無新 action）

- [ ] **Step 3: 在 `frontend/src/types.ts` 末端新增 `Sheet`，並擴充 `JobStatus`**

新增：
```ts
export interface Sheet {
  columns: string[]
  rows: string[][]
}
```
把 `JobStatus` 介面內 `error: string | null` 之後新增三行：
```ts
  structure_status: 'idle' | 'running' | 'done' | 'error'
  tables: Record<string, Sheet> | null
  structure_error: string | null
```

- [ ] **Step 4: 以完整內容覆寫 `frontend/src/state.ts`**

```ts
import type { JobMeta, JobStatus, Sheet } from './types'

export interface AppState {
  step: 1 | 2
  meta: JobMeta | null
  status: JobStatus | null
  curPage: number
  view: 'text' | 'table'
  tables: Record<number, Sheet>
}

export type Action =
  | { type: 'SET_META'; meta: JobMeta | null }
  | { type: 'SET_STATUS'; status: JobStatus | null }
  | { type: 'SET_PAGE'; page: number }
  | { type: 'SET_VIEW'; view: 'text' | 'table' }
  | { type: 'SET_TABLES'; tables: Record<number, Sheet> }
  | { type: 'EDIT_CELL'; page: number; row: number; col: number; value: string }
  | { type: 'EDIT_HEADER'; page: number; col: number; value: string }
  | { type: 'GO'; step: 1 | 2 }
  | { type: 'RESET' }

export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, view: 'text', tables: {},
}

function editCell(t: Sheet, row: number, col: number, value: string): Sheet {
  return {
    columns: t.columns,
    rows: t.rows.map((r, ri) => (ri === row ? r.map((c, ci) => (ci === col ? value : c)) : r)),
  }
}

function editHeader(t: Sheet, col: number, value: string): Sheet {
  return { columns: t.columns.map((c, ci) => (ci === col ? value : c)), rows: t.rows }
}

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'SET_META':
      return { ...s, meta: a.meta, status: null, tables: {}, view: 'text', curPage: 1 }
    case 'SET_STATUS':
      return { ...s, status: a.status }
    case 'SET_PAGE':
      return { ...s, curPage: a.page }
    case 'SET_VIEW':
      return { ...s, view: a.view }
    case 'SET_TABLES':
      return { ...s, tables: a.tables }
    case 'EDIT_CELL': {
      const t = s.tables[a.page]
      if (!t) return s
      return { ...s, tables: { ...s.tables, [a.page]: editCell(t, a.row, a.col, a.value) } }
    }
    case 'EDIT_HEADER': {
      const t = s.tables[a.page]
      if (!t) return s
      return { ...s, tables: { ...s.tables, [a.page]: editHeader(t, a.col, a.value) } }
    }
    case 'GO':
      return { ...s, step: a.step }
    case 'RESET':
      return initialState
  }
}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（state 7 ＋ 其他既有）

- [ ] **Step 6: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/types.ts frontend/src/state.ts frontend/src/state.test.ts
git commit -m "feat(web): Sheet type + table-edit reducer"
```

---

## Task 4：前端 API（startStructure、exportExcel 改吃 sheets）

**Files:** Modify `frontend/src/api.ts`、`frontend/src/api.test.ts`

- [ ] **Step 1: 改寫測試**（編輯 `frontend/src/api.test.ts`）

把現有的 `it('exportExcel posts json and returns blob', ...)` 整段替換為下列兩個 `it`（仍放在 `describe('api', ...)` 內）：
```ts
  it('exportExcel posts sheets json and returns blob', async () => {
    const blob = new Blob(['x'])
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob })
    vi.stubGlobal('fetch', fetchMock)
    const res = await api.exportExcel('f.pdf', { '1': { columns: ['a'], rows: [['b']] } })
    expect(res).toBe(blob)
    expect(fetchMock).toHaveBeenCalledWith('/api/excel', expect.objectContaining({ method: 'POST' }))
  })

  it('startStructure posts to structure endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ job_id: 'x', structure_status: 'running' }) })
    vi.stubGlobal('fetch', fetchMock)
    const res = await api.startStructure('x')
    expect(res.structure_status).toBe('running')
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs/x/structure', expect.objectContaining({ method: 'POST' }))
  })
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（`api.startStructure` 不存在、`exportExcel` 簽名不符）

- [ ] **Step 3: 修改 `frontend/src/api.ts`**

頂端 import 改為帶入 `Sheet`：
```ts
import type { JobMeta, JobStatus, Sheet } from './types'
```
把既有 `exportExcel` 整段改為：
```ts
export async function exportExcel(fileName: string, sheets: Record<string, Sheet>): Promise<Blob> {
  const r = await fetch(`${BASE}/excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, sheets }),
  })
  if (!r.ok) throw new Error(`Excel 匯出失敗 (${r.status})`)
  return r.blob()
}
```
並在檔案末端新增：
```ts
export async function startStructure(jobId: string): Promise<{ job_id: string; structure_status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/structure`, { method: 'POST' })
  if (!r.ok) throw new Error(`表格整理啟動失敗 (${r.status})`)
  return r.json()
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（api 測試含新兩項）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(web): startStructure + exportExcel(sheets)"
```

---

## Task 5：前端步驟 2 重寫（雙檢視＋自動整理＋表格編輯）

**Files:** Modify `frontend/src/components/Step2Edit.tsx`、`frontend/src/App.css`

- [ ] **Step 1: 以完整內容覆寫 `frontend/src/components/Step2Edit.tsx`**

```tsx
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
```

- [ ] **Step 2: 在 `frontend/src/App.css` 末端新增表格／檢視切換樣式**

```css
/* ── view tabs + table (step 2) ─────────────────────────── */
.viewtabs {
  display: flex;
  gap: 8px;
}

.vtab {
  padding: 6px 14px;
  font-size: 14px;
  border-radius: 8px;
}

.vtab.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.tablewrap {
  height: 560px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 10px;
}

table.grid {
  border-collapse: collapse;
  width: 100%;
}

table.grid th,
table.grid td {
  border: 1px solid var(--border);
  padding: 0;
}

table.grid th {
  background: #f3f4f6;
}

table.grid input {
  border: none;
  border-radius: 0;
  width: 100%;
  min-width: 90px;
  padding: 6px 8px;
  background: transparent;
  font: inherit;
}

table.grid input:focus {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
```

- [ ] **Step 3: 型別檢查＋測試通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功（tsc 無錯）。
Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（全部）。

- [ ] **Step 4: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/components/Step2Edit.tsx frontend/src/App.css
git commit -m "feat(web): step 2 dual view + editable table + auto-structure"
```

---

## 完成後（實機驗證，可選）

重啟後端 :8000、前端 :5173 後：上傳→辨識→進步驟2 看到唯讀文字、切到「表格」看到整理中→可編輯表格；改幾格→「下載 Excel」確認下載到同名 .xlsx 且為編輯後內容。（需真 DeepSeek。）
