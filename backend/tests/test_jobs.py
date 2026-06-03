import time
from pathlib import Path
from app.jobs import JobStore

BORN = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"


def _data():
    return Path(BORN).read_bytes()


def test_create_job_detects_and_renders():
    store = JobStore()
    job = store.create("file3.pdf", _data())
    assert job.status == "created"
    assert job.n_pages == 1
    assert job.is_born_digital is True
    assert store.preview_path(job.job_id, 1).is_file()


def test_get_and_unknown():
    store = JobStore()
    job = store.create("file3.pdf", _data())
    assert store.get(job.job_id).job_id == job.job_id
    assert store.get("nope") is None


def test_delete_removes_job_and_files():
    store = JobStore()
    job = store.create("file3.pdf", _data())
    work = Path(job.file_path).parent
    assert store.delete(job.job_id) is True
    assert store.get(job.job_id) is None
    assert not work.exists()
    assert store.delete("nope") is False


def test_recognition_runs_in_background_to_done():
    store = JobStore()
    job = store.create("file3.pdf", _data())
    started = store.start_recognition(job.job_id)
    assert started.status in ("running", "done")
    for _ in range(60):
        cur = store.get(job.job_id)
        if cur.status in ("done", "error"):
            break
        time.sleep(0.2)
    assert cur.status == "done"
    assert cur.mode == "文字層擷取"
    assert cur.pages["1"].strip()
    assert store.start_recognition("nope") is None
