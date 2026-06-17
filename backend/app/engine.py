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

from . import local_ocr  # noqa: E402

PREVIEW_DPI = 150


def detect(path) -> dict:
    """{is_born_digital, n_pages, text_chars}。"""
    return detect_file(str(path))


def render_previews(path, out_dir) -> int:
    """渲染各頁為 PNG 到 out_dir（檔名 page_{n}.png，n 從 1），回傳頁數。

    逐頁串流（iter_hidpi）：一次只在記憶體保留一頁，避免大檔／多頁一次載入
    全部頁面而 OOM；iter_hidpi 也會套用 /Rotate 旋轉與單頁像素上限。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, im in ocr_lib.iter_hidpi(Path(path), PREVIEW_DPI):
        im.convert("RGB").save(out_dir / f"page_{i}.png")
        im.close()
        n += 1
    return n


def recognize(path, progress=None, pages=None) -> dict:
    """辨識路由：
      • born-digital（內嵌文字層）→ 直接擷取文字層（位數精準），結構化走 DeepSeek。
      • 掃描檔 → 本地 PaddleOCR（含自動轉正）+ 幾何重建表格，直接得到正確分欄。
    回傳 {mode, pages:{int:str}}；掃描檔另含 tables:{int:{columns,rows}}（幾何重建），
    供結構化階段直接採用、不必再呼叫 DeepSeek。pages 給定時只辨識選到的原始頁碼。
    """
    if ocr_lib.has_text_layer(Path(path)):
        res = ocr_recognize.recognize(
            str(path), corrector="deepseek",
            deepseek_key=resolve_deepseek_key(), progress=progress, pages=pages)
        return {"mode": res["mode"], "pages": res["pages"]}
    res = local_ocr.recognize_scanned(path, progress=progress, pages=pages)
    return {"mode": res["mode"], "pages": res["pages"], "tables": res["tables"]}
