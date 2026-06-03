"""進階版網頁的純函式（不 import streamlit，可單元測試）。"""
from __future__ import annotations

import os
from pathlib import Path

# 與專案測試腳本一致的可用金鑰，作為最後 fallback
BUILTIN_DEEPSEEK_KEY = "sk-dfc52c43969c4457a83928fd3f42a8cb"


def load_env_file(path) -> dict:
    """讀取 .env（每行 KEY=VALUE，# 開頭為註解）填入 os.environ。

    已存在的環境變數不覆寫（真實環境變數優先於檔案）。回傳本次實際載入的
    {key: value}。檔案不存在時回傳空 dict。
    """
    loaded: dict = {}
    p = Path(path)
    if not p.is_file():
        return loaded
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
            loaded[key] = val
    return loaded


def resolve_deepseek_key(override: str = "") -> str:
    """解析 DeepSeek 金鑰：覆寫 → 環境變數 DEEPSEEK_API_KEY → 內建 fallback。"""
    if override and override.strip():
        return override.strip()
    env = os.environ.get("DEEPSEEK_API_KEY", "")
    if env and env.strip():
        return env.strip()
    return BUILTIN_DEEPSEEK_KEY


def combine_pages(pages: dict) -> str:
    """{page_no: text} → 下載用全文。單頁回純文字；多頁加 '===== 第 N 頁 ====='。"""
    keys = sorted(pages)
    if not keys:
        return ""
    if len(keys) == 1:
        return pages[keys[0]]
    return "\n\n".join(f"===== 第 {k} 頁 =====\n{pages[k]}" for k in keys)


def current_page_text(result_pages: dict, edited: dict, pno: int) -> str:
    """回傳某頁目前文字：有編輯過用編輯版，否則用原辨識結果。"""
    if pno in edited:
        return edited[pno]
    return result_pages.get(pno, "")


def detect_file(path) -> dict:
    """偵測上傳檔：是否含文字層（born-digital）、頁數、文字層字元數。"""
    import sys
    if r"E:\OCR-Work-platform" not in sys.path:
        sys.path.insert(0, r"E:\OCR-Work-platform")
    import ocr_lib
    import fitz
    chars = ocr_lib.text_layer_char_count(path)
    with fitz.open(path) as doc:
        n_pages = doc.page_count
    return {"is_born_digital": chars >= 50, "n_pages": n_pages, "text_chars": chars}
