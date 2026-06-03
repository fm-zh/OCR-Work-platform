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
