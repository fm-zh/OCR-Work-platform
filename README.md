# 財報文件智慧辨識平台（OCR Work Platform）

財務報表／稅報文件的智慧辨識網頁。前後端分離：**FastAPI 後端 ＋ React/Vite 前端**。
三步驟精靈：**① 上傳檔案 → ② 辨識與對照編輯 → ③ 輸出 Excel**。

線上版：https://ocr-platform.zhgpt.org

## 辨識方法（自動分流）

| 檔案類型 | 處理方式 |
|---|---|
| 內含文字層的 PDF（born-digital） | 直接擷取文字層並重建表格列（數字 100% 精準、免 OCR）；表格結構化走 DeepSeek |
| 掃描影像／截圖（PDF 或圖片） | 本地 PaddleOCR（GPU，含自動轉正）→ 以文字框座標**幾何重建表格** → OpenCC 簡轉繁 → DeepSeek 只修「截斷／錯字的中文科目名稱」（數字與欄位不動） |

掃描檔的「幾何重建」利用每塊文字的 bbox 座標還原欄位，能正確處理**雙欄**（左資產／右負債）
以及被 90° 擺放的**橫式寬表**——欄位與數字為確定性流程，DeepSeek 僅用於補回被掃描裁切的中文科目名稱。

## 架構

- **後端**（`backend/`，FastAPI）：任務管理、頁面渲染、辨識路由、Excel 匯出。
- **本地 PaddleOCR worker**（`backend/paddle_worker.py`）：在獨立的 `paddleocr` conda 環境執行，
  回傳每頁文字框的座標。後端以子程序呼叫（隔離 Python 版本／相依，避免衝突）。
- **前端**（`frontend/`，React ＋ Vite）：三步驟 UI、原圖對照、表格線上編輯、Excel 下載。

## 安裝

### 後端
```
pip install -r backend/requirements-backend.txt
pip install -r requirements.txt          # ocr_lib 共用：pymupdf / opencv / numpy / pillow
```

### 本地 PaddleOCR（掃描檔辨識用，獨立 conda 環境）
```
conda create -n paddleocr python=3.11 -y
conda activate paddleocr
# GPU（建議，需 NVIDIA + CUDA）：
pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
# 或 CPU：pip install paddlepaddle
pip install paddleocr opencc
```
後端以環境變數 `PADDLE_OCR_PYTHON` 指定此環境的 python
（預設 `~/miniconda3/envs/paddleocr/bin/python`）。

### 前端
```
cd frontend && npm install
```

### DeepSeek 金鑰
表格結構化／科目名稱還原使用 DeepSeek。於專案根目錄 `.env`（或環境變數）設定：
```
DEEPSEEK_API_KEY=你的金鑰
```
系統啟動時自動讀取（`load_env_file`）；若作業系統已設同名環境變數則以其為準。

## 啟動（本地開發）

```
# 後端（:8000）
cd backend && python -m uvicorn app.main:app --port 8000
# 前端（:5173，dev 下 /api 由 Vite proxy 轉到後端）
cd frontend && npm run dev
```
Swagger 文件：http://localhost:8000/docs ；瀏覽器開 http://localhost:5173 。

## 檔案結構

| 路徑 | 說明 |
|---|---|
| `backend/app/main.py` | FastAPI 路由（上傳／辨識／狀態／Excel／結構化） |
| `backend/app/jobs.py` | 記憶體任務管理＋背景辨識／結構化 |
| `backend/app/engine.py` | 辨識路由：born-digital→文字層；掃描→本地 PaddleOCR |
| `backend/app/local_ocr.py` | 渲染→呼叫 worker→幾何重建→OpenCC 的編排 |
| `backend/app/table_reconstruct.py` | 由 bbox 座標幾何重建表格 `{columns, rows}` |
| `backend/app/excel.py` | DeepSeek 結構化／科目名稱還原＋openpyxl 產生 `.xlsx` |
| `backend/paddle_worker.py` | 本地 PaddleOCR（在 paddleocr 環境執行，回傳座標） |
| `ocr_lib.py` | PaddleOCR API client、PDF 渲染、文字層擷取、影像前處理 |
| `ocr_recognize.py` | 辨識引擎（born-digital 文字層擷取；CLI／舊流程共用） |
| `llm_correct.py` | Claude CLI／DeepSeek 文字校正 |
| `ocr_postprocess.py` | 財報後處理（標題回補、簽署列等） |
| `ocr_app_pro_helpers.py` | 共用輔助（檔案偵測、金鑰解析、`.env` 載入） |
| `frontend/` | React ＋ Vite 前端 |

## 部署

線上以 Cloudflare Tunnel ＋ systemd user services 部署
（後端 `:8010`、前端 `vite preview :4173`）；更新後需重啟對應服務、前端須先 `npm run build`。
