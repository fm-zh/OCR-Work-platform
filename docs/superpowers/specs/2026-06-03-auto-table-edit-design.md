# 辨識後自動表格整理＋表格編輯＋Excel 設計規格

日期：2026-06-03
狀態：設計定稿，待寫實作計畫
取代範圍：調整既有「Excel 匯出」功能（spec 2026-06-03-excel-export）的觸發時機與 UI。

## 1. 目的

辨識完成後**自動**用 DeepSeek 把每頁整理成表格，並把表格直接呈現在結果分頁、提供**儲存格編輯**與 **Excel 下載**。移除原本的「文字編輯」與「.txt 下載」：文字只保留**唯讀檢視**。

## 2. 與現況差異

| 項目 | 現況 | 改為 |
|---|---|---|
| 表格整理時機 | 按「下載 Excel」時才呼叫 DeepSeek | 進入步驟 2 後**自動**在背景整理 |
| 結果編輯 | 純文字 textarea 可編輯 | 文字**唯讀**；**表格**儲存格可編輯 |
| 下載 | .txt（編輯後文字）＋ Excel | **只有 Excel**（編輯後表格） |
| `/api/excel` | 收文字、內部呼叫 DeepSeek | 收**已結構化表格**、純 openpyxl |

## 3. 流程（兩階段）

1. 辨識完成（既有流程）→ 自動進步驟 2，立即顯示**唯讀文字**。
2. 步驟 2 一進來自動觸發**表格整理**：`POST /api/jobs/{id}/structure` → 前端輪詢 `GET /api/jobs/{id}` → 「表格檢視」整理中顯示「整理中…」，`structure_status=done` 後顯示**可編輯表格**。
3. 文字檢視（唯讀）與表格檢視（可編輯）各自獨立；表格由「原始辨識文字」整理而來，不隨任何編輯即時重算。

## 4. 後端設計

### 4.1 結構化第二階段（`backend/app/jobs.py`）

- `Job` 新增欄位：
  - `structure_status: str = "idle"`（idle / running / done / error）
  - `tables: dict | None = None`（`{ "1": {"columns": [...], "rows": [[...]]}, ... }`，字串頁碼鍵）
  - `structure_error: str | None = None`
- `JobStore.start_structuring(job_id) -> Job | None`：
  - job 不存在 → None。
  - job.status != "done"（尚未辨識完）→ 不啟動，回 job（呼叫端據此回 409）。
  - structure_status 已 running/done → 回 job（idempotent，不重跑）。
  - 否則設 `structure_status="running"`，提交背景工作 `_run_structuring(job_id)`。
- `_run_structuring(job_id)`：
  - 取 job.pages（`{頁碼字串: 文字}`），對每頁並行（`self._pool`）呼叫 `excel.structure_page(text, resolve_deepseek_key())`。
  - 全部完成 → `job.tables = {頁碼: {columns, rows}}`、`structure_status="done"`。
  - 任一例外 → `structure_error`、`structure_status="error"`。
  - 金鑰透過 `engine.resolve_deepseek_key()`（或 `ocr_app_pro_helpers.resolve_deepseek_key`）。

### 4.2 端點（`backend/app/main.py`）

- `POST /api/jobs/{job_id}/structure`：
  - job 不存在 → 404；job.status != "done" → 409（detail：「請先完成辨識」）。
  - 呼叫 `store.start_structuring`；回 `{job_id, structure_status}`。
- `GET /api/jobs/{job_id}`（`JobStatus`）新增 `structure_status`、`tables`、`structure_error`。
- `POST /api/excel` **改寫**：請求模型 `ExcelRequest { file_name: str, sheets: Dict[str, SheetModel] }`，其中 `SheetModel { columns: list[str], rows: list[list[str]] }`。
  - sheets 為空 → 400。
  - `build_workbook({int(k): {"columns":..., "rows":...}})` → bytes → 回 `.xlsx`（同名、RFC5987 header，同現況）。
  - **不再於此呼叫 DeepSeek**（`excel.structure_page` 仍存在，由結構化階段使用）。

### 4.3 schemas（`backend/app/schemas.py`）

- `JobStatus` 加：`structure_status: str`、`tables: Optional[Dict[str, Sheet]]`、`structure_error: Optional[str]`。
- 新 `Sheet { columns: List[str]; rows: List[List[str]] }`。
- `ExcelRequest` 改為 `{ file_name: str; sheets: Dict[str, Sheet] }`。

