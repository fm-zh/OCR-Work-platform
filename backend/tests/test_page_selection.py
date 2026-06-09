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
