"""OCR-Work-platform 後端 API（FastAPI）。"""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import engine, excel, schemas
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
ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png"}

# 上傳防護：以「單一總檔大小」為唯一關卡（不再分頁數型別設上限）。
# Cloudflare 免費方案單一請求硬限約 100MB，故 50MB 留足安全邊距。
# 辨識（逐頁串流）與預覽（逐頁渲染）記憶體都只與單頁有關、與頁數無關，
# 故總檔大小即足以同時擋住「過大」與「過多頁」兩種風險。
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _meta(job: Job) -> schemas.JobMeta:
    return schemas.JobMeta(job_id=job.job_id, file_name=job.file_name,
                           n_pages=job.n_pages, is_born_digital=job.is_born_digital,
                           status=job.status)


def _status(job: Job) -> schemas.JobStatus:
    return schemas.JobStatus(job_id=job.job_id, file_name=job.file_name,
                             n_pages=job.n_pages, is_born_digital=job.is_born_digital,
                             status=job.status, progress=job.progress,
                             mode=job.mode, pages=job.pages, error=job.error,
                             structure_status=job.structure_status,
                             tables=job.tables, structure_error=job.structure_error)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=schemas.JobMeta)
async def create_job(file: UploadFile = File(...)) -> schemas.JobMeta:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支援的副檔名：{ext}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"檔案過大：{len(data) / 1048576:.1f}MB，上限 "
                   f"{MAX_UPLOAD_BYTES // 1048576}MB，請壓縮或分批上傳")
    job = store.create(file.filename, data)
    return _meta(job)


@app.get("/api/jobs/{job_id}/pages/{page_no}/image")
def page_image(job_id: str, page_no: int) -> FileResponse:
    p = store.preview_path(job_id, page_no)
    if p is None:
        raise HTTPException(status_code=404, detail="找不到該頁影像")
    return FileResponse(str(p), media_type="image/png")


@app.post("/api/jobs/{job_id}/recognize")
def recognize(job_id: str, req: schemas.RecognizeRequest) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    pages = sorted(set(req.pages))
    if not pages:
        raise HTTPException(status_code=400, detail="請至少選擇一頁")
    if pages[0] < 1 or pages[-1] > job.n_pages:
        raise HTTPException(
            status_code=400,
            detail=f"頁碼超出範圍：本檔共 {job.n_pages} 頁")
    job = store.start_recognition(job_id, pages=pages)
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


@app.post("/api/excel")
def export_excel(req: schemas.ExcelRequest) -> Response:
    if not req.sheets:
        raise HTTPException(status_code=400, detail="sheets 不可為空")
    structured: dict[int, dict] = {}
    for k, sheet in req.sheets.items():
        try:
            page_no = int(k)
        except ValueError:
            continue
        structured[page_no] = {"columns": sheet.columns, "rows": sheet.rows}
    stem = Path(req.file_name).stem or "result"
    if req.merge:
        pages_in_order = [structured[p] for p in sorted(structured)]
        merged = excel.merge_sheets(pages_in_order)
        data = excel.build_workbook({1: merged}, sheet_titles={1: stem})
    else:
        data = excel.build_workbook(structured)
    quoted = urllib.parse.quote(f"{stem}.xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


@app.post("/api/jobs/{job_id}/structure")
def structure_job(job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    if job.status != "done":
        raise HTTPException(status_code=409, detail="請先完成辨識")
    job = store.start_structuring(job_id)
    return {"job_id": job.job_id, "structure_status": job.structure_status}
