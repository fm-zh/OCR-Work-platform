# 選頁辨識（Page Selection OCR）設計

- 日期：2026-06-09
- 狀態：設計已確認，待寫實作計畫
- 範圍：前後端分離版（backend FastAPI + frontend React/Vite）

## 目標

讓使用者在辨識**之前**，從一份多頁檔案中挑選要處理的特定頁，僅對選到的頁執行完整辨識管線。

**主因**：只需要特定幾頁（例如 30 頁財報只要資產負債表、損益表）。
**次要效益**：省時間（OCR 是最慢一步，沒選的頁完全不跑）；在頁數上限內最大化利用。

## 需求摘要（已與客戶確認）

1. 辨識前可挑選要處理的頁，**預設不選**，附「全選／全不選」按鈕。
2. 選頁方式：**縮圖打勾 ＋ 頁碼輸入（如 `3,5,8-10`）兩者同步**，共用同一份選取狀態。
3. 頁數上限**維持上傳時檢查**（掃描檔 ≤30、文字層檔 ≤60）。選頁只在合格檔案內挑頁，不為破限而放寬上傳。
4. **掃描檔與文字層檔都套用**；文字、表格、Excel **只輸出選到的頁**。
5. **保留原始頁碼**（選 3、5、8 → 輸出與 Excel 工作表標為 3、5、8，不重編號）。
6. 一頁都沒選時擋住不給辨識（前端按鈕禁用 + 後端驗證雙保險）。

## 採用方案：A — 在辨識引擎裡只處理選到的頁

選頁清單一路往下傳進引擎的逐頁迴圈，沒選的頁在渲染（`get_pixmap`）**之前**就跳過。

對沒選的頁，以下全部不發生：700 DPI 渲染、`red_to_black` 去紅前處理、暫存 JPEG、打包上傳 PaddleOCR、LLM 校正。這是省時間的真正來源。

**否決方案 B**（全部辨識後再濾輸出）：完全沒省到時間，違背次要效益。
**否決方案 C**（先抽成子 PDF 再走現有管線）：子 PDF 會重編頁碼，需額外維護「新頁碼→原始頁碼」映射，多一層易錯；掃描檔多一次 PDF 編解碼。

## 資料流

```
步驟1 前端                後端 API                    引擎
─────────              ─────────                  ─────
勾選縮圖 / 輸入 3,5,8  →  POST /recognize
  ↓ 整理成 [3,5,8]        body: {pages:[3,5,8]}    →  engine.recognize(path, pages=[3,5,8])
  （沒選→按鈕禁用）        ↓ 驗證頁碼合法（1..n_pages）   ↓
                          start_recognition(id,      掃描檔：只 render/OCR 第3,5,8頁
                            pages)                    文字層：只取第3,5,8頁
                                                      ↓ 結果 key 回填為原始頁碼
步驟2 ← 輪詢狀態      ←   job.pages={3:..,5:..,8:..} ←
  只顯示 3,5,8 頁、Excel 也只有這三頁
```

**單一事實來源**：選頁清單，全程使用**原始頁碼**。後端啟動辨識前去重、排序、範圍驗證。

## 後端改動（5 檔）

### `schemas.py`
新增請求模型：
```python
class RecognizeRequest(BaseModel):
    pages: List[int]   # 原始頁碼，如 [3,5,8]
```

### `main.py`
- `/api/jobs/{id}/recognize` 從「無 body」改為收 `RecognizeRequest`。
- 驗證（不合法回 `400`）：非空、每個頁碼在 `1..job.n_pages`、去重 + 排序後往下傳。

### `jobs.py`
- `start_recognition(job_id, pages)` 多收 `pages`，存到 `Job`（步驟 2 可知實際辨識了哪幾頁）。
- `_run` 呼叫 `engine.recognize(path, pages=pages, progress=...)`。

### `engine.py`
- `recognize(path, pages, progress)` 透傳 `pages` 給 `ocr_recognize.recognize(...)`。

### `ocr_recognize.py` + `ocr_lib.py`
- `iter_hidpi(pdf, dpi, pages=None)`：迴圈內，未選頁在 `get_pixmap` 之前 `continue`；改成 `yield (page_no, image)`，吐出**原始頁碼**。
- `recognize(..., pages=None)`：
  - 文字層檔：`extract_text_layer` 後用 `pages` 過濾 dict（key 本即原始頁碼）。
  - 掃描檔：只前處理／OCR 選到的頁。

