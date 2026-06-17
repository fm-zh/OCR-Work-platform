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

## 使用的模型

掃描檔辨識（`backend/paddle_worker.py`）以 PaddleOCR pipeline 執行。**雙模型擇優**：每頁同時用
PP-OCRv6_medium（預設）與 PP-OCRv5_server 各跑一次，再依文字框「信心分數」逐格擇優合併——
因為沒有單一模型對所有頁都最好（medium 對「有底線的總計列」較穩、server 對清晰小字較準）。

| 階段 | 模型 / 設定 | 說明 |
|---|---|---|
| 文字偵測＋辨識（模型 A）| `PP-OCRv6_medium`（預設 det＋rec）| 對總計列等情境較穩 |
| 文字偵測＋辨識（模型 B）| `PP-OCRv5_server_det` ＋ `PP-OCRv5_server_rec` | 對清晰小字（金額、科目名）辨識力較強 |
| 合併 | 逐格依信心擇優 | 兩模型逐一載入跑完釋放（控 GPU 記憶體），約 1.5× 時間 |
| 文件方向 | `PP-LCNet_x1_0_doc_ori` | `use_doc_orientation_classify=True`，側躺寬表自動轉正 |
| 文字行方向 | `PP-LCNet_x1_0_textline_ori` | `use_textline_orientation=True` |
| 偵測解析度 | `text_det_limit_side_len=2000` | 避免密集表被降採樣 |
| 語言 | `chinese_cht`（繁體中文）| |
| 其他 | `enable_mkldnn=False` | 否則 paddlepaddle 3.3 在 CPU 會 PIR oneDNN 崩潰 |

> 表格欄位由文字框 bbox 幾何重建：欄位錨點只採「含數字、信心≥0.7」的框（破折號與低信心雜訊不參與定欄，避免相鄰欄被誤併）。

LLM／後處理：

| 用途 | 模型 / 工具 |
|---|---|
| 簡轉繁 | OpenCC `s2tw`（規則轉換，非模型；不用 `s2twp` 以免誤改財報用詞）|
| 掃描檔科目名稱還原 | DeepSeek `deepseek-chat`（只修中文標籤，數字／欄位不動）|
| born-digital 表格結構化 | DeepSeek `deepseek-chat` |

> 註：模型權重首次執行時自動下載並快取於 `~/.paddlex/official_models`。
> 遠端 OCR API（`paddleocr-remote`）已不用於 web 掃描流程，僅 `ocr_recognize.py` 的 CLI 路徑保留。

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
