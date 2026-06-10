"""薄包裝：重用平台根目錄的既有辨識引擎。"""
from __future__ import annotations

import sys
from pathlib import Path

# 把平台根目錄（含 ocr_lib / ocr_recognize / ocr_app_pro_helpers）加入 sys.path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ocr_lib  # noqa: E402
import ocr_recognize  # noqa: E402
from ocr_app_pro_helpers import (  # noqa: E402
    detect_file, resolve_deepseek_key, load_env_file,
)

PREVIEW_DPI = 150


def detect(path) -> dict:
    """{is_born_digital, n_pages, text_chars}。"""
    return detect_file(str(path))


def render_previews(path, out_dir) -> int:
    """渲染各頁為 PNG 到 out_dir（檔名 page_{n}.png，n 從 1），回傳頁數。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    imgs = ocr_lib.render_hidpi(Path(path), PREVIEW_DPI)
    for i, im in enumerate(imgs, start=1):
        im.convert("RGB").save(out_dir / f"page_{i}.png")
    return len(imgs)


def recognize(path, progress=None, pages=None) -> dict:
    """固定 PaddleOCR+DeepSeek（born-digital 自動文字層）。回傳 {mode, pages:{int:str}}。
    pages 給定時只辨識選到的頁（原始頁碼）。"""
    res = ocr_recognize.recognize(
        str(path), corrector="deepseek",
        deepseek_key=resolve_deepseek_key(), progress=progress, pages=pages)
    return {"mode": res["mode"], "pages": res["pages"]}
