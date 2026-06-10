import { describe, it, expect } from 'vitest'
import { reducer, initialState } from './state'
import type { JobMeta, Sheet } from './types'

const META: JobMeta = { job_id: 'j', file_name: 'f.pdf', n_pages: 2, is_born_digital: false, status: 'created' }
const SHEET: Sheet = { columns: ['項目', '金額'], rows: [['現金', '100']] }

describe('reducer', () => {
  it('SET_META resets tables/view/page/status', () => {
    const s = reducer({ ...initialState, curPage: 3, view: 'table', tables: { 1: SHEET } }, { type: 'SET_META', meta: META })
    expect(s.meta).toEqual(META)
    expect(s.curPage).toBe(1)
    expect(s.tables).toEqual({})
    expect(s.view).toBe('text')
    expect(s.status).toBeNull()
  })
  it('SET_VIEW switches view', () => {
    expect(reducer(initialState, { type: 'SET_VIEW', view: 'table' }).view).toBe('table')
  })
  it('SET_TABLES loads tables', () => {
    expect(reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } }).tables[1]).toEqual(SHEET)
  })
  it('EDIT_CELL updates one cell immutably', () => {
    const s0 = reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } })
    const s1 = reducer(s0, { type: 'EDIT_CELL', page: 1, row: 0, col: 1, value: '999' })
    expect(s1.tables[1].rows[0][1]).toBe('999')
    expect(SHEET.rows[0][1]).toBe('100')
  })
  it('EDIT_HEADER updates one column', () => {
    const s0 = reducer(initialState, { type: 'SET_TABLES', tables: { 1: SHEET } })
    const s1 = reducer(s0, { type: 'EDIT_HEADER', page: 1, col: 0, value: '科目' })
    expect(s1.tables[1].columns[0]).toBe('科目')
  })
  it('GO switches step', () => {
    expect(reducer(initialState, { type: 'GO', step: 2 }).step).toBe(2)
  })
  it('RESET returns initial', () => {
    const dirty = reducer(initialState, { type: 'SET_VIEW', view: 'table' })
    expect(reducer(dirty, { type: 'RESET' })).toEqual(initialState)
  })
})

const META10: JobMeta = {
  job_id: 'j1', file_name: 'a.pdf', n_pages: 10,
  is_born_digital: false, status: 'created',
}

describe('selected pages reducer', () => {
  it('TOGGLE_PAGE adds then removes, kept sorted', () => {
    let s = reducer(initialState, { type: 'TOGGLE_PAGE', page: 5 })
    s = reducer(s, { type: 'TOGGLE_PAGE', page: 2 })
    expect(s.selected).toEqual([2, 5])
    s = reducer(s, { type: 'TOGGLE_PAGE', page: 5 })
    expect(s.selected).toEqual([2])
  })
  it('SET_SELECTED replaces selection', () => {
    const s = reducer(initialState, { type: 'SET_SELECTED', pages: [8, 3, 3] })
    expect(s.selected).toEqual([3, 8])
  })
  it('SELECT_ALL fills 1..n', () => {
    const s = reducer({ ...initialState, meta: META10 },
      { type: 'SELECT_ALL' })
    expect(s.selected).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
  })
  it('CLEAR_SELECTED empties', () => {
    const s = reducer({ ...initialState, selected: [1, 2] },
      { type: 'CLEAR_SELECTED' })
    expect(s.selected).toEqual([])
  })
  it('SET_META clears selection', () => {
    const s = reducer({ ...initialState, selected: [1, 2] },
      { type: 'SET_META', meta: META10 })
    expect(s.selected).toEqual([])
  })
  it('SET_META auto-selects the only page for single-page files', () => {
    const single: JobMeta = { ...META10, n_pages: 1 }
    const s = reducer({ ...initialState, selected: [9] },
      { type: 'SET_META', meta: single })
    expect(s.selected).toEqual([1])
  })
})
