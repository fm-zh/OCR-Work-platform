import { describe, it, expect } from 'vitest'
import { reducer, initialState } from './state'
import type { JobMeta } from './types'

const META: JobMeta = { job_id: 'j', file_name: 'f.pdf', n_pages: 2, is_born_digital: false, status: 'created' }

describe('reducer', () => {
  it('SET_META stores meta and resets page/edited/status', () => {
    const s = reducer({ ...initialState, curPage: 3, edited: { 1: 'x' } }, { type: 'SET_META', meta: META })
    expect(s.meta).toEqual(META)
    expect(s.curPage).toBe(1)
    expect(s.edited).toEqual({})
    expect(s.status).toBeNull()
  })
  it('EDIT updates one page', () => {
    const s = reducer(initialState, { type: 'EDIT', page: 2, text: 'hi' })
    expect(s.edited[2]).toBe('hi')
  })
  it('GO switches step', () => {
    expect(reducer(initialState, { type: 'GO', step: 2 }).step).toBe(2)
  })
  it('RESET returns initial', () => {
    const dirty = reducer(initialState, { type: 'EDIT', page: 1, text: 'x' })
    expect(reducer(dirty, { type: 'RESET' })).toEqual(initialState)
  })
})
