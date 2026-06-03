# 前後端分離設計規格（React SPA + FastAPI）

日期：2026-06-03
狀態：設計定稿，待寫實作計畫（分兩階段：先後端、後前端）

## 1. 目的與動機

把目前 Streamlit 整合式的進階版辨識網頁（`ocr_app_pro.py`）改為前後端分離。

動機（使用者確認）：
- **前端 UI/UX 要高度客製**（Streamlit 版面/互動限制太多）。
- **架構升級／未來擴充**。
- **與其他系統整合**（需穩定、有文件的 REST API）。

非動機：多人/公開部署/認證並非首要——v1 保持單程序、不做認證。

辨識引擎 `ocr_recognize.recognize()` 已與 UI 解耦，因此本案是「後端把引擎包成 API、前端做獨立 SPA 重現現有兩步驟流程」。

## 2. 範圍

第一版**完整重現現有進階版**功能，換成 React + FastAPI：
上傳 → 縮圖預覽確認 → 非同步辨識 → 原圖對照＋線上編輯 → 下載；born-digital 自動分流；辨識固定 PaddleOCR＋DeepSeek。

既有 Streamlit App（`ocr_app.py`@8502、`ocr_app_pro.py`@8503）與引擎模組**原封不動保留並行**。

## 3. 目標架構

```
React SPA (Vite+TS)  ──HTTP/JSON(REST)──▶  FastAPI 後端  ──函式呼叫──▶  既有 Python 引擎
   瀏覽器            ◀──輪詢狀態/取圖──     非同步任務管理              ocr_recognize / ocr_lib /
                                          + OpenAPI 文件               llm_correct / ocr_postprocess
                                                                              │ 外呼
                                                              PaddleOCR API / DeepSeek API
```

- 前端：所有畫面與互動，透過 REST API 與後端溝通。
- 後端：FastAPI，包裝引擎、管理非同步辨識任務、提供原圖預覽、自動產生 Swagger。
- 引擎：沿用現有模組，後端直接 import（不重寫）。
- 技術：前端 React + Vite + TypeScript；後端 FastAPI + uvicorn。

## 4. API 契約

任務生命週期：`created`（已上傳、預覽就緒、未辨識）→ `running` → `done` / `error`。

| 方法 | 路徑 | 用途 | 回傳 |
|---|---|---|---|
| POST | `/api/jobs` | 上傳檔案（multipart `file`）。存檔、偵測 born-digital/頁數、預先渲染原圖。**不辨識** | `JobMeta`（status=created） |
| GET | `/api/jobs/{id}/pages/{n}/image` | 取某頁原圖 PNG（預覽與對照用） | `image/png` |
| POST | `/api/jobs/{id}/recognize` | 開始辨識（背景任務、立即返回） | `{job_id, status:"running"}` |
| GET | `/api/jobs/{id}` | 輪詢狀態／進度／結果 | `JobStatus` |
| DELETE | `/api/jobs/{id}` | 清理暫存 | `204` |
| GET | `/api/health` | 健康檢查 | `{status:"ok"}` |

**JobMeta（POST /api/jobs）**
```jsonc
{ "job_id": "uuid", "file_name": "x.pdf", "n_pages": 3,
  "is_born_digital": false, "status": "created" }
```

**JobStatus（GET /api/jobs/{id}）**
```jsonc
{ "job_id": "uuid", "file_name": "x.pdf", "n_pages": 3, "is_born_digital": false,
  "status": "created" | "running" | "done" | "error",
  "progress": { "message": "DeepSeek 校正中…", "percent": 66 } | null,
  "mode": "PaddleOCR + DeepSeek" | null,        // done 時才有
  "pages": { "1": "…文字…", "2": "…" } | null,   // done 時才有（鍵為字串頁碼）
  "error": "…" | null }                          // error 時才有
```

關鍵語義：
- **上傳 ≠ 辨識**：`POST /jobs` 只上傳＋備好預覽；按「確認辨識」才 `POST /recognize`（對應步驟切換）。
- 辨識引擎固定 PaddleOCR＋DeepSeek（v1 不在 API 暴露 corrector 選擇）；born-digital 自動走文字層。
- **進度**：引擎 progress callback 寫入任務狀態，前端輪詢取得 `progress`。percent 採粗略對應（每則訊息 +22，上限 90；done 設 100）。
- **編輯與下載在前端**：前端取得 `pages` 後於瀏覽器內編輯、組與原檔同名 `.txt` 下載（後端不需下載端點；原始結果仍可由 GET /jobs/{id} 取得）。
- 自動產生 Swagger（`/docs`）供整合。
- `POST /recognize` 對已 running/done 的任務回目前狀態（不重複啟動）。

## 5. 後端設計（FastAPI）

結構：`backend/app/`
- `main.py`：FastAPI app、路由、CORS、啟動時 `load_env_file`。
- `jobs.py`：記憶體任務管理（`Job` dataclass、`JobStore` dict、建立/查詢/刪除、進度更新、背景辨識）。
- `schemas.py`：Pydantic 模型（JobMeta、JobStatus、Progress）。
- `engine.py`：薄包裝，import 既有 `ocr_recognize` / `ocr_lib` / `ocr_app_pro_helpers`（後端把平台根目錄加入 `sys.path` 以重用）。

