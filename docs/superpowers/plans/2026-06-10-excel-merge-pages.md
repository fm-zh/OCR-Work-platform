# Excel 跨頁合併（Merge Pages into One Sheet）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下載 Excel 時可選擇把本次辨識的所有頁機械式疊接清理成單一工作表，讓跨頁財報讀起來像一張連續的表（預設關閉，只影響下載）。

**Architecture:** 方案 A——後端新增純函式 `merge_sheets` 把依頁碼排序的多頁 `{columns, rows}` 疊接清理成一張；`build_workbook` 加一個可選的自訂工作表名參數；`/api/excel` 加 `merge` 旗標選擇走合併或現狀。前端只多一個下載 checkbox。

**Tech Stack:** Backend：FastAPI、openpyxl、pytest。Frontend：React + Vite + TypeScript、vitest。

**設計依據：** `docs/superpowers/specs/2026-06-10-excel-merge-pages-design.md`

---

## 檔案結構

| 檔案 | 動作 | 責任 |
|---|---|---|
| `backend/app/excel.py` | 修改 | 新增 `merge_sheets`；重構 `_sanitize_sheet_title`；`build_workbook` 加 `sheet_titles` 參數 |
| `backend/app/schemas.py` | 修改 | `ExcelRequest` 加 `merge: bool = False` |
| `backend/app/main.py` | 修改 | `export_excel` 依 `merge` 走合併或現狀 |
| `backend/tests/test_merge_sheets.py` | 新建 | `merge_sheets` 與 `build_workbook` 自訂命名單元測試 |
| `backend/tests/test_api.py` | 修改 | `/api/excel` merge=true / false 整合測試 |
| `frontend/src/api.ts` | 修改 | `exportExcel` 加 `merge` 參數，body 帶 `merge` |
| `frontend/src/api.test.ts` | 修改 | `exportExcel` body 含 `merge` 旗標 |
| `frontend/src/components/Step2Edit.tsx` | 修改 | 下載區加「全部頁合併成一張表」checkbox |

---

## Task 1：`merge_sheets` 純函式

**Files:**
- Modify: `backend/app/excel.py`
- Test: `backend/tests/test_merge_sheets.py`（新建）

- [ ] **Step 1: 寫失敗測試**

新建 `backend/tests/test_merge_sheets.py`：

```python
from app.excel import merge_sheets


def test_basic_stacks_rows_and_keeps_first_header():
    pages = [
        {"columns": ["項目", "金額"], "rows": [["現金", "100"], ["應收", "200"]]},
        {"columns": ["項目", "金額"], "rows": [["存貨", "300"], ["合計", "600"]]},
    ]
    out = merge_sheets(pages)
    assert out["columns"] == ["項目", "金額"]
    assert out["rows"] == [["現金", "100"], ["應收", "200"],
                           ["存貨", "300"], ["合計", "600"]]


def test_drops_repeated_header_on_continuation_page():
    pages = [
        {"columns": ["項目", "金額"], "rows": [["現金", "100"]]},
        {"columns": ["項目", "金額"], "rows": [["項目", "金額"], ["存貨", "300"]]},
    ]
    out = merge_sheets(pages)
    assert out["rows"] == [["現金", "100"], ["存貨", "300"]]


def test_keeps_real_data_row_on_continuation_page():
    pages = [
        {"columns": ["項目", "金額"], "rows": [["現金", "100"]]},
        {"columns": ["項目", "金額"], "rows": [["存貨", "300"], ["合計", "600"]]},
    ]
    out = merge_sheets(pages)
    assert out["rows"][1] == ["存貨", "300"]  # 首列非表頭，未被刪


def test_pads_short_rows_and_keeps_long_rows():
    pages = [
        {"columns": ["a", "b", "c"], "rows": [["1"], ["1", "2", "3", "4"]]},
    ]
    out = merge_sheets(pages)
    assert out["rows"][0] == ["1", "", ""]            # 補空到 3
    assert out["rows"][1] == ["1", "2", "3", "4"]      # 長列保留不截


def test_header_taken_from_first_nonempty_columns():
    pages = [
        {"columns": [], "rows": [["x", "y"]]},
        {"columns": ["A", "B"], "rows": [["1", "2"]]},
    ]
    out = merge_sheets(pages)
    assert out["columns"] == ["A", "B"]


def test_all_columns_empty_uses_max_row_width():
    pages = [
        {"columns": [], "rows": [["1"]]},
        {"columns": [], "rows": [["1", "2", "3"]]},
    ]
    out = merge_sheets(pages)
    assert out["columns"] == []
    assert out["rows"][0] == ["1", "", ""]   # W = 最長列 3，短列補空


def test_single_page_and_empty():
    assert merge_sheets([]) == {"columns": [], "rows": []}
    one = merge_sheets([{"columns": ["a"], "rows": [["1"]]}])
    assert one == {"columns": ["a"], "rows": [["1"]]}
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend; python -m pytest tests/test_merge_sheets.py -v`
Expected: FAIL — `merge_sheets` 不存在（ImportError）。

