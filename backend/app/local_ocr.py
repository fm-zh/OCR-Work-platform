"""本地 PaddleOCR 辨識（取代遠端無座標 OCR）：渲染 → worker 取座標 → 幾何重建表格。

後端（base 3.13）無法 import paddle，故以子程序呼叫 `paddle_worker.py`
（在 `paddleocr` conda 環境 / 3.11 執行）。worker 回傳每頁文字框座標，
本模組再用 table_reconstruct 拼回表格 {columns, rows}，並攤平成文字。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ocr_lib  # noqa: E402
from . import table_reconstruct  # noqa: E402

# PaddleOCR worker（在 paddleocr 環境執行）。可用環境變數覆寫 python 路徑。
PADDLE_PYTHON = os.environ.get(
    "PADDLE_OCR_PYTHON", "/home/zhaoi/miniconda3/envs/paddleocr/bin/python")
WORKER = str(Path(__file__).resolve().parents[1] / "paddle_worker.py")
OCR_DPI = 300  # PaddleOCR 用：300 DPI 足夠（含方向偵測），比 700 快很多


def _run_worker(image_paths: list[str], timeout: int) -> dict:
    """呼叫 worker，回傳 {path: [boxes]}。失敗則拋出 RuntimeError。"""
    proc = subprocess.run(
        [PADDLE_PYTHON, WORKER, *image_paths],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()[:500]
        raise RuntimeError(f"paddle worker 退出碼 {proc.returncode}：{msg}")
    try:
        return json.loads(proc.stdout)["results"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(f"paddle worker 輸出解析失敗：{exc}；stderr={proc.stderr[:300]}")


def recognize_scanned(pdf_path, progress=None, pages=None) -> dict:
    """掃描檔走本地 PaddleOCR。回傳 {mode, pages:{int:text}, tables:{int:{columns,rows}}}。

    pages 給定時只處理選到的原始頁碼。
    """
    def log(msg):
        if progress:
            progress(msg)

    workdir = Path(tempfile.mkdtemp(prefix="paddleocr_"))
    try:
        # 1. 逐頁渲染成 PNG（套用 /Rotate；側躺寬表由 worker 的方向偵測再轉正）
        log(f"渲染影像（{OCR_DPI} DPI）…")
        path_to_page: dict[str, int] = {}
        for i, im in ocr_lib.iter_hidpi(Path(pdf_path), OCR_DPI, pages=pages):
            pp = workdir / f"page_{i:04d}.png"
            im.convert("RGB").save(pp, "PNG")
            im.close()
            path_to_page[str(pp)] = i

        order = [p for p, _ in sorted(path_to_page.items(), key=lambda kv: kv[1])]
        if not order:
            return {"mode": "本地 PaddleOCR", "pages": {}, "tables": {}}

        # 2. 一次把所有選頁交給 worker（攤平模型初始化成本）
        log(f"PaddleOCR 辨識中…（{len(order)} 頁，含自動轉正）")
        timeout = 90 + 90 * len(order)
        results = _run_worker(order, timeout=timeout)

        # 3. 幾何重建
        pages_text: dict[int, str] = {}
        tables: dict[int, dict] = {}
        for p in order:
            n = path_to_page[p]
            boxes = results.get(p, [])
            grid = table_reconstruct.reconstruct(boxes)
            tables[n] = grid
            pages_text[n] = table_reconstruct.grid_to_text(grid)
            log(f"重建第 {n} 頁表格…")
        return {"mode": "本地 PaddleOCR", "pages": pages_text, "tables": tables}
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
