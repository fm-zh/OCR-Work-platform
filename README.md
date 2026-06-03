# 財報文件智慧辨識平台（OCR Work Platform）

PaddleOCR ＋ Claude 的財務報表／稅報文件辨識網頁。三步驟分頁精靈：
**① 上傳檔案 → ② 進行辨識 → ③ 輸出結果**。

## 辨識方法（自動分流）

| 檔案類型 | 處理方式 |
|---|---|
| 內含文字層的 PDF（born-digital） | 直接擷取文字層並重建表格列（數字 100% 精準，免 OCR/LLM） |
| 掃描影像／截圖（PDF 或圖片） | PaddleOCR（700 DPI＋去紅印章/紅字）＋ Claude 校正＋財報後處理 |

校正引擎可在介面選 **Claude**（最準、較慢）或 **DeepSeek**（快、需 API Key）。

## 安裝

```
pip install -r requirements.txt
```

另需：
- 私有 PaddleOCR API（已內建於 `ocr_lib.py`，submit→poll→result）。
- Claude 校正需安裝 Claude Code CLI：`npm install -g @anthropic-ai/claude-code`
  （若不使用 Claude，可在介面改選 DeepSeek）。

## 啟動

```
streamlit run ocr_app.py --server.port 8502
```
或直接執行 `run.bat`，瀏覽器開啟 http://localhost:8502 。

## 進階版（ocr_app_pro.py）

比簡單版多「原圖對照」與「結果線上編輯」；辨識固定走 PaddleOCR ＋ DeepSeek
（born-digital 自動文字層）。**兩步驟分頁，完成後自動跳轉下一步**：
① 選擇檔案 → 預覽確認 → 進行辨識；② 辨識結果與對照編輯（左原圖可縮放、右可編輯、同名 .txt 下載）。

**DeepSeek 金鑰以 `.env` 管理**（介面不再有輸入欄位）：在專案根目錄的 `.env` 設定
```
DEEPSEEK_API_KEY=你的金鑰
```
系統啟動時自動讀取（`load_env_file`）；若作業系統已設同名環境變數，則以環境變數為準。

啟動：`streamlit run ocr_app_pro.py --server.port 8503`，或執行 `run_pro.bat`，
瀏覽器開 http://localhost:8503 。

## 檔案結構

| 檔案 | 說明 |
|---|---|
| `ocr_app.py` | 網頁（Streamlit 三步驟分頁精靈） |
| `ocr_recognize.py` | 辨識引擎：`recognize(path, corrector='claude'|'deepseek')` 自動分流 |
| `ocr_lib.py` | 核心：PaddleOCR API client、PDF 渲染、文字層擷取、前處理 |
| `llm_correct.py` | Claude CLI／DeepSeek 校正 |
| `ocr_postprocess.py` | 財報後處理（標題回補、簽署列、待彌補虧損、金額欄頭等） |

## 前後端分離版（backend + frontend）

- 後端 API（FastAPI）：`cd backend && run_api.bat`（或 `python -m uvicorn app.main:app --port 8000`），Swagger 文件 http://localhost:8000/docs 。
- 前端 SPA（React+Vite）：先啟動後端，再 `cd frontend && run_frontend.bat`（或 `npm run dev`），開 http://localhost:5173 。dev 下 `/api` 由 Vite proxy 轉到 :8000。

流程：① 選檔→縮圖預覽確認→辨識（非同步、顯示進度、完成自動跳轉）→ ② 原圖對照＋線上編輯→下載同名 .txt。