細節：
- **任務儲存**：記憶體 dict `{job_id: Job}`。每任務一個暫存資料夾（`tempfile`）放上傳檔與預先渲染的 PNG。
- **背景辨識**：`POST /recognize` 以工作執行緒執行（`recognize()` 為阻塞網路呼叫），用 `asyncio.to_thread` 或 `ThreadPoolExecutor`；透過 progress callback 更新 `job.progress`；完成設 `done`（存 `pages`、`mode`），例外設 `error`（存訊息）。
- **預覽渲染**：上傳時即以 `ocr_lib.render_hidpi(path, 150)` 渲染各頁，存 PNG 至任務資料夾；image 端點回該檔。
- **金鑰**：啟動讀 `.env`（沿用 `ocr_app_pro_helpers.load_env_file` 與 `resolve_deepseek_key`）。
- **CORS**：`CORSMiddleware` 允許 `http://localhost:5173`（前端 dev），來源可由環境變數設定。
- **錯誤**：未知 job → 404；不支援的副檔名 → 400；辨識失敗 → 收進 `job.error`、status=error（非 500）。
- 伺服器：`uvicorn app.main:app --port 8000`。

## 6. 前端設計（React + Vite + TypeScript）

- 重現兩步驟流程；狀態驅動自動跳轉（輪詢到 `done` 即切步驟 2）。
- 模組：
  - `api.ts`：typed API client，包 6 個端點。
  - 狀態：`step / jobId / meta / status / pages / edited / curPage`（`useReducer` 或輕量 store）。
  - `Step1`（選檔/預覽/辨識）、`Step2`（對照/編輯/下載）、`StepNav`（步驟列）、`ZoomImage`（縮放/拖曳）、`Thumbnail`（規定範圍縮圖）。
- 步驟1：`<input type=file>` → `POST /jobs` → `<img src=image端點>` 顯示規定範圍縮圖（CSS 限制 max-width/height）＋頁碼切換 → 「確認辨識」→ `POST /recognize` → 以 `setInterval` 輪詢 `GET /jobs/{id}` 顯示進度。
- 步驟2：頁碼切換；左原圖可縮放/拖曳（輕量 pan-zoom，自寫或最小相依套件）、右 `textarea` 綁 `edited[page]`；下載按鈕在前端組同名 `.txt`（combinePages 的 TS 版：單頁純文字、多頁加 `===== 第 N 頁 =====`）；🔄 換檔（DELETE 舊 job、重置狀態）。
- 樣式：乾淨簡潔、相依最小化（CSS Modules 或極簡 UI；後續可高度客製）。

## 7. 專案結構與分階段

```
E:\OCR-Work-platform\
  (既有引擎 ocr_*.py + Streamlit ocr_app.py/ocr_app_pro.py 保留)
  backend\
    app\  main.py  jobs.py  schemas.py  engine.py
    tests\ test_api.py
    requirements-backend.txt
    run_api.bat            # uvicorn app.main:app --port 8000
  frontend\
    src\ ...  package.json  vite.config.ts  index.html
```

- **Phase 1（先做）**：後端 API——自帶 pytest（TestClient）＋ Swagger，本身即可交付整合價值。獨立一份實作 plan。
- **Phase 2（後做）**：前端 SPA——串接已穩定的 API。另一份實作 plan。
- 兩階段分開建置與審查；既有 Streamlit 不動、續存。

## 8. 測試

- **後端（Phase 1）**：pytest ＋ FastAPI `TestClient`。
  - 上傳 born-digital 檔（`E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf`）→ 200、status=created、n_pages=1、is_born_digital=true。
  - `GET .../pages/1/image` → 200、`content-type: image/png`。
  - `POST .../recognize` → 200（`status:"running"`）；輪詢 `GET /jobs/{id}` 直到 `done`，`pages["1"]` 非空、`mode=="文字層擷取"`（檔3 走文字層、免網路，測試離線可跑）。
  - 未知 job → 404；`DELETE` → 204 後再 GET → 404。
- **前端（Phase 2）**：vitest 輕量測 `api.ts` 與關鍵元件渲染冒煙；v1 保持精簡。

## 9. 非目標（v1）

- 認證／多人權限／並發擴展（單程序、記憶體任務、暫存於本機）。
- 任務持久化（重啟即清空）／DB／Redis／訊息佇列。
- corrector 選擇、Claude／Claude Vision（固定 DeepSeek）。
- production 部署（HTTPS／反向代理／容器化）——先 dev 跑通；prod 另議。
- 批次多檔上傳、Excel 匯出。

## 10. 成功標準

- 後端 `uvicorn` 起在 :8000，`/docs` 可看到 Swagger；pytest 全綠。
- 透過 API 走完：上傳檔3 → 取得預覽圖 → recognize → 輪詢 done → 取得 pages（文字層 100%）。
- 前端起在 :5173，完成：上傳 → 縮圖確認 → 辨識（顯示進度）→ 自動跳步驟2 → 原圖對照＋編輯 → 下載同名 .txt。
- 既有 Streamlit（8502/8503）不受影響、仍可執行。
