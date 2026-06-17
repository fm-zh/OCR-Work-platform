import type { JobMeta, JobStatus, Sheet } from './types'

const BASE = '/api'

export const MAX_UPLOAD_MB = 50

export async function createJob(file: File): Promise<JobMeta> {
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    throw new Error(`檔案 ${(file.size / 1048576).toFixed(1)}MB 超過上限 ${MAX_UPLOAD_MB}MB，請壓縮或分批上傳`)
  }
  const fd = new FormData()
  fd.append('file', file)
  const r = await fetch(`${BASE}/jobs`, { method: 'POST', body: fd })
  if (!r.ok) {
    let detail = ''
    try { detail = (await r.json()).detail } catch { /* 無 JSON 內容 */ }
    throw new Error(detail || `上傳失敗 (${r.status})`)
  }
  return r.json()
}

export async function startRecognize(
  jobId: string, pages: number[],
): Promise<{ job_id: string; status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/recognize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages }),
  })
  if (!r.ok) {
    let detail = ''
    try { detail = (await r.json()).detail } catch { /* 無 JSON 內容 */ }
    throw new Error(detail || `辨識啟動失敗 (${r.status})`)
  }
  return r.json()
}

export async function getStatus(jobId: string): Promise<JobStatus> {
  const r = await fetch(`${BASE}/jobs/${jobId}`)
  if (!r.ok) throw new Error(`查詢失敗 (${r.status})`)
  return r.json()
}

export async function deleteJob(jobId: string): Promise<void> {
  await fetch(`${BASE}/jobs/${jobId}`, { method: 'DELETE' })
}

export function pageImageUrl(jobId: string, page: number): string {
  return `${BASE}/jobs/${jobId}/pages/${page}/image`
}

export async function exportExcel(
  fileName: string, sheets: Record<string, Sheet>, merge: boolean,
): Promise<Blob> {
  const r = await fetch(`${BASE}/excel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_name: fileName, sheets, merge }),
  })
  if (!r.ok) throw new Error(`Excel 匯出失敗 (${r.status})`)
  return r.blob()
}

export async function startStructure(jobId: string): Promise<{ job_id: string; structure_status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/structure`, { method: 'POST' })
  if (!r.ok) throw new Error(`表格整理啟動失敗 (${r.status})`)
  return r.json()
}
