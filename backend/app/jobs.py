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
