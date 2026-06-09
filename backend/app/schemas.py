"""API 回應模型。"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class Sheet(BaseModel):
    columns: List[str]
    rows: List[List[str]]


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
    structure_status: str = "idle"
    tables: Optional[Dict[str, Sheet]] = None
    structure_error: Optional[str] = None


class ExcelRequest(BaseModel):
    file_name: str
    sheets: Dict[str, Sheet]


class RecognizeRequest(BaseModel):
    pages: List[int]
