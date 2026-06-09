import sys
import tempfile
from pathlib import Path

import fitz

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ocr_lib  # noqa: E402


def _blank_pdf(n_pages: int) -> Path:
    """產生 n 頁空白（無文字層）PDF，供掃描路線測試。"""
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=300, height=400)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    import os
    os.close(fd)
    doc.save(path)
    doc.close()
    return Path(path)


def test_iter_hidpi_yields_page_no_and_filters():
    pdf = _blank_pdf(5)
    try:
        got = [(no, im.size) for no, im in ocr_lib.iter_hidpi(pdf, 72, pages={2, 4})]
        assert [no for no, _ in got] == [2, 4]
        assert all(w > 0 and h > 0 for _, (w, h) in got)
    finally:
        pdf.unlink()


def test_iter_hidpi_none_yields_all_with_page_no():
    pdf = _blank_pdf(3)
    try:
        nos = [no for no, _ in ocr_lib.iter_hidpi(pdf, 72)]
        assert nos == [1, 2, 3]
    finally:
        pdf.unlink()


import ocr_recognize  # noqa: E402


def _born_pdf(n_pages: int) -> Path:
    """產生 n 頁、每頁含足量文字層的 PDF（has_text_layer 為真）。"""
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 60),
                         f"page {i + 1} 資產負債表 合計 1234567 現金 8900",
                         fontsize=11)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    import os
    os.close(fd)
    doc.save(path)
    doc.close()
    return Path(path)


def test_remap_to_original_maps_positional_to_selected():
    out = ocr_recognize._remap_to_original({1: "a", 2: "b", 3: "c"}, [3, 5, 8])
    assert out == {3: "a", 5: "b", 8: "c"}


def test_recognize_born_digital_filters_selected_pages():
    pdf = _born_pdf(4)
    try:
        res = ocr_recognize.recognize(pdf, pages=[2, 4])
        assert res["mode"] == "文字層擷取"
        assert sorted(res["pages"].keys()) == [2, 4]
    finally:
        pdf.unlink()


def test_recognize_scanned_remaps_to_original_pages(monkeypatch):
    pdf = _blank_pdf(8)

    def fake_ocr_file(path):
        # 模擬 OCR 依「送進去 PDF 內第幾頁」回位置編號（送了 3 頁 → 1/2/3）
        return {"full_text": "--- 第 1 頁 ---\nA\n--- 第 2 頁 ---\nB\n--- 第 3 頁 ---\nC"}

    monkeypatch.setattr(ocr_lib, "ocr_file", fake_ocr_file)
    monkeypatch.setattr(
        ocr_recognize.llm_correct, "correct_via_deepseek",
        lambda text, key, model, timeout: text)  # 校正回傳原文

    try:
        res = ocr_recognize.recognize(
            pdf, corrector="deepseek", deepseek_key="x", pages=[3, 5, 8])
        assert sorted(res["pages"].keys()) == [3, 5, 8]
        assert res["pages"][3].strip() == "A"
        assert res["pages"][8].strip() == "C"
    finally:
        pdf.unlink()


import time as _time

from app.jobs import JobStore  # noqa: E402

BORN_FIXTURE = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"


def test_start_recognition_passes_pages_to_engine():
    store = JobStore()
    job = store.create("file3.pdf", Path(BORN_FIXTURE).read_bytes())
    started = store.start_recognition(job.job_id, pages=[1])
    assert started.selected == [1]
    for _ in range(60):
        if store.get(job.job_id).status in ("done", "error"):
            break
        _time.sleep(0.2)
    cur = store.get(job.job_id)
    assert cur.status == "done"
    assert sorted(cur.pages.keys()) == ["1"]
