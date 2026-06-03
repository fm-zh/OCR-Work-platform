import type { JobMeta, JobStatus } from './types'

const BASE = '/api'

export async function createJob(file: File): Promise<JobMeta> {
  const fd = new FormData()
  fd.append('file', file)
  const r = await fetch(`${BASE}/jobs`, { method: 'POST', body: fd })
  if (!r.ok) throw new Error(`上傳失敗 (${r.status})`)
  return r.json()
}

export async function startRecognize(jobId: string): Promise<{ job_id: string; status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/recognize`, { method: 'POST' })
  if (!r.ok) throw new Error(`辨識啟動失敗 (${r.status})`)
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
