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
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import ocr_lib
import llm_correct
import ocr_postprocess


def red_to_black(im: Image.Image) -> Image.Image:
    """Turn red pixels (stamps / red negative figures) black, then grayscale —
    recovers text the OCR would otherwise drop or be confused by.

    使用 int16（而非 int64）計算色差，結果與原本完全相同，但記憶體用量約少 4 倍；
    直接輸出灰階（L），避免多保留一份 RGB 副本。"""
    rgb = im.convert("RGB")
    arr = np.asarray(rgb)
    R = arr[..., 0].astype(np.int16)
    G = arr[..., 1].astype(np.int16)
    B = arr[..., 2].astype(np.int16)
    mask = ((R - G) > 20) & ((R - B) > 20) & (R > 80)
    gray = np.asarray(rgb.convert("L")).copy()
    gray[mask] = 0
    return Image.fromarray(gray, "L")


def _ordered_pages(full_text: str, expected: int) -> list[str]:
    """把單批 OCR 的 full_text 依「--- 第 N 頁 ---」拆成有序的頁面文字清單。
    用於多批辨識時把各批結果接回全域頁序。"""
    d = _split_pages(full_text)
    if d:
        return [d.get(k, "") for k in sorted(d)]
    return [full_text.strip()]


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


def _remap_to_original(pages_dict: dict, selected) -> dict:
    """把位置編號（1..M）的結果 dict 換回原始頁碼。

    `selected` 為使用者選的原始頁碼；排序後第 k 個位置 → 第 k 個原始頁碼。
    例：selected=[3,5,8]、pages_dict={1:..,2:..,3:..} → {3:..,5:..,8:..}。
    """
    order = sorted(selected)
    out: dict = {}
    for k, v in sorted(pages_dict.items()):
        if 1 <= k <= len(order):
            out[order[k - 1]] = v
    return out


def recognize(path, corrector: str = "claude", deepseek_key: str = "",
              dpi: int = 700, progress=None, pages=None) -> dict:
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
        out_pages = ocr_lib.extract_text_layer(path)
        if pages is not None:
            want = set(pages)
            out_pages = {k: v for k, v in out_pages.items() if k in want}
        return {"mode": "文字層擷取", "pages": out_pages, "corrector": "（文字層，未經 LLM）"}

    # ---- Route 2: image / scanned → PaddleOCR + LLM correction --------------
    # 逐頁串流：render 一頁 → 去紅字 → 存暫存 JPEG → 釋放，記憶體只跟單頁有關，
    # 避免高 DPI 多頁文件一次載入全部頁面而 OOM。
    log(f"渲染影像（{dpi} DPI）並去除紅色印章/紅字…")
    workdir = Path(tempfile.mkdtemp(prefix="ocrpages_"))
    try:
        # 逐頁 render→去紅字→存暫存 JPEG（單一壓縮、維持 DPI 與畫質）
        page_files = []  # (path, size_bytes)
        for i, im in ocr_lib.iter_hidpi(path, dpi, pages=pages):
            g = red_to_black(im)
            im.close()
            pp = workdir / f"p{i:04d}.jpg"
            g.convert("L").save(pp, "JPEG", quality=88)
            g.close()
            page_files.append((pp, pp.stat().st_size))
            log(f"前處理第 {i} 頁…")

        # 依 OCR API 單檔上限把頁面切成多批（維持 700 DPI，不犧牲畫質）
        limit = ocr_lib.MAX_UPLOAD_BYTES - 1024 * 1024
        batches, cur, cur_sz = [], [], 0
        for pp, sz in page_files:
            if cur and cur_sz + sz > limit:
                batches.append(cur); cur, cur_sz = [], 0
            cur.append(pp); cur_sz += sz
        if cur:
            batches.append(cur)

        def _ocr_batch(paths) -> str:
            fd, tmp = tempfile.mkstemp(prefix="ocrapp_", suffix=".pdf")
            os.close(fd)
            try:
                ocr_lib.pack_paths_to_pdf(paths, Path(tmp), dpi=dpi)
                return ocr_lib.ocr_file(Path(tmp)).get("full_text") or ""
            finally:
                try:
                    Path(tmp).unlink()
                except OSError:
                    pass

        if len(batches) <= 1:
            log("PaddleOCR 辨識中…")
            full_text = _ocr_batch([p for p, _ in page_files])
        else:
            pages_text = []
            for bi, batch in enumerate(batches, start=1):
                log(f"PaddleOCR 辨識中…（第 {bi}/{len(batches)} 批）")
                pages_text.extend(_ordered_pages(_ocr_batch(batch), len(batch)))
            full_text = "\n".join(
                f"--- 第 {i} 頁 ---\n{t}" for i, t in enumerate(pages_text, start=1))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

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

    out_pages = _split_pages(corrected)
    out_pages = ocr_postprocess.post_process(out_pages)
    if pages is not None:
        out_pages = _remap_to_original(out_pages, pages)
    return {"mode": mode, "pages": out_pages, "corrector": cname}