### 頁碼回填（最高風險點）
PaddleOCR 依「送進去 PDF 內第幾頁」標記 `--- 第 N 頁 ---`，回來是 1、2、3…（送幾頁就從 1 編），**非原始頁碼**。辨識後需做一次**位置→原始頁碼**映射：第 k 個處理頁 = 排序後選頁清單第 k 個。例：選 `[3,5,8]`、OCR 回 `{1,2,3}` → 回填成 `{3,5,8}`。掃描檔多批時尤其要驗，不可串頁。文字層檔不受影響。

## 前端改動（3 檔 + 1 新檔）

### `state.ts`
- `AppState` 新增 `selected: number[]`（排序後原始頁碼）。
- 新增 actions：`TOGGLE_PAGE`、`SET_SELECTED`、`SELECT_ALL`、`CLEAR_SELECTED`。
- `SET_META` 與 `RESET` 清空 `selected`（落實「預設不選」）。

### `lib/pageRange.ts`（新檔，純函式 + 測試）
- `parseRange("3,5,8-10", n_pages) → [3,5,8,9,10]`：去空白、忽略超範圍、去重排序、展開區段、反向區段視為無效。
- `formatRange([3,5,8,9,10]) → "3,5,8-10"`：壓回精簡字串。

### `Step1Upload.tsx`
- 上傳後，把「單張縮圖 + 頁碼下拉」換成**縮圖格狀清單**：每張縮圖角落勾選框，選中高亮。
- 上方控制列：頁碼輸入框（綁 `formatRange(selected)`，打字 → `parseRange` → `SET_SELECTED`）、「全選」「全不選」、即時統計「已選 3 / 30 頁」。
- 同步：兩者都只讀寫同一個 `selected`。
- 單頁檔：自動視為已選該頁。
- 防呆：`selected.length === 0` 時「開始辨識」按鈕禁用 + 提示。

### `api.ts`
- `startRecognize(jobId, pages)` 帶 JSON body `{ pages }`，沿用現有錯誤透傳。

### 步驟 2（不需大改）
結果依 `status.pages` 的 key 顯示，後端已只回選到的頁、且為原始頁碼 → 頁碼下拉、文字／表格、Excel 自然只剩選到的頁。

## 邊界情況

| 情況 | 處理 |
|---|---|
| 一頁都沒選就辨識 | 前端按鈕禁用 + 提示；後端 `400` |
| 頁碼超範圍（50 頁輸入 99） | `parseRange` 以 `n_pages` 為界忽略；後端再驗，回 `400` |
| 反向／亂序／重複（`5-3`、`8,3,3`） | `parseRange` 容錯：反向無效、去重、排序 |
| 全選（等於現行全部辨識） | 回歸測試確保結果與舊版一致 |
| 單頁檔 | 自動已選該頁，不顯示多餘勾選 |
| 掃描檔多批 OCR 的頁碼回填 | 重點測項：非連續頁（`3,5,8`）跨批，驗回填正確不串頁 |
| 文字層檔選頁 | 驗 `extract_text_layer` 後過濾，key 維持原始頁碼 |
| 暫存清理 | 沿用 `tempfile` + `shutil.rmtree`；跳過頁不產生暫存，無洩漏 |

## 測試規劃

### 後端（pytest，`backend/tests/`）
- `/recognize` 收空清單、超範圍、重複 → `400`／正規化。
- 引擎過濾（mock OCR client）：`pages=[3,5,8]` → 只渲染這三頁、結果 key `{3,5,8}`。
- 頁碼回填：模擬 OCR 回 `第 1/2/3 頁`、選 `[3,5,8]` → 結果 `{3,5,8}`；多批另一案。
- 回歸：全頁時結果與現行一致。

### 前端（vitest，既有 `*.test.ts`）
- `pageRange.test.ts`：`parseRange`／`formatRange` 往返與容錯（亂序、重複、超頁、區段、反向）。
- `state.test.ts`：`TOGGLE_PAGE`／`SET_SELECTED`／`SELECT_ALL`／`CLEAR_SELECTED`／`SET_META` 清空。
- `api.test.ts`：`startRecognize` 帶正確 body。

### 手動驗收
多頁掃描檔 → 只選 `3,5,8` → 進度僅顯示這幾頁前處理 → 步驟 2 只有三頁、頁碼正確 → Excel 三個工作表頁碼 3/5/8。

## 不做（YAGNI）

- 不放寬上傳頁數上限（維持上傳時檢查）。
- 不為破限做「只渲染指定範圍附近縮圖」的安全閥（方案 C 的延伸）。
- 不做選頁的記憶／預設樣板（預設一律不選）。
- 不做頁碼重編號選項。
