# Phase 1：後端 API（FastAPI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `E:\OCR-Work-platform\backend` 建一個 FastAPI 非同步辨識 API，重用既有 Python 引擎（born-digital→文字層；影像→PaddleOCR+DeepSeek），提供上傳、原圖預覽、背景辨識＋輪詢、刪除等端點與 Swagger 文件。

**Architecture:** 薄 API 層委派既有引擎。`engine.py` 包裝 `ocr_recognize`/`ocr_lib`/`ocr_app_pro_helpers`；`jobs.py` 用記憶體 `JobStore` 管理任務（每任務一個暫存資料夾，存上傳檔＋預渲染 PNG），背景以 ThreadPoolExecutor 跑辨識並更新進度；`main.py` 是 FastAPI 路由＋CORS。對應 spec：`docs/superpowers/specs/2026-06-03-frontend-backend-split-design.md`。

**Tech Stack:** Python 3.14、FastAPI、uvicorn、Pydantic、python-multipart、（測試）pytest＋FastAPI TestClient（httpx）。既有引擎相依：PyMuPDF/OpenCV/numpy/Pillow。

> **環境備註：**
> - 工作目錄 `E:\OCR-Work-platform`（git 倉庫）。後端在子資料夾 `backend\`。
> - 平台根目錄已有引擎模組：`ocr_lib.py`、`ocr_recognize.py`、`ocr_app_pro_helpers.py`、`.env`。
> - 測試離線可跑：全部用 born-digital 檔 `E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf`（走文字層、不呼叫 DeepSeek/PaddleOCR）。
> - 測試指令一律從 `E:\OCR-Work-platform\backend` 執行：`python -m pytest tests -q`。
> - `.env` 已被忽略；不要提交。`.gitignore` 需新增忽略 `backend/__pycache__` 等（已含 `__pycache__/`）。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `backend/requirements-backend.txt` | 後端＋測試套件清單 |
| `backend/conftest.py` | 讓 pytest 能 `from app import ...`（把 backend 加入 sys.path） |
| `backend/app/__init__.py` | 套件標記 |
| `backend/app/engine.py` | 薄包裝：`detect()`、`render_previews()`、`recognize()`，重用既有引擎 |
| `backend/app/schemas.py` | Pydantic 模型：`Progress`、`JobMeta`、`JobStatus` |
| `backend/app/jobs.py` | `Job` dataclass、`JobStore`（建立/查詢/刪除/預覽路徑/背景辨識） |
| `backend/app/main.py` | FastAPI app、路由、CORS、啟動讀 .env |
| `backend/tests/test_engine.py` | engine 單元測試 |
| `backend/tests/test_jobs.py` | JobStore 單元測試 |
| `backend/tests/test_api.py` | API 整合測試（TestClient） |
| `backend/run_api.bat` | 啟動 uvicorn :8000 |

---

## Task 1：腳手架、相依、engine 包裝

**Files:**
- Create: `backend/requirements-backend.txt`、`backend/conftest.py`、`backend/app/__init__.py`、`backend/app/engine.py`、`backend/tests/test_engine.py`

- [ ] **Step 1: 建立相依清單與腳手架檔**

`backend/requirements-backend.txt`：
```
fastapi
uvicorn[standard]
python-multipart
pydantic
pymupdf
opencv-python
numpy
pillow
httpx
pytest
```

`backend/conftest.py`：
```python
import sys
from pathlib import Path

# 讓 pytest 能 `from app import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

`backend/app/__init__.py`：（空檔）
```python
```

- [ ] **Step 2: 安裝相依**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pip install -r requirements-backend.txt`
Expected: 安裝成功（fastapi、uvicorn、httpx、pytest 等）。

- [ ] **Step 3: 寫 engine 失敗測試**

`backend/tests/test_engine.py`：
```python
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
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_engine.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.engine'`）

- [ ] **Step 5: 實作 `backend/app/engine.py`**

