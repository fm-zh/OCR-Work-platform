import type { JobMeta, JobStatus, Sheet } from './types'

export interface AppState {
  step: 1 | 2
  meta: JobMeta | null
  status: JobStatus | null
  curPage: number
  view: 'text' | 'table'
  tables: Record<number, Sheet>
  selected: number[]
}

export type Action =
  | { type: 'SET_META'; meta: JobMeta | null }
  | { type: 'SET_STATUS'; status: JobStatus | null }
  | { type: 'SET_PAGE'; page: number }
  | { type: 'TOGGLE_PAGE'; page: number }
  | { type: 'SET_SELECTED'; pages: number[] }
  | { type: 'SELECT_ALL' }
  | { type: 'CLEAR_SELECTED' }
  | { type: 'SET_VIEW'; view: 'text' | 'table' }
  | { type: 'SET_TABLES'; tables: Record<number, Sheet> }
  | { type: 'EDIT_CELL'; page: number; row: number; col: number; value: string }
  | { type: 'EDIT_HEADER'; page: number; col: number; value: string }
  | { type: 'GO'; step: 1 | 2 }
  | { type: 'RESET' }

export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, view: 'text', tables: {},
  selected: [],
}

function editCell(t: Sheet, row: number, col: number, value: string): Sheet {
  return {
    columns: t.columns,
    rows: t.rows.map((r, ri) => (ri === row ? r.map((c, ci) => (ci === col ? value : c)) : r)),
  }
}

function editHeader(t: Sheet, col: number, value: string): Sheet {
  return { columns: t.columns.map((c, ci) => (ci === col ? value : c)), rows: t.rows }
}

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'SET_META':
      return { ...s, meta: a.meta, status: null, tables: {}, view: 'text', curPage: 1, selected: [] }
    case 'SET_STATUS':
      return { ...s, status: a.status }
    case 'SET_PAGE':
      return { ...s, curPage: a.page }
    case 'TOGGLE_PAGE': {
      const has = s.selected.includes(a.page)
      const next = has ? s.selected.filter((p) => p !== a.page)
                       : [...s.selected, a.page].sort((x, y) => x - y)
      return { ...s, selected: next }
    }
    case 'SET_SELECTED':
      return { ...s, selected: [...new Set(a.pages)].sort((x, y) => x - y) }
    case 'SELECT_ALL':
      return {
        ...s,
        selected: s.meta
          ? Array.from({ length: s.meta.n_pages }, (_, i) => i + 1)
          : [],
      }
    case 'CLEAR_SELECTED':
      return { ...s, selected: [] }
    case 'SET_VIEW':
      return { ...s, view: a.view }
    case 'SET_TABLES':
      return { ...s, tables: a.tables }
    case 'EDIT_CELL': {
      const t = s.tables[a.page]
      if (!t) return s
      return { ...s, tables: { ...s.tables, [a.page]: editCell(t, a.row, a.col, a.value) } }
    }
    case 'EDIT_HEADER': {
      const t = s.tables[a.page]
      if (!t) return s
      return { ...s, tables: { ...s.tables, [a.page]: editHeader(t, a.col, a.value) } }
    }
    case 'GO':
      return { ...s, step: a.step }
    case 'RESET':
      return initialState
  }
}
