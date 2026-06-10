# Excel 跨頁合併（Merge Pages into One Sheet）設計

- 日期：2026-06-10
- 狀態：設計已確認，待寫實作計畫
- 範圍：前後端分離版（backend FastAPI + frontend React/Vite）
- 相關：建立在「選頁辨識」之上（`2026-06-09-page-selection-ocr-design.md`）

## 背景與目標

目前多頁檔案下載 Excel 時，**每頁各自成為一個工作表**。當一張財報跨兩頁（會計內容延續）時，內容被拆到兩個工作表，使用者難以連續解讀。

本功能讓使用者在下載時選擇**把本次辨識的所有頁合併成單一工作表**，讓跨頁報表讀起來像一張連續的表。

## 需求摘要（已與使用者確認）

1. **手動、由使用者決定**：下載時一個開關「全部頁合併成一張表」，預設**關閉**。系統不自動偵測、不分組。
2. **合併範圍＝本次辨識的所有頁**。理由：辨識前的「選頁」功能已讓使用者決定要哪些頁，故毋需再做頁分組 UI。若使用者同一次選了不同報表的頁，合併會把它們併在一起——這是使用者的選擇（要分開就分次辨識或不勾合併）。
3. **機械式疊接 + 清理**（不重跑 LLM）：保留使用者在各頁所做的手動編輯。
4. **只影響下載的 Excel**：螢幕步驟2 維持逐頁顯示／編輯，不變。
5. **完全無縫**：頁交界不插分隔列、不加來源頁欄位。
6. 後端負責合併邏輯（方案 A）。

## 採用方案：A — 合併邏輯放後端 `excel.py`

前端只多送一個 `merge` 旗標；後端新增純函式 `merge_sheets` 把多頁 `{columns, rows}` 疊接清理成單一 `{columns, rows}`，再交給既有 `build_workbook`。清理規則屬資料處理，與 Excel 產生同層、用 pytest 好測；前端維持極薄。

否決方案 B（前端 TS 合併）：清理啟發式寫在 TS、無法與未來其他匯出路徑共用，資料清理放 Python 較自然。

## 資料流

```
步驟2（畫面逐頁不變）
  state.tables = { 3:{cols,rows}, 5:{...}, 8:{...} }
        │ 按「下載 Excel」，帶開關 mergeExport
        ▼ POST /api/excel { file_name, sheets, merge }
  export_excel：
     merge=false → build_workbook(每頁一張)            （現有行為，不動）
     merge=true  → merge_sheets(依頁碼排序的各頁) → 單一 {cols,rows}
                   → build_workbook({單一工作表})
        ▼ 回傳 .xlsx
```

契約：合併是下載階段的純資料轉換，不碰 `state.tables`、螢幕顯示、辨識結果。`merge` 預設 false。合併輸出單一工作表。

## 合併演算法 `merge_sheets`

輸入：依頁碼排序的各頁 `{columns, rows}` 清單。輸出：單一 `{columns, rows}`。

1. **決定表頭**：取第一個「columns 非空」的頁的 columns 當整張表唯一表頭；全空則表頭 `[]`。設欄數 `W`：表頭非空時 `W=len(表頭)`；表頭空時 `W=各頁所有列中最長列的長度`。
2. **逐頁疊接資料列**（依頁序）：
   - 不把任何頁的 `columns` 當資料列附加（續頁被獨立抽出的重複欄位標題自然丟棄）。
   - **移除續頁殘留重複表頭列**：第一頁之後的頁，若其**第一列**逐格去空白後等於合併表頭，丟棄該列。只比對「該頁第一列 vs 表頭」，避免誤刪真實資料。
   - **欄數對齊**：列短於 W → 右補空字串到 W；列長於 W → 保留不截斷（不丟資料）。
3. 輸出 `{columns: 合併表頭, rows: 疊接後所有列}`。

範例：
```
第1頁: cols=[項目,金額]  rows=[[現金,100],[應收,200]]
第2頁: cols=[項目,金額]  rows=[[項目,金額],[存貨,300],[合計,600]]   ← 首列重複表頭，丟棄
合併:  cols=[項目,金額]  rows=[[現金,100],[應收,200],[存貨,300],[合計,600]]
```

