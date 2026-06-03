"""Unified document recognition engine (used by the end-user web app).

Routing:
  • born-digital PDF (has embedded text layer) → extract text layer (digit-perfect)
  • scanned image / screenshot / image file → PaddleOCR  +  LLM correction
        (Claude CLI by default; DeepSeek optional)

Returns {"mode", "pages": {page_no: text}, "corrector"}.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import ocr_lib
import llm_correct
import ocr_postprocess


def red_to_black(im: Image.Image) -> Image.Image:
    """Turn red pixels (stamps / red negative figures) black, then grayscale —
    recovers text the OCR would otherwise drop or be confused by."""
    arr = np.array(im.convert("RGB"))
    R = arr[..., 0].astype(int); G = arr[..., 1].astype(int); B = arr[..., 2].astype(int)
    mask = ((R - G) > 20) & ((R - B) > 20) & (R > 80)
    out = arr.copy(); out[mask] = [0, 0, 0]
    return Image.fromarray(out).convert("L")


def _split_pages(corrected: str) -> dict[int, str]:
    parts = re.split(r"---\s*第\s*(\d+)\s*頁\s*---\s*\n?", corrected)
    pages: dict[int, str] = {}
    i = 1
    while i + 1 < len(parts):
        try:
            pages[int(parts[i])] = parts[i + 1].strip()
        except (ValueError, TypeError):
            pass
        i += 2
    if not pages:
        pages[1] = corrected.strip()
    return pages


def recognize(path, corrector: str = "claude", deepseek_key: str = "",
              dpi: int = 700, progress=None) -> dict:
    """Recognize a PDF / image file. `corrector` ∈ {"claude","deepseek"}.

    `progress(msg)` — optional callback for UI status updates.
    """
    path = Path(path)

    def log(msg):
        if progress:
            progress(msg)

    # ---- Route 1: born-digital PDF → text layer (no OCR needed) -------------
    if ocr_lib.has_text_layer(path):
        log("偵測到內嵌文字層（born-digital），直接擷取並重建表格…")
        pages = ocr_lib.extract_text_layer(path)
        return {"mode": "文字層擷取", "pages": pages, "corrector": "（文字層，未經 LLM）"}

    # ---- Route 2: image / scanned → PaddleOCR + LLM correction --------------
    log(f"渲染影像（{dpi} DPI）並去除紅色印章/紅字…")
    images = [red_to_black(im) for im in ocr_lib.render_hidpi(path, dpi)]
    fd, tmp = tempfile.mkstemp(prefix="ocrapp_", suffix=".pdf")
    os.close(fd)
    try:
        ocr_lib.pack_to_pdf(images, Path(tmp), resolution=dpi)
        log("PaddleOCR 辨識中…")
        full_text = ocr_lib.ocr_file(Path(tmp)).get("full_text") or ""
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass

    if corrector == "deepseek":
        log("DeepSeek 校正中…")
        corrected = llm_correct.correct_via_deepseek(full_text, deepseek_key,
                                                     "deepseek-chat", 300)
        cname = "DeepSeek (deepseek-chat)"
        mode = "PaddleOCR + DeepSeek"
    else:
        log("Claude 校正中（可能需數十秒）…")
        corrected = llm_correct.correct_via_claude_cli(full_text, timeout=300)
        cname = "Claude CLI"
        mode = "PaddleOCR + Claude"

    pages = _split_pages(corrected)
    pages = ocr_postprocess.post_process(pages)
    return {"mode": mode, "pages": pages, "corrector": cname}
