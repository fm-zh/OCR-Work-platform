import { describe, it, expect, vi, afterEach } from 'vitest'
import * as api from './api'

afterEach(() => { vi.restoreAllMocks() })

describe('api', () => {
  it('createJob posts multipart and returns meta', async () => {
    const meta = { job_id: 'x', file_name: 'f.pdf', n_pages: 1, is_born_digital: true, status: 'created' }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => meta })
    vi.stubGlobal('fetch', fetchMock)
    const f = new File([new Uint8Array([1])], 'f.pdf', { type: 'application/pdf' })
    const res = await api.createJob(f)
    expect(res).toEqual(meta)
    expect(fetchMock).toHaveBeenCalledWith('/api/jobs', expect.objectContaining({ method: 'POST' }))
  })

  it('getStatus fetches job by id', async () => {
    const st = { job_id: 'x', status: 'done' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => st }))
    const res = await api.getStatus('x')
    expect(res.status).toBe('done')
  })

  it('pageImageUrl builds url', () => {
    expect(api.pageImageUrl('x', 2)).toBe('/api/jobs/x/pages/2/image')
  })

  it('createJob throws on http error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }))
    const f = new File([new Uint8Array([1])], 'f.pdf')
    await expect(api.createJob(f)).rejects.toThrow()
  })
})
