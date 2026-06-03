from pathlib import Path
from app import engine

BORN = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"


def test_detect_born_digital():
    info = engine.detect(BORN)
    assert info["is_born_digital"] is True
    assert info["n_pages"] == 1
    assert info["text_chars"] >= 50


def test_render_previews_creates_png(tmp_path):
    n = engine.render_previews(BORN, tmp_path)
    assert n == 1
    assert (tmp_path / "page_1.png").is_file()


def test_recognize_born_digital_returns_pages():
    res = engine.recognize(BORN)
    assert res["mode"] == "文字層擷取"
    assert 1 in res["pages"]
    assert res["pages"][1].strip()
