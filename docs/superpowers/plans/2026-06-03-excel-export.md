# Excel 匯出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者把（編輯後的）辨識結果按原表格式匯出成 Excel：後端用 DeepSeek 把每頁文字整理成欄／列、openpyxl 產生每頁一個工作表的 .xlsx，前端步驟 2 新增「下載 Excel」。

**Architecture:** 後端新模組 `backend/app/excel.py`（`structure_page` 呼叫 DeepSeek 回 JSON、`build_workbook` 純函式產生 xlsx），新端點 `POST /api/excel`；前端 `api.exportExcel` ＋ `Step2Edit` 按鈕。對應 spec：`docs/superpowers/specs/2026-06-03-excel-export-design.md`。

**Tech Stack:** Python FastAPI、openpyxl、DeepSeek（json_object）、pytest；React+TS、Vitest。

> **環境備註：**
> - 後端在 `E:\OCR-Work-platform\backend`，測試 `python -m pytest tests -q`（從 backend 目錄）。
> - 前端在 `E:\OCR-Work-platform\frontend`，測試 `npm test`、型別檢查 `npm run build`（從 frontend 目錄）。
> - `pip install` / 後端啟動可能需網路 → Bash tool 設 `dangerouslyDisableSandbox=true`。
> - 後端測試離線可跑：以 `monkeypatch` 換掉 DeepSeek 呼叫；純函式直接測。
> - 平台根目錄有 `llm_correct.py`（含 `DEEPSEEK_API_BASE`）、`ocr_app_pro_helpers.py`（`resolve_deepseek_key`）。git 倉庫。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `backend/app/excel.py`（新增） | `structure_page`（DeepSeek→{columns,rows}）、`_parse_structured`（解析/退化）、`build_workbook`（openpyxl→bytes） |
| `backend/app/schemas.py`（修改） | 新增 `ExcelRequest` |
| `backend/app/main.py`（修改） | 新增 `POST /api/excel` |
| `backend/requirements-backend.txt`（修改） | 新增 `openpyxl` |
| `backend/tests/test_excel.py`（新增） | excel 純函式 ＋ 端點測試（monkeypatch DeepSeek） |
| `frontend/src/api.ts`（修改） | 新增 `exportExcel` |
| `frontend/src/api.test.ts`（修改） | `exportExcel` 測試 |
| `frontend/src/components/Step2Edit.tsx`（修改） | 「下載 Excel」按鈕＋處理 |

---

## Task 1：後端 excel.py（結構化＋產生 xlsx）

**Files:** Create `backend/app/excel.py`、`backend/tests/test_excel.py`；Modify `backend/requirements-backend.txt`

- [ ] **Step 1: 加 openpyxl 相依並安裝**

在 `backend/requirements-backend.txt` 末端新增一行：
```
openpyxl
```
然後安裝（Bash，dangerouslyDisableSandbox=true）：
`cd /d E:\OCR-Work-platform\backend && python -m pip install openpyxl`
Expected: 安裝成功。

- [ ] **Step 2: 寫失敗測試 `backend/tests/test_excel.py`**

```python
import io
import openpyxl
from app import excel


def test_parse_structured_valid():
    raw = '{"columns":["項目","金額"],"rows":[["現金","100"]]}'
    out = excel._parse_structured(raw, "ignored")
    assert out["columns"] == ["項目", "金額"]
    assert out["rows"] == [["現金", "100"]]


def test_parse_structured_fallback_on_bad_json():
    out = excel._parse_structured("not json", "行一\n行二")
    assert out["columns"] == []
    assert out["rows"] == [["行一"], ["行二"]]


def test_parse_structured_coerces_non_strings():
    raw = '{"columns":["c"],"rows":[[1, null, "x"]]}'
    out = excel._parse_structured(raw, "")
    assert out["rows"] == [["1", "", "x"]]


def test_build_workbook_with_columns():
    data = {1: {"columns": ["項目", "金額"], "rows": [["現金", "100"], ["存貨", "200"]]}}
    wb = openpyxl.load_workbook(io.BytesIO(excel.build_workbook(data)))
    assert wb.sheetnames == ["第1頁"]
    ws = wb["第1頁"]
    assert [c.value for c in ws[1]] == ["項目", "金額"]
    assert ws.cell(row=2, column=1).value == "現金"


def test_build_workbook_multi_page_no_columns():
    data = {1: {"columns": [], "rows": [["a"]]}, 2: {"columns": [], "rows": [["b"]]}}
    wb = openpyxl.load_workbook(io.BytesIO(excel.build_workbook(data)))
    assert wb.sheetnames == ["第1頁", "第2頁"]
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.excel'`）

- [ ] **Step 4: 實作 `backend/app/excel.py`**

