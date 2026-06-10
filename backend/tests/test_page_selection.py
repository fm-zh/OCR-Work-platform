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
    """產生 n 頁、每頁含足量文字層的 PDF。

    每頁字數須超過 has_text_layer 的門檻（50 非空白字）才會被判為 born-digital；
    has_text_layer 是加總全部頁，但本 helper 也用於單頁（_born_bytes），故每頁
    都放多行、確保「單頁」也過門檻，避免單頁被誤判為掃描檔而走真實 OCR。"""
    lines = [
        "資產負債表 流動資產 現金及約當現金 1,234,567",
        "應收帳款淨額 890,000 存貨 456,000 預付款項 78,900",
        "非流動資產 不動產廠房及設備 5,600,000 合計 8,259,467",
        "流動負債 應付帳款 320,000 待彌補虧損 (588,000)",
    ]
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((40, 50), f"第 {i + 1} 頁", fontsize=11)
        for j, ln in enumerate(lines):
            page.insert_text((40, 80 + j * 22), ln, fontsize=10)
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


def test_recognize_scanned_multibatch_remaps_to_original_pages(monkeypatch):
    pdf = _blank_pdf(8)

    # 強制每頁各自成批：把單檔上限調到極小
    monkeypatch.setattr(ocr_lib, "MAX_UPLOAD_BYTES", 1)

    calls = {"n": 0}
    texts = ["A", "B", "C"]

    def fake_ocr_file(path):
        # 每批一頁；OCR 依「批內位置」回第 1 頁
        i = calls["n"]
        calls["n"] += 1
        return {"full_text": f"--- 第 1 頁 ---\n{texts[i]}"}

    monkeypatch.setattr(ocr_lib, "ocr_file", fake_ocr_file)
    monkeypatch.setattr(
        ocr_recognize.llm_correct, "correct_via_deepseek",
        lambda text, key, model, timeout: text)

    try:
        res = ocr_recognize.recognize(
            pdf, corrector="deepseek", deepseek_key="x", pages=[3, 5, 8])
        assert calls["n"] == 3                      # 確實跑了 3 批
        assert sorted(res["pages"].keys()) == [3, 5, 8]
        assert res["pages"][3].strip() == "A"
        assert res["pages"][5].strip() == "B"
        assert res["pages"][8].strip() == "C"
    finally:
        pdf.unlink()


import time as _time

from app.jobs import JobStore  # noqa: E402


def _born_bytes() -> bytes:
    """產生一份 1 頁 born-digital PDF 的位元組（取代硬編碼的本機 fixture，
    讓測試在任何機器／CI 都能跑）。"""
    pdf = _born_pdf(1)
    try:
        return pdf.read_bytes()
    finally:
        pdf.unlink()


def test_start_recognition_passes_pages_to_engine():
    store = JobStore()
    job = store.create("file3.pdf", _born_bytes())
    started = store.start_recognition(job.job_id, pages=[1])
    assert started.selected == [1]
    for _ in range(60):
        if store.get(job.job_id).status in ("done", "error"):
            break
        _time.sleep(0.2)
    cur = store.get(job.job_id)
    assert cur.status == "done"
    assert sorted(cur.pages.keys()) == ["1"]


from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

_client = TestClient(app)


def _upload_born():
    return _client.post(
        "/api/jobs",
        files={"file": ("file3.pdf", _born_bytes(), "application/pdf")},
    ).json()["job_id"]


def test_recognize_rejects_empty_pages():
    jid = _upload_born()
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": []})
    assert r.status_code == 400


def test_recognize_rejects_out_of_range_pages():
    jid = _upload_born()  # 此檔 1 頁
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": [2]})
    assert r.status_code == 400


def test_recognize_accepts_valid_pages():
    jid = _upload_born()
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": [1]})
    assert r.status_code == 200
    assert r.json()["status"] in ("running", "done")
