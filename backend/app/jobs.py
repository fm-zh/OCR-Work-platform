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

from . import engine, excel


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
    selected: Optional[list] = None   # 實際辨識的原始頁碼，如 [3,5,8]
    structure_status: str = "idle"   # idle | running | done | error
    tables: Optional[dict] = None     # {"1": {"columns":[...], "rows":[[...]]}}
    structure_error: Optional[str] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # 序列化辨識：這台機器記憶體吃緊，單次辨識峰值約 1.2GB，
        # 並發會疊加導致 OOM，故一次只跑一個。
        self._pool = ThreadPoolExecutor(max_workers=1)

    def create(self, file_name: str, data: bytes,
               max_pages_scanned: Optional[int] = None,
               max_pages_born: Optional[int] = None) -> Job:
        job_id = uuid.uuid4().hex
        work = Path(tempfile.mkdtemp(prefix=f"ocrjob_{job_id}_"))
        fpath = work / file_name
        fpath.write_bytes(data)
        det = engine.detect(fpath)
        # 在「渲染影像」之前就擋掉頁數過多的檔，避免吃爆記憶體。
        limit = max_pages_born if det["is_born_digital"] else max_pages_scanned
        if limit is not None and det["n_pages"] > limit:
            shutil.rmtree(work, ignore_errors=True)
            kind = "文字層" if det["is_born_digital"] else "掃描"
            raise ValueError(
                f"頁數過多：{det['n_pages']} 頁（{kind}檔上限 {limit} 頁），請分批上傳")
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

    def start_recognition(self, job_id: str, pages=None) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in ("running", "done"):
            return job
        job.selected = list(pages) if pages is not None else None
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
            res = engine.recognize(job.file_path, progress=_progress,
                                    pages=job.selected)
            job.mode = res["mode"]
            job.pages = {str(k): v for k, v in res["pages"].items()}
            job.progress = {"message": "完成", "percent": 100}
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "error"

    def start_structuring(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status != "done":
            return job  # 尚未辨識完，不啟動（呼叫端回 409）
        if job.structure_status in ("running", "done"):
            return job
        job.structure_status = "running"
        self._pool.submit(self._run_structuring, job_id)
        return job

    def _run_structuring(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        try:
            key = engine.resolve_deepseek_key()
            items = sorted((job.pages or {}).items(),
                           key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
            tables: dict = {}
            if items:
                with ThreadPoolExecutor(max_workers=min(4, len(items))) as ex:
                    for k, st in ex.map(
                        lambda kv: (kv[0], excel.structure_page(kv[1], key)), items):
                        tables[k] = st
            job.tables = tables
            job.structure_status = "done"
        except Exception as exc:  # noqa: BLE001
            job.structure_error = f"{type(exc).__name__}: {exc}"
            job.structure_status = "error"