## 5. 前端設計

### 5.1 型別（`src/types.ts`）

- 新 `Sheet { columns: string[]; rows: string[][] }`。
- `JobStatus` 加：`structure_status: 'idle' | 'running' | 'done' | 'error'`、`tables: Record<string, Sheet> | null`、`structure_error: string | null`。

### 5.2 狀態（`src/state.ts`）

- **移除**文字編輯：刪 `edited`、`EDIT` action。
- 新增：`view: 'text' | 'table'`（預設 'text'）、`tables: Record<number, Sheet>`（可編輯工作副本）。
- Actions：`SET_VIEW`、`SET_TABLES`（從輪詢結果載入工作副本）、`EDIT_CELL { page, row, col, value }`、`EDIT_HEADER { page, col, value }`。
- `SET_META`/`RESET` 一併清空 `tables`、`view='text'`。

### 5.3 步驟 2（`src/components/Step2Edit.tsx`）

- 左欄：原圖（`ZoomImage`）＋頁碼切換（不變）。
- 右欄上方：檢視切換鈕「文字（唯讀）／表格」。
- 文字檢視：唯讀顯示 `status.pages[page]`（`<textarea readOnly>` 或 `<pre>`）。
- 表格檢視：
  - `structure_status` 為 running/idle → 顯示「整理中…」。
  - done → 渲染可編輯表格：表頭 `columns`（`<input>`，`EDIT_HEADER`）、各列 `rows` 儲存格（`<input>`，`EDIT_CELL`）；資料來源為 `state.tables[page]`（工作副本）。
  - error → 顯示錯誤、提供「重試」按鈕（再次 `POST .../structure`）。
- 進入步驟 2 自動觸發整理：`useEffect`（依 jobId）— 若 `structure_status` 為 idle/未啟動則 `POST .../structure`，並以 interval 輪詢 `GET /jobs/{id}`，把回傳的 `tables` 經 `SET_TABLES` 載入工作副本、更新 `structure_status`；done/error 停止輪詢。
- 動作列：「⬇ 下載 Excel」（用 `state.tables` 編輯後內容 → `POST /api/excel`）、「🔄 辨識新檔案」。移除 .txt 下載。

### 5.4 API（`src/api.ts`）

- 新 `startStructure(jobId): Promise<{ job_id: string; structure_status: string }>` → `POST /api/jobs/{id}/structure`。
- `exportExcel(fileName, sheets: Record<string, Sheet>): Promise<Blob>` → `POST /api/excel`，body `{ file_name, sheets }`。
- 移除 `.txt` 相關（`combinePages` 不再被使用，可保留檔案或刪除其引用）。

## 6. 測試

- **後端（離線）**：
  - `start_structuring`：建立 job（born-digital 檔3、走辨識）→ 設 status done →（monkeypatch `excel.structure_page` 回固定 `{columns,rows}`）→ `start_structuring` → 輪詢 job 直到 `structure_status=done`、`tables["1"]` 正確。
  - `POST /api/jobs/{id}/structure`：未辨識完 → 409；辨識完 → 200、輪詢 `GET` 得 `tables`（monkeypatch）。
  - `POST /api/excel`（新版）：送 `{file_name, sheets:{"1":{columns,rows},"2":{...}}}` → 200、xlsx、openpyxl 開回工作表數＝sheets 數；空 sheets → 400。
- **前端**：`startStructure`/`exportExcel` mock fetch；reducer 測 `EDIT_CELL`/`EDIT_HEADER`/`SET_TABLES`/`SET_VIEW`/`RESET`；App 冒煙仍綠。

## 7. 非目標（v1）

- 文字↔表格不即時同步；不提供「依目前文字重整表格」。
- 表格不做數值型儲存格、合併格、樣式、增刪列。
- 不快取／持久化結構化結果（重啟即清）。
- 結構化仍為每頁一次 DeepSeek 呼叫（多頁並行；不分塊）。

## 8. 成功標準

- 辨識完成自動進步驟 2 顯示唯讀文字；表格在背景整理，完成後表格檢視顯示可編輯表格。
- 編輯儲存格後按「下載 Excel」，下載到與原檔同名 `.xlsx`，每頁一個工作表、內容＝編輯後表格。
- 後端 `start_structuring` 與 `/api/excel`（新版）測試全綠；前端測試全綠。
- 既有辨識流程不受影響。