```python
"""把辨識文字用 DeepSeek 整理成表格，再用 openpyxl 產生 .xlsx。"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import llm_correct  # noqa: E402
import openpyxl  # noqa: E402

_STRUCT_PROMPT = """以下是一頁台灣財務報表/稅報的辨識文字。請整理成一個表格的 JSON 物件，格式：
{{"columns": ["欄1","欄2",...], "rows": [["儲存格",...], ...]}}

規則：
- 欄位依內容判斷（例如「項目/金額/百分比」或「代碼/科目/金額」）；若難以判斷欄位可給空陣列 columns。
- 每一列對應原文一行的資料；把標籤與數字拆到對應欄位。
- 儲存格值「保留原始文字」：含千分位逗號、括號負號（如 (588)）、百分比 %、$ 等，不要改寫成數值。
- 只輸出單一 JSON 物件，不要任何說明或 markdown。

辨識文字：
=====
{text}
====="""


def _fallback(source_text: str) -> dict:
    rows = [[ln] for ln in source_text.splitlines() if ln.strip()]
    return {"columns": [], "rows": rows}


def _parse_structured(raw: str, source_text: str) -> dict:
    """DeepSeek 回傳字串 → {columns, rows}；失敗退化為每行單欄。"""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fallback(source_text)
    if not isinstance(data, dict):
        return _fallback(source_text)
    rows = data.get("rows")
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        return _fallback(source_text)
    columns = data.get("columns")
    if not isinstance(columns, list):
        columns = []
    columns = [str(c) for c in columns]
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    return {"columns": columns, "rows": rows}


def _deepseek_json(prompt: str, api_key: str, model: str, timeout: int) -> str:
    """呼叫 DeepSeek chat（response_format=json_object），回傳內容字串。"""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{llm_correct.DEEPSEEK_API_BASE}/chat/completions",
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def structure_page(text: str, api_key: str, model: str = "deepseek-chat",
                   timeout: int = 180) -> dict:
    """呼叫 DeepSeek 把一頁文字整理成 {columns, rows}。"""
    if not text or not text.strip():
        return {"columns": [], "rows": []}
    raw = _deepseek_json(_STRUCT_PROMPT.format(text=text), api_key, model, timeout)
    return _parse_structured(raw, text)


_ILLEGAL_SHEET = re.compile(r"[\[\]:*?/\\]")


def _sheet_name(page_no: int) -> str:
    return _ILLEGAL_SHEET.sub("", f"第{page_no}頁")[:31]


def build_workbook(pages_structured: dict) -> bytes:
    """{page_no: {columns, rows}} → .xlsx bytes（每頁一個工作表）。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for page_no in sorted(pages_structured):
        st = pages_structured[page_no]
        ws = wb.create_sheet(title=_sheet_name(page_no))
        columns = st.get("columns") or []
        if columns:
            ws.append([str(c) for c in columns])
        for row in st.get("rows") or []:
            ws.append([("" if c is None else str(c)) for c in row])
    if not wb.sheetnames:
        wb.create_sheet(title="第1頁")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: PASS（5 passed）

- [ ] **Step 6: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/excel.py backend/tests/test_excel.py backend/requirements-backend.txt
git commit -m "feat(api): excel module (DeepSeek structuring + openpyxl)"
```

---

## Task 2：後端端點 `POST /api/excel`

**Files:** Modify `backend/app/schemas.py`、`backend/app/main.py`；Test in `backend/tests/test_excel.py`

- [ ] **Step 1: 加端點失敗測試**（附加到 `backend/tests/test_excel.py` 末端）

```python
import io as _io
import openpyxl as _openpyxl
from fastapi.testclient import TestClient
from app.main import app
from app import excel as _excel

_client = TestClient(app)


def test_excel_endpoint_builds_xlsx(monkeypatch):
    monkeypatch.setattr(
        _excel, "structure_page",
        lambda text, key, **kw: {"columns": ["項目"], "rows": [[text[:3]]]},
    )
    r = _client.post("/api/excel", json={"file_name": "財報.pdf",
                                         "pages": {"1": "abc", "2": "def"}})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    wb = _openpyxl.load_workbook(_io.BytesIO(r.content))
    assert wb.sheetnames == ["第1頁", "第2頁"]


def test_excel_endpoint_empty_pages_400():
    r = _client.post("/api/excel", json={"file_name": "x.pdf", "pages": {}})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: FAIL（端點不存在 → 404，斷言失敗）

- [ ] **Step 3: 在 `backend/app/schemas.py` 末端新增 `ExcelRequest`**

```python
class ExcelRequest(BaseModel):
    file_name: str
    pages: Dict[str, str]