```python
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

PREVIEW_DPI = 150


def detect(path) -> dict:
    """{is_born_digital, n_pages, text_chars}。"""
    return detect_file(str(path))


def render_previews(path, out_dir) -> int:
    """渲染各頁為 PNG 到 out_dir（檔名 page_{n}.png，n 從 1），回傳頁數。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    imgs = ocr_lib.render_hidpi(Path(path), PREVIEW_DPI)
    for i, im in enumerate(imgs, start=1):
        im.convert("RGB").save(out_dir / f"page_{i}.png")
    return len(imgs)


def recognize(path, progress=None) -> dict:
    """固定 PaddleOCR+DeepSeek（born-digital 自動文字層）。回傳 {mode, pages:{int:str}}。"""
    res = ocr_recognize.recognize(
        str(path), corrector="deepseek",
        deepseek_key=resolve_deepseek_key(), progress=progress)
    return {"mode": res["mode"], "pages": res["pages"]}
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_engine.py -q`
Expected: PASS（3 passed）

- [ ] **Step 7: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/requirements-backend.txt backend/conftest.py backend/app/__init__.py backend/app/engine.py backend/tests/test_engine.py
git commit -m "feat(api): backend scaffolding + engine wrapper"
```

---

## Task 2：JobStore（記憶體任務管理＋背景辨識）

**Files:**
- Create: `backend/app/jobs.py`、`backend/tests/test_jobs.py`

- [ ] **Step 1: 寫 JobStore 失敗測試**

`backend/tests/test_jobs.py`：
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_jobs.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.jobs'`）

- [ ] **Step 3: 實作 `backend/app/jobs.py`**

```python
"""記憶體任務管理 + 背景辨識。"""
from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import engine


@dataclass
class Job:
    job_id: str
    file_name: str
    file_path: str
    preview_dir: str
    n_pages: int
    is_born_digital: bool
    status: str = "created"          # created | running | done | error
    progress: Optional[dict] = None  # {message, percent}
    mode: Optional[str] = None
    pages: Optional[dict] = None      # {str(page_no): text}
    error: Optional[str] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4)

    def create(self, file_name: str, data: bytes) -> Job:
        job_id = uuid.uuid4().hex
        work = Path(tempfile.mkdtemp(prefix=f"ocrjob_{job_id}_"))
        fpath = work / file_name
        fpath.write_bytes(data)
        det = engine.detect(fpath)
        preview_dir = work / "preview"
        engine.render_previews(fpath, preview_dir)
        job = Job(job_id=job_id, file_name=file_name, file_path=str(fpath),
                  preview_dir=str(preview_dir), n_pages=det["n_pages"],
                  is_born_digital=det["is_born_digital"])
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        shutil.rmtree(Path(job.file_path).parent, ignore_errors=True)
        return True

    def preview_path(self, job_id: str, page_no: int) -> Optional[Path]:
        job = self.get(job_id)
        if job is None:
            return None
        p = Path(job.preview_dir) / f"page_{page_no}.png"
        return p if p.is_file() else None

    def start_recognition(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in ("running", "done"):
            return job
        job.status = "running"
        job.progress = {"message": "準備中…", "percent": 0}
        self._pool.submit(self._run, job_id)
        return job

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        counter = {"n": 0}

        def _progress(msg: str) -> None:
            counter["n"] += 1
            job.progress = {"message": msg, "percent": min(90, counter["n"] * 22)}

        try:
            res = engine.recognize(job.file_path, progress=_progress)
            job.mode = res["mode"]
            job.pages = {str(k): v for k, v in res["pages"].items()}
            job.progress = {"message": "完成", "percent": 100}
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "error"
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_jobs.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/jobs.py backend/tests/test_jobs.py
git commit -m "feat(api): in-memory JobStore + background recognition"
```

---

## Task 3：FastAPI 路由（schemas + main）＋ API 測試

**Files:**
- Create: `backend/app/schemas.py`、`backend/app/main.py`、`backend/tests/test_api.py`

- [ ] **Step 1: 寫 API 失敗測試**

`backend/tests/test_api.py`：
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_api.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.main'`）

- [ ] **Step 3: 實作 `backend/app/schemas.py`**

