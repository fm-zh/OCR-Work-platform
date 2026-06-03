import time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
BORN = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"


def _upload():
    with open(BORN, "rb") as f:
        return client.post("/api/jobs",
                           files={"file": ("file3.pdf", f, "application/pdf")})


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_creates_job():
    r = _upload()
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "created"
    assert j["n_pages"] == 1
    assert j["is_born_digital"] is True
    assert j["job_id"]


def test_reject_unsupported_extension():
    r = client.post("/api/jobs",
                    files={"file": ("bad.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_page_image_returns_png():
    jid = _upload().json()["job_id"]
    r = client.get(f"/api/jobs/{jid}/pages/1/image")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_recognize_then_poll_done():
    jid = _upload().json()["job_id"]
    r = client.post(f"/api/jobs/{jid}/recognize")
    assert r.status_code == 200
    assert r.json()["status"] in ("running", "done")
    s = None
    for _ in range(60):
        s = client.get(f"/api/jobs/{jid}").json()
        if s["status"] in ("done", "error"):
            break
        time.sleep(0.3)
    assert s["status"] == "done"
    assert s["mode"] == "文字層擷取"
    assert s["pages"]["1"]


def test_unknown_job_404():
    assert client.get("/api/jobs/nope").status_code == 404


def test_delete_then_404():
    jid = _upload().json()["job_id"]
    assert client.delete(f"/api/jobs/{jid}").status_code == 204
    assert client.get(f"/api/jobs/{jid}").status_code == 404