## 後端改動

### `backend/app/schemas.py`
```python
class ExcelRequest(BaseModel):
    file_name: str
    sheets: Dict[str, Sheet]
    merge: bool = False        # true → 全部頁合併成單一工作表
```

### `backend/app/excel.py`
新增純函式 `merge_sheets(pages_in_order: list[dict]) -> dict`，實作上述演算法。`build_workbook` 不改。

### `backend/app/main.py`（`export_excel`）
- `merge=false`：維持現狀（每頁一張工作表）。
- `merge=true`：把 `req.sheets` 依頁碼（int(key)）排序成清單 → `excel.merge_sheets(...)` → 以單一鍵丟給 `build_workbook`。
- **合併工作表命名**：用檔名主檔名（`Path(file_name).stem`，剔除非法字元、截 31 字）。`build_workbook` 目前以 `第{page_no}頁` 命名，故合併路徑需讓 `build_workbook` 能接受自訂工作表名（或在合併路徑改用既有 `_sheet_name` 之外的命名）。實作時讓合併分支以檔名主檔名作為該唯一工作表標題。

## 前端改動

### `frontend/src/api.ts`
`exportExcel(fileName, sheets, merge: boolean)` — body 改為 `{ file_name, sheets, merge }`。

### `frontend/src/components/Step2Edit.tsx`
- 下載「下載 Excel」按鈕旁加 checkbox「全部頁合併成一張表」，預設不勾。
- 元件區域狀態 `const [mergeExport, setMergeExport] = useState(false)`（純下載選項，不進全域 reducer）。
- `downloadExcel()` 改呼叫 `api.exportExcel(fileName, sheets, mergeExport)`。
- 單頁時（`pnos.length === 1`）不顯示此 checkbox。

其餘畫面（逐頁檢視、編輯、頁碼下拉）不動。

## 邊界情況

| 情況 | 處理 |
|---|---|
| 只辨識一頁卻 merge=true | `merge_sheets` 單頁輸入＝原樣輸出；前端單頁不顯示開關 |
| 所有頁 columns 都空 | 表頭 `[]`，`W` 取最長列長度，疊接並各列補空到 W |
| 某頁 rows 全空 | 該頁不貢獻列 |
| 全部頁皆空 | 合併輸出空表；`build_workbook` 沿用「至少一張工作表」保底 |
| 續頁首列像表頭但其實是資料 | 只在逐格完全等於表頭時刪，極難誤刪真實數字列 |
| 列比表頭長 | 保留不截斷 |
| 頁碼非連續（3,5,8）且 merge | 依頁碼排序後無縫疊接；工作表用檔名命名 |

## 測試規劃

### 後端（pytest，新建 `backend/tests/test_merge_sheets.py`）
- 基本疊接：兩頁同欄位 → 列數相加、表頭取第一頁。
- 移除續頁重複表頭：續頁首列等於表頭 → 被丟棄。
- 不誤刪：續頁首列為真實資料 → 保留。
- 欄數對齊：短列補空到 W；長列保留不截。
- 表頭挑選：第一頁 columns 空、第二頁非空 → 用第二頁 columns 當表頭。
- 全空頁／單頁輸入 → 合理輸出。
- 端點整合：`POST /api/excel {merge:true}` 回 200 且為合法 xlsx；用 openpyxl 讀回確認**只有一張工作表、列數正確、工作表名＝檔名主檔名**。並保留一個 `merge:false` 維持每頁一張的回歸測試。

### 前端（vitest）
- `api.test.ts`：`exportExcel(..., true)` body 含 `merge:true`；`exportExcel(..., false)` 含 `merge:false`。
- UI checkbox 互動不寫單元測試（邏輯由後端 + api 測試覆蓋），以 build／型別檢查把關。

## 不做（YAGNI）

- 不做自動偵測「哪些頁是延續」。
- 不做頁分組 UI（指定哪幾頁併哪幾頁）。
- 不重跑 LLM 統一欄位語意。
- 不插頁分隔列、不加來源頁欄位。
- 不改螢幕步驟2 的逐頁顯示／編輯。
- 不做合併結果的線上預覽（合併只在下載時發生）。