```python
"""API 回應模型。"""
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel


class Progress(BaseModel):
    message: str
    percent: int


class JobMeta(BaseModel):
    job_id: str
    file_name: str
    n_pages: int
    is_born_digital: bool
    status: str


class JobStatus(BaseModel):
    job_id: str
    file_name: str
    n_pages: int
    is_born_digital: bool
    status: str
    progress: Optional[Progress] = None
    mode: Optional[str] = None
    pages: Optional[Dict[str, str]] = None
    error: Optional[str] = None
```

- [ ] **Step 4: 實作 `backend/app/main.py`**

```python
"""OCR-Work-platform 後端 API（FastAPI）。"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import engine, schemas
from .jobs import Job, JobStore

# 啟動時讀取平台根目錄的 .env（DeepSeek 金鑰；真實環境變數優先）
engine.load_env_file(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="OCR-Work-platform API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JobStore()
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def _meta(job: Job) -> schemas.JobMeta:
    return schemas.JobMeta(job_id=job.job_id, file_name=job.file_name,
                           n_pages=job.n_pages, is_born_digital=job.is_born_digital,
                           status=job.status)


def _status(job: Job) -> schemas.JobStatus:
    return schemas.JobStatus(job_id=job.job_id, file_name=job.file_name,
                             n_pages=job.n_pages, is_born_digital=job.is_born_digital,
                             status=job.status, progress=job.progress,
                             mode=job.mode, pages=job.pages, error=job.error)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=schemas.JobMeta)
async def create_job(file: UploadFile = File(...)) -> schemas.JobMeta:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支援的副檔名：{ext}")
    data = await file.read()
    job = store.create(file.filename, data)
    return _meta(job)


@app.get("/api/jobs/{job_id}/pages/{page_no}/image")
def page_image(job_id: str, page_no: int) -> FileResponse:
    p = store.preview_path(job_id, page_no)
    if p is None:
        raise HTTPException(status_code=404, detail="找不到該頁影像")
    return FileResponse(str(p), media_type="image/png")


@app.post("/api/jobs/{job_id}/recognize")
def recognize(job_id: str) -> dict:
    job = store.start_recognition(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    return {"job_id": job.job_id, "status": job.status}


@app.get("/api/jobs/{job_id}", response_model=schemas.JobStatus)
def job_status(job_id: str) -> schemas.JobStatus:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    return _status(job)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> None:
    if not store.delete(job_id):
        raise HTTPException(status_code=404, detail="找不到任務")
    return None
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests/test_api.py -q`
Expected: PASS（7 passed）

- [ ] **Step 6: 跑後端全部測試**

Run: `cd /d E:\OCR-Work-platform\backend && python -m pytest tests -q`
Expected: PASS（14 passed：engine 3 ＋ jobs 4 ＋ api 7）

- [ ] **Step 7: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/app/schemas.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(api): FastAPI routes (upload/preview/recognize/poll/delete)"
```

---

## Task 4：啟動腳本與實機冒煙（Swagger）

**Files:**
- Create: `backend/run_api.bat`

- [ ] **Step 1: 建立 `backend/run_api.bat`**

```bat
@echo off
REM 啟動 OCR-Work-platform 後端 API（FastAPI / uvicorn）
cd /d "%~dp0"
python -m uvicorn app.main:app --port 8000
```

- [ ] **Step 2: 背景啟動 uvicorn 並冒煙**

Run（背景啟動）：`cd /d E:\OCR-Work-platform\backend && start "" python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
等約 6 秒後 Run：`curl -s -o NUL -w "health %{http_code}\n" http://127.0.0.1:8000/api/health`
Expected: `health 200`
再 Run：`curl -s -o NUL -w "docs %{http_code}\n" http://127.0.0.1:8000/docs`
Expected: `docs 200`（Swagger UI）

- [ ] **Step 3: Commit**

```bash
cd /d E:\OCR-Work-platform
git add backend/run_api.bat
git commit -m "chore(api): uvicorn launch script"
```

---

## 完成後

Phase 1 交付：可執行的 FastAPI 後端（:8000）＋ Swagger（/docs）＋ 14 個通過測試。Phase 2（React 前端）將另寫 plan，串接本 API 契約。
