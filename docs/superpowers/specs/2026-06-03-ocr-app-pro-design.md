# 進階版辨識網頁（ocr_app_pro）設計規格

日期：2026-06-03
狀態：設計定稿，待寫實作計畫

## 1. 目的與定位

把舊的「OCR 調參工作台」（`E:\PJ_OCR\ocr_gui.py`，port 8501）重建為**進階版使用者網頁**。

- 對象：進階使用者（非開發者），需要比精靈簡單版（`ocr_app.py`）多一點能力，但不需要開發/調參級的細部參數。
- 與簡單版差異：多了「**原圖預覽＋逐頁對照**」與「**結果線上編輯再下載**」。
- 辨識方式固定為 **PaddleOCR ＋ DeepSeek 校正**（born-digital 自動走文字層）；不提供引擎選擇、不含 Claude / Claude Vision。

## 2. 重建方法（做法 A）

- **全新重寫**成獨立檔，不在舊 `ocr_gui.py` 上修改。
- 共用既有辨識引擎 `ocr_recognize.recognize()`，與簡單版 `ocr_app.py` 同核心，避免邏輯漂移。
- 舊 `ocr_gui.py` 退役（檔案保留、不再啟動）。

### 檔案與部署
- 新檔：`E:\OCR-Work-platform\ocr_app_pro.py`
- 連接埠：**8503**（簡單版 8502、舊工作台 8501 並存互不影響）
- 啟動：`streamlit run ocr_app_pro.py --server.port 8503`
- 相依模組沿用平台內既有檔：`ocr_recognize.py`、`ocr_lib.py`、`llm_correct.py`、`ocr_postprocess.py`

## 3. 流程與版面（三步驟分頁精靈）

沿用簡單版的三步驟分頁（含頂部 ①②③ 進度指示器），但步驟③改為對照編輯。

### 步驟 ① 上傳檔案
- 拖曳/點選上傳 PDF 或圖片（pdf/jpg/jpeg/png/webp）。
- 上傳後存到暫存資料夾，偵測：頁數、是否 born-digital（`ocr_lib.text_layer_char_count >= 50`）。
- 顯示偵測結果，引導前往步驟②。

### 步驟 ② 進行辨識
- 顯示待辨識檔名與頁數。
- 「🚀 開始辨識」按鈕；以進度條回報各階段（渲染 → PaddleOCR → DeepSeek 校正／或文字層擷取）。
- 呼叫 `ocr_recognize.recognize(path, corrector="deepseek", deepseek_key=<resolved>)`。
- 成功後存結果到 session、前往步驟③。

### 步驟 ③ 對照編輯
- **頁面切換**：多頁時於上方提供頁碼下拉選單（`st.selectbox`，存於 `cur_page`），左右兩欄同步顯示同一頁；單頁時不顯示選單。
- **左欄＝原圖**：以 `ocr_lib.render_hidpi(path, 預覽DPI≈150)` 取得該頁影像，使用可縮放元件（沿用 `ocr_gui.py` 的 `zoomable_image` JS 元件，複製進新檔）。
- **右欄＝可編輯結果**：`st.text_area` 顯示該頁辨識文字，使用者可直接修改；編輯內容存入 `session_state["edited"][page_no]`。
- **下載**：「⬇ 下載辨識結果（.txt）」匯出**編輯後**的全文，檔名與原檔同名（`<stem>.txt`）；多頁以 `===== 第 N 頁 =====` 分隔，單頁則純內容。
- **🔄 辨識新檔案**：清空 session、回到步驟①。

## 4. 辨識引擎與設定（固定）

- 掃描影像 / 截圖 / 圖片 → PaddleOCR（固定 **700 DPI ＋ 紅轉黑灰階**）＋ DeepSeek（`deepseek-chat`）校正 ＋ `ocr_postprocess.post_process`。
- born-digital PDF → `ocr_lib.extract_text_layer`（文字層、表格列重建），不跑 OCR/LLM。
- 以上分流邏輯完全由 `ocr_recognize.recognize()` 處理，網頁不重複實作。
- **DeepSeek 金鑰解析順序**：`os.environ["DEEPSEEK_API_KEY"]` → 程式內建 fallback 金鑰（沿用專案測試腳本中可用的那把）。使用者**預設不必輸入**；「進階設定」折疊區提供覆寫欄位。

## 5. 移除的功能（相對舊調參工作台）

- 前處理參數滑桿：去印章、灰階、雙邊去噪、CLAHE、Unsharp、Otsu、裁切文字區塊
- 切分 OCR（高密度小字模式）
- baseline 並排比較
- Claude 校正、Claude Vision OCR、辨識引擎選擇
- DPI 細部滑桿、內建資料夾瀏覽、下載前處理 PDF/JPG、重新預覽

## 6. 錯誤處理

- 辨識例外：以 `st.error` 顯示明確訊息（型別＋訊息），不讓整頁崩潰。
- DeepSeek 連線／金鑰錯誤：提示檢查金鑰或網路。
- 上傳非支援格式：由 `st.file_uploader` 的 `type` 參數擋下。
- 未完成前一步驟就跳到後續分頁：顯示提示，引導回上一步。

## 7. 元件與資料流

- **Session state**：`step`、`file_path`、`file_name`、`is_born_digital`、`n_pages`、`result`(pages dict)、`edited`(dict)、`preview_dpi`、`cur_page`。
- **重用**：`ocr_recognize.recognize`（辨識）、`ocr_lib.render_hidpi`（原圖預覽）、`ocr_lib.text_layer_char_count`（偵測）、`zoomable_image`（縮放，複製自 `ocr_gui.py`）。
- 原圖預覽影像在步驟③首次顯示時才渲染並快取於 session（避免重複渲染）。
- 下載內容一律取自 `edited`（若某頁未編輯，預設等於原辨識結果）。

## 8. 非目標（Out of scope）

- 不做批次多檔上傳。
- 不做 PDF/Excel 匯出（僅 .txt）。
- 不做使用者帳號/權限。
- 不在此頁提供 Claude 相關辨識（已固定 DeepSeek）。
- 不保留任何開發/調參參數介面。

## 9. 成功標準與驗收

- 以 Streamlit `AppTest` 無頭載入無例外，三分頁存在。
- born-digital 檔（檔案 3）：步驟③右欄顯示文字層結果、可編輯，下載檔名與原檔同名且含編輯內容。
- 影像檔（檔案 4 或 1）：左欄顯示原圖（可縮放、可切頁），右欄顯示 PaddleOCR＋DeepSeek 結果並可編輯。
- 在右欄修改文字後，下載的 .txt 反映修改後內容。
- 啟動於 8503，與 8502／8501 並存不衝突。
