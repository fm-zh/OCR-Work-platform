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

## 檔案結構

| 檔案 | 說明 |
|---|---|
| `ocr_app.py` | 網頁（Streamlit 三步驟分頁精靈） |
| `ocr_recognize.py` | 辨識引擎：`recognize(path, corrector='claude'|'deepseek')` 自動分流 |
| `ocr_lib.py` | 核心：PaddleOCR API client、PDF 渲染、文字層擷取、前處理 |
| `llm_correct.py` | Claude CLI／DeepSeek 校正 |
| `ocr_postprocess.py` | 財報後處理（標題回補、簽署列、待彌補虧損、金額欄頭等） |