- [ ] **Step 3: 實作 `merge_sheets`**

在 `backend/app/excel.py` 的 `build_workbook` 之前（`_sheet_name` 附近）新增：

```python
def merge_sheets(pages_in_order: list[dict]) -> dict:
    """把依頁碼排序的多頁 {columns, rows} 疊接清理成單一 {columns, rows}。

    規則（見設計 §合併演算法）：
    - 表頭取第一個 columns 非空的頁；全空則表頭為 []。
    - 欄數 W：表頭非空 → len(表頭)；表頭空 → 各頁所有列中最長列長度。
    - 逐頁疊接 rows：不附加任何頁的 columns；第一頁之後，若某頁第一列逐格
      去空白後等於合併表頭，視為重複表頭並丟棄；列短於 W 右補空，列長於 W 保留。
    """
    header: list[str] = []
    for p in pages_in_order:
        cols = [str(c) for c in (p.get("columns") or [])]
        if cols:
            header = cols
            break

    if header:
        width = len(header)
    else:
        width = 0
        for p in pages_in_order:
            for r in (p.get("rows") or []):
                width = max(width, len(r))

    header_trimmed = [h.strip() for h in header]
    out_rows: list[list[str]] = []
    for idx, p in enumerate(pages_in_order):
        rows = [[("" if c is None else str(c)) for c in r]
                for r in (p.get("rows") or [])]
        if idx > 0 and header and rows:
            if [c.strip() for c in rows[0]] == header_trimmed:
                rows = rows[1:]
        for r in rows:
            if len(r) < width:
                r = r + [""] * (width - len(r))
            out_rows.append(r)
    return {"columns": header, "rows": out_rows}
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd backend; python -m pytest tests/test_merge_sheets.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/excel.py backend/tests/test_merge_sheets.py
git commit -m "feat(excel): merge_sheets 多頁疊接清理成單一表"
```

---

## Task 2：`build_workbook` 支援自訂工作表名

**Files:**
- Modify: `backend/app/excel.py`（`_sheet_name` 重構 + `build_workbook` 加參數）
- Test: `backend/tests/test_merge_sheets.py`（新增測試）

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_merge_sheets.py` 末尾追加：

```python
import io
import openpyxl
from app.excel import build_workbook


def test_build_workbook_custom_sheet_title():
    data = build_workbook({1: {"columns": ["a"], "rows": [["1"]]}},
                          sheet_titles={1: "2024財報"})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["2024財報"]


def test_build_workbook_custom_title_sanitized_and_truncated():
    long_name = "報表/名稱:" + "X" * 40
    data = build_workbook({1: {"columns": [], "rows": [["1"]]}},
                          sheet_titles={1: long_name})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    name = wb.sheetnames[0]
    assert "/" not in name and ":" not in name      # 非法字元剔除
    assert len(name) <= 31                            # Excel 上限


