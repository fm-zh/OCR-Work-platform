# Excel 匯出設計規格（DeepSeek 結構化 → openpyxl）

日期：2026-06-03
狀態：設計定稿，待寫實作計畫

## 1. 目的

讓使用者把辨識結果「按原 PDF 的格式」整理成 Excel（.xlsx）並下載。前後端分離版（FastAPI 後端 :8000 ＋ React 前端 :5173）新增此功能。

做法：用 DeepSeek 把每頁辨識文字整理成結構化表格（欄／列），後端以 openpyxl 產生每頁一個工作表的 .xlsx，前端按鈕下載。

## 2. 範圍

- 在前端步驟 2（結果與對照編輯）新增「⬇ 下載 Excel」按鈕。
- 使用**編輯後**的各頁文字（使用者在右欄修改的內容會反映到 Excel）。
- 每頁 → 一個工作表。
- 儲存格值**保留原始文字格式**（逗號、括號負號 `(588)`、`%`），以貼近原表。

## 3. 架構與資料流

```
React 步驟2「下載 Excel」
  → POST /api/excel  { file_name, pages: {"1": "...", "2": "..."} }   (編輯後文字)
  → 後端 excel.structure_page(text)  ──DeepSeek(json_object)──▶  {columns?, rows}
  → 後端 excel.build_workbook(...)  ──openpyxl──▶  .xlsx bytes
  → 回傳檔案（Content-Disposition: attachment; <stem>.xlsx）
  → 前端取 blob → 觸發下載
```

- 同步端點（DeepSeek 約 10–20 秒），前端按鈕顯示「產生中…」並防重複點擊。
- DeepSeek 金鑰由後端 `.env` 讀取（沿用既有 `resolve_deepseek_key`）。

## 4. 後端設計

### 4.1 新模組 `backend/app/excel.py`

- `structure_page(text: str, api_key: str) -> dict`
  - 呼叫 DeepSeek（`deepseek-chat`，`response_format={"type":"json_object"}`）。
  - 回傳 `{"columns": list[str] | [], "rows": list[list[str]]}`。
  - 提示要點：把該頁財報文字整理成表格 JSON；欄位依內容判斷（如 `項目/金額/百分比` 或 `代碼/科目/金額`）；儲存格保留原始文字（逗號、`(負值)`、`%`）；只輸出 JSON。
  - 防呆：DeepSeek 回應無法解析成預期結構時，退化為 `{"columns": [], "rows": [[line] for line in text.splitlines() if line.strip()]}`（每行一列單欄），不讓匯出失敗。

- `build_workbook(pages_structured: dict[int, dict]) -> bytes`（**純函式、可離線測試**）
  - 用 openpyxl 建活頁簿；移除預設工作表；對每個 page（依頁碼排序）建一個工作表，名稱 `第{n}頁`（openpyxl 工作表名上限 31 字、不可含 `[]:*?/\\`，需清理）。
  - 若該頁 `columns` 非空 → 第 1 列寫表頭；其後逐列寫 `rows`。每個 cell 一律以字串寫入。
  - 回傳 xlsx 的 bytes（`openpyxl.Workbook.save` 到 `io.BytesIO`）。

### 4.2 端點（`backend/app/main.py`）

- `POST /api/excel`，請求模型 `ExcelRequest { file_name: str, pages: Dict[str, str] }`。
  - 對每頁呼叫 `excel.structure_page(text, resolve_deepseek_key())`。
  - `excel.build_workbook({int(k): structured})` → bytes。
  - 回傳 `Response(content=bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'})`，其中 stem = `file_name` 去副檔名（檔名含非 ASCII 時用 RFC 5987 `filename*=UTF-8''...` 以免 header 編碼問題）。
  - `pages` 為空 → 400。
- 相依：`openpyxl`（加入 `backend/requirements-backend.txt`）。

## 5. DeepSeek 結構化規格

- 模型 `deepseek-chat`、`temperature=0`、`response_format={"type":"json_object"}`。
- 每頁一次呼叫，輸入該頁文字，要求輸出單一 JSON 物件 `{"columns": [...], "rows": [[...], ...]}`。
- 解析：`json.loads`；驗證為 dict 且 `rows` 為 list of list；任一不符即套用防呆退化。

## 6. 前端設計

- `src/api.ts` 新增 `exportExcel(fileName: string, pages: Record<string,string>): Promise<Blob>`
  - `POST /api/excel`，JSON body `{ file_name, pages }`，回應為 blob（`res.blob()`）；`!res.ok` 拋錯。
- `src/components/Step2Edit.tsx`：
  - 動作列新增「⬇ 下載 Excel」按鈕（在「下載 .txt」旁）。
  - 點擊：組 `final` 各頁（編輯後）→ `exportExcel(meta.file_name, finalAsStringKeys)` → 取 blob → 以 `<a download="<stem>.xlsx">` 觸發下載。
  - 本地 `useState` 控制「產生中…」狀態，期間 disabled；失敗顯示錯誤訊息。

## 7. 測試

- **後端（離線）**：
  - `build_workbook`：餵固定結構（含一頁有 columns、一頁無 columns）→ 用 openpyxl 從回傳 bytes 讀回 → 斷言工作表名、表頭列、儲存格值。
  - 端點 `POST /api/excel`：以 `monkeypatch` 把 `app.excel.structure_page` 換成回固定結構的 stub（不打 DeepSeek）→ 斷言 200、`content-type` 為 xlsx、回傳 bytes 可被 openpyxl 開啟且工作表數＝頁數。
  - 空 `pages` → 400。
- **前端**：`exportExcel` 用 mock fetch 斷言 URL/method、回傳 blob。

## 8. 非目標（v1）

- 不把金額轉成數值型儲存格（保留原始文字格式；日後可選）。
- 不做合併儲存格、樣式美化、欄寬自動調整。
- 匯出為同步端點（非 async job）。
- 不快取結構化結果（每次下載重新呼叫 DeepSeek）。

## 9. 成功標準

- 後端 `POST /api/excel`（structure 以 stub 測）回傳可開啟的 .xlsx，工作表數＝頁數、表頭與列正確；空 pages→400；後端測試全綠。
- 前端步驟 2 出現「⬇ 下載 Excel」，點擊後實機（接真 DeepSeek）下載到與原檔同名的 .xlsx，每頁一個工作表、欄位貼近原表、儲存格保留原始文字。
- 既有功能（.txt 下載、辨識流程、現有測試）不受影響。