```
（`Dict` 已於檔案頂端 `from typing import Dict, Optional` 匯入，無需再加。）

- [ ] **Step 4: 修改 `backend/app/main.py`**

把 import 區塊：
```python
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import engine, schemas
from .jobs import Job, JobStore
```
改為：
```python
import urllib.parse

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import engine, excel, schemas
from .jobs import Job, JobStore
```

並在 `delete_job` 路由之後（檔案末端）新增：
```python
@app.post("/api/excel")
def export_excel(req: schemas.ExcelRequest) -> Response:
    if not req.pages:
        raise HTTPException(status_code=400, detail="pages 不可為空")
    key = engine.resolve_deepseek_key()
    structured: dict[int, dict] = {}
    for k, text in req.pages.items():
        try:
            page_no = int(k)
        except ValueError:
            continue
        structured[page_no] = excel.structure_page(text, key)
    data = excel.build_workbook(structured)
    stem = Path(req.file_name).stem or "result"
    quoted = urllib.parse.quote(f"{stem}.xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
```
（`Path` 已於 main.py 頂端 `from pathlib import Path` 匯入；`engine.resolve_deepseek_key` 來自 engine.py 既有匯入。）

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_excel.py -q`
Expected: PASS（5 ＋ 2 = 7 passed）

- [ ] **Step 6: 跑後端全部測試**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests -q`
Expected: PASS（原 14 ＋ excel 7 = 21 passed）

- [ ] **Step 7: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/schemas.py backend/app/main.py backend/tests/test_excel.py
git commit -m "feat(api): POST /api/excel endpoint"
```

---

## Task 3：前端 `exportExcel`

**Files:** Modify `frontend/src/api.ts`、`frontend/src/api.test.ts`

- [ ] **Step 1: 加失敗測試**（附加到 `frontend/src/api.test.ts` 的 `describe('api', ...)` 內，最後一個 `it` 之後）

```ts
  it('exportExcel posts json and returns blob', async () => {
    const blob = new Blob(['x'])
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob })
    vi.stubGlobal('fetch', fetchMock)
    const res = await api.exportExcel('f.pdf', { '1': 'a' })
    expect(res).toBe(blob)
    expect(fetchMock).toHaveBeenCalledWith('/api/excel', expect.objectContaining({ method: 'POST' }))
  })
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: FAIL（`api.exportExcel` 不存在）

- [ ] **Step 3: 在 `frontend/src/api.ts` 末端新增**

```ts
export async function exportExcel(fileName: string, pages: Record<string, string>): Promise<Blob> {
  const r = await fetch(`${BASE}/excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, pages }),
  })
  if (!r.ok) throw new Error(`Excel 匯出失敗 (${r.status})`)
  return r.blob()
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（前端測試數 +1）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(web): exportExcel api client"
```

---

## Task 4：前端步驟 2「下載 Excel」按鈕

**Files:** Modify `frontend/src/components/Step2Edit.tsx`

- [ ] **Step 1: 以下列完整內容覆寫 `frontend/src/components/Step2Edit.tsx`**

```tsx
import { useState } from 'react'
import type { Dispatch } from 'react'
import type { AppState, Action } from '../state'
import * as api from '../api'
import { ZoomImage } from './ZoomImage'
import { combinePages } from '../lib/combine'

export function Step2Edit({ state, dispatch }: { state: AppState; dispatch: Dispatch<Action> }) {
  const { meta, status } = state
  const [excelBusy, setExcelBusy] = useState(false)
  const [excelErr, setExcelErr] = useState<string | null>(null)

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

  function finalText(p: number): string {
    return state.edited[p] ?? pages[String(p)]
  }

  function download() {
    const final: Record<number, string> = {}
    for (const p of pnos) final[p] = finalText(p)
    const blob = new Blob([combinePages(final)], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = (meta?.file_name?.replace(/\.[^.]+$/, '') || 'result') + '.txt'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function downloadExcel() {
    setExcelErr(null)
    setExcelBusy(true)
    try {
      const final: Record<string, string> = {}
      for (const p of pnos) final[String(p)] = finalText(p)
      const blob = await api.exportExcel(meta?.file_name ?? 'result', final)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = (meta?.file_name?.replace(/\.[^.]+$/, '') || 'result') + '.xlsx'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (ex) {
      setExcelErr(String(ex))
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
      <div className="compare">
        <div className="left">
          {meta && <ZoomImage src={api.pageImageUrl(meta.job_id, page)} alt={`第 ${page} 頁`} />}
        </div>
        <div className="right">
          <textarea value={cur} onChange={(e) => dispatch({ type: 'EDIT', page, text: e.target.value })} />
        </div>
      </div>
      {excelErr && <p className="error">❌ {excelErr}</p>}
      <div className="actions">
        <button className="primary" onClick={download}>⬇ 下載辨識結果（.txt）</button>
        <button onClick={downloadExcel} disabled={excelBusy}>
          {excelBusy ? '產生 Excel 中…' : '⬇ 下載 Excel'}
        </button>
        <button onClick={reset}>🔄 辨識新檔案</button>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: 型別檢查＋測試通過**

Run: `cd /d E:\OCR-Work-platform\frontend && npm run build`
Expected: 成功（tsc 無錯）。
Run: `cd /d E:\OCR-Work-platform\frontend && npm test`
Expected: PASS（全部，App 冒煙不受影響）。

- [ ] **Step 3: Commit**

```bash
cd /d E:\OCR-Work-platform
git add frontend/src/components/Step2Edit.tsx
git commit -m "feat(web): step 2 download Excel button"
```

---

## 完成後（實機驗證，可選）

後端 :8000、前端 :5173 都啟動後，上傳檔案→辨識→步驟2 按「⬇ 下載 Excel」，確認下載到與原檔同名的 `.xlsx`、每頁一個工作表、欄位貼近原表。（此步需真 DeepSeek，非自動測試。）