def test_build_workbook_default_naming_unchanged():
    data = build_workbook({3: {"columns": ["a"], "rows": [["1"]]}})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["第3頁"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend; python -m pytest tests/test_merge_sheets.py -v -k build_workbook`
Expected: FAIL — `build_workbook` 不接受 `sheet_titles`（TypeError）。

- [ ] **Step 3: 重構 `_sheet_name` 並改 `build_workbook`**

在 `backend/app/excel.py`，把現有：
```python
_ILLEGAL_SHEET = re.compile(r"[\[\]:*?/\\]")


def _sheet_name(page_no: int) -> str:
    return _ILLEGAL_SHEET.sub("", f"第{page_no}頁")[:31]
```
改為：
```python
_ILLEGAL_SHEET = re.compile(r"[\[\]:*?/\\]")


def _sanitize_sheet_title(name: str) -> str:
    """剔除 Excel 工作表名非法字元並截到 31 字；空字串以 'Sheet' 保底。"""
    s = _ILLEGAL_SHEET.sub("", name)[:31]
    return s or "Sheet"


def _sheet_name(page_no: int) -> str:
    return _sanitize_sheet_title(f"第{page_no}頁")
```

把 `build_workbook` 的簽章與工作表命名一行改為：
```python
def build_workbook(pages_structured: dict, sheet_titles: dict | None = None) -> bytes:
    """{page_no: {columns, rows}} → .xlsx bytes（每頁一個工作表）。
    sheet_titles 給定時，對應 page_no 改用自訂工作表名（會自動剔除非法字元、截 31 字）。"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for page_no in sorted(pages_structured):
        st = pages_structured[page_no]
        custom = (sheet_titles or {}).get(page_no)
        title = _sanitize_sheet_title(custom) if custom else _sheet_name(page_no)
        ws = wb.create_sheet(title=title)
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
（其餘 `build_workbook` 內容不變。）

- [ ] **Step 4: 執行測試確認通過**

Run: `cd backend; python -m pytest tests/test_merge_sheets.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 回歸既有 excel 測試**

Run: `cd backend; python -m pytest tests/test_excel.py -v`
Expected: PASS（`build_workbook` 預設行為不變）

- [ ] **Step 6: Commit**

```bash
git add backend/app/excel.py backend/tests/test_merge_sheets.py
git commit -m "feat(excel): build_workbook 支援自訂工作表名（合併用）"
```

---

## Task 3：`/api/excel` 加 `merge` 旗標

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`（`export_excel`）
- Test: `backend/tests/test_api.py`（新增整合測試）

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_api.py` 末尾追加（檔案頂部已 `from fastapi.testclient import TestClient`、`client = TestClient(app)`；新增 io/openpyxl import）：

```python
import io
import openpyxl


def _excel_req(merge: bool):
    return {
        "file_name": "2024財報.pdf",
        "sheets": {
            "1": {"columns": ["項目", "金額"], "rows": [["現金", "100"]]},
            "2": {"columns": ["項目", "金額"], "rows": [["項目", "金額"], ["存貨", "300"]]},
        },
        "merge": merge,
    }


def test_excel_merge_true_single_sheet_named_by_file():
    r = client.post("/api/excel", json=_excel_req(True))
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["2024財報"]                 # 檔名主檔名命名
    ws = wb["2024財報"]
    # 表頭列 + 現金 + 存貨（第2頁重複表頭列被移除）
    values = [[c.value for c in row] for row in ws.iter_rows()]
    assert values == [["項目", "金額"], ["現金", "100"], ["存貨", "300"]]


def test_excel_merge_false_keeps_per_page_sheets():
    r = client.post("/api/excel", json=_excel_req(False))
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["第1頁", "第2頁"]


def test_excel_merge_defaults_false_when_omitted():
    body = _excel_req(False)
    del body["merge"]
    r = client.post("/api/excel", json=body)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["第1頁", "第2頁"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend; python -m pytest tests/test_api.py -v -k excel_merge`
Expected: FAIL — `ExcelRequest` 無 `merge`；端點未走合併（merge=true 仍輸出兩張工作表）。

- [ ] **Step 3: 加 `merge` 欄位**

`backend/app/schemas.py` 的 `ExcelRequest` 改為：
```python
class ExcelRequest(BaseModel):
    file_name: str
    sheets: Dict[str, Sheet]
    merge: bool = False
```

- [ ] **Step 4: 改 `export_excel`**

`backend/app/main.py` 的 `export_excel` 改為（保留現有 400 守衛與標頭邏輯，只在組 workbook 處分流）：
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
    stem = Path(req.file_name).stem or "result"
    if req.merge:
        pages_in_order = [structured[p] for p in sorted(structured)]
        merged = excel.merge_sheets(pages_in_order)
        data = excel.build_workbook({1: merged}, sheet_titles={1: stem})
    else:
        data = excel.build_workbook(structured)
    quoted = urllib.parse.quote(f"{stem}.xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd backend; python -m pytest tests/test_api.py -v -k excel`
Expected: PASS

- [ ] **Step 6: 全後端回歸**

Run: `cd backend; python -m pytest -q`
Expected: PASS（既有 + 新測試全綠）

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(api): /api/excel 加 merge 旗標合併成單一工作表"
```

---

## Task 4：前端 `exportExcel` 帶 `merge`

**Files:**
- Modify: `frontend/src/api.ts`（`exportExcel`）
- Test: `frontend/src/api.test.ts`

vitest 在本機跑法：`cd frontend; node node_modules/vitest/vitest.mjs run src/api.test.ts`（若 vitest 起不來：先 `npm install --no-save @rolldown/binding-win32-x64-msvc@1.0.3`，不動 package.json/lock）。型別檢查用 `node node_modules/typescript/bin/tsc -b`（bare `tsc --noEmit` 不檢查任何東西）。

- [ ] **Step 1: 寫失敗測試**

在 `frontend/src/api.test.ts` 追加（沿用既有 fetch stub 與 `afterEach(() => vi.restoreAllMocks())`，勿重複 import）：

```typescript
describe('exportExcel', () => {
  it('posts merge flag in JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, blob: async () => new Blob(['x']),
    })
    vi.stubGlobal('fetch', fetchMock)
    await api.exportExcel('f.pdf', { '1': { columns: [], rows: [] } }, true)
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/excel')
    expect(JSON.parse(opts.body)).toEqual({
      file_name: 'f.pdf', sheets: { '1': { columns: [], rows: [] } }, merge: true,
    })
  })
})
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd frontend; node node_modules/vitest/vitest.mjs run src/api.test.ts`
Expected: FAIL — `exportExcel` 目前不收 `merge`、body 無 `merge`。

- [ ] **Step 3: 改 `exportExcel`**

`frontend/src/api.ts` 將 `exportExcel` 換成：
```typescript
export async function exportExcel(
  fileName: string, sheets: Record<string, Sheet>, merge: boolean,
): Promise<Blob> {
  const r = await fetch(`${BASE}/excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, sheets, merge }),
  })
  if (!r.ok) throw new Error(`Excel 匯出失敗 (${r.status})`)
  return r.blob()
}
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd frontend; node node_modules/vitest/vitest.mjs run src/api.test.ts`
Expected: PASS

- [ ] **Step 5: 型別檢查（預期僅 Step2Edit arity 錯，Task 5 修）**

Run: `cd frontend; node node_modules/typescript/bin/tsc -b`
Expected: 僅 `Step2Edit.tsx` 對 `exportExcel` 的呼叫少一個引數（TS2554）。這是預期的，Task 5 修。若有其他無關新錯誤才需調查。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(web): exportExcel 帶 merge 旗標"
```

---

## Task 5：步驟2 加「合併成一張表」下載開關

**Files:**
- Modify: `frontend/src/components/Step2Edit.tsx`
- 驗證：型別檢查 + 全前端測試 + build

- [ ] **Step 1: 先讀現況**

讀 `frontend/src/components/Step2Edit.tsx`，找到 `const [excelBusy, setExcelBusy] = useState(false)`、`downloadExcel()` 內的 `api.exportExcel(meta?.file_name ?? 'result', sheets)`、以及底部 `<div className="actions">` 的「下載 Excel」按鈕。

- [ ] **Step 2: 加區域狀態**

在既有 `const [excelBusy, setExcelBusy] = useState(false)` 旁新增：
```typescript
  const [mergeExport, setMergeExport] = useState(false)
```

- [ ] **Step 3: 下載帶上 mergeExport**

把 `downloadExcel` 內：
```typescript
      const blob = await api.exportExcel(meta?.file_name ?? 'result', sheets)
```
改為：
```typescript
      const blob = await api.exportExcel(meta?.file_name ?? 'result', sheets, mergeExport)
```

- [ ] **Step 4: 加 checkbox（單頁不顯示）**

在 `<div className="actions">` 內、「下載 Excel」按鈕之前，插入：
```tsx
        {pnos.length > 1 && (
          <label className="mergeopt">
            <input
              type="checkbox"
              checked={mergeExport}
              onChange={(e) => setMergeExport(e.target.checked)}
            />
            全部頁合併成一張表
          </label>
        )}
```
（`pnos` 已於元件內定義為排序後的頁碼陣列。）

- [ ] **Step 5: 型別檢查 + 全前端測試 + build**

Run: `cd frontend; node node_modules/typescript/bin/tsc -b`
Expected: 無錯誤（Step2Edit arity 錯已消失）。

Run: `cd frontend; node node_modules/vitest/vitest.mjs run`
Expected: 全部測試通過。

Run: `cd frontend; npm run build`
Expected: build 成功。

- [ ] **Step 6: 手動驗收**

啟動後端 `cd backend; .\run_api.bat`、前端 `cd frontend; npm run dev`，開 http://localhost:5173 ：
1. 辨識一份多頁檔 → 步驟2 出現「全部頁合併成一張表」checkbox（預設不勾）。
2. 不勾下載 → Excel 每頁一張工作表（現狀）。
3. 勾選下載 → Excel 只有一張工作表、名為檔名主檔名、跨頁內容無縫接續、續頁重複表頭已移除。
4. 單頁檔 → 不顯示該 checkbox。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Step2Edit.tsx
git commit -m "feat(web): 步驟2 下載 Excel 可選擇合併成一張表"
```

---

## Self-Review 紀錄

- **Spec 覆蓋**：手動開關（Task 5 checkbox、Task 3 merge 旗標）、合併範圍＝所有頁（Task 3 依頁碼排序全傳入）、機械式疊接+清理（Task 1 `merge_sheets`：首頁欄位/移除續頁重複表頭/補空/長列不截）、只影響下載（Task 5 區域狀態、不進 reducer；螢幕逐頁不動）、完全無縫（Task 1 不插分隔列/欄）、後端負責（方案 A）、合併工作表用檔名命名（Task 2 `sheet_titles` + Task 3 `stem`）、預設關閉（schema 預設 False、checkbox 預設不勾）。皆有對應任務。
- **命名一致**：`merge_sheets`、`build_workbook(sheet_titles=...)`、`_sanitize_sheet_title`、`exportExcel(fileName, sheets, merge)`、`mergeExport` 於各任務定義與使用一致。
- **回歸**：Task 2 Step 5、Task 3 Step 6 要求既有 excel／全後端測試保持綠；`build_workbook` 與 `exportExcel` 既有行為在 merge=false 時不變。
- **無佔位符**：每個程式步驟皆附完整程式碼與預期輸出。
