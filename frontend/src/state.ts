import type { JobMeta, JobStatus, Sheet } from './types'

export interface AppState {
  step: 1 | 2
  meta: JobMeta | null
  status: JobStatus | null
  curPage: number
  view: 'text' | 'table'
  tables: Record<number, Sheet>
}

export type Action =
  | { type: 'SET_META'; meta: JobMeta | null }
  | { type: 'SET_STATUS'; status: JobStatus | null }
  | { type: 'SET_PAGE'; page: number }
  | { type: 'SET_VIEW'; view: 'text' | 'table' }
  | { type: 'SET_TABLES'; tables: Record<number, Sheet> }
  | { type: 'EDIT_CELL'; page: number; row: number; col: number; value: string }
  | { type: 'EDIT_HEADER'; page: number; col: number; value: string }
  | { type: 'GO'; step: 1 | 2 }
  | { type: 'RESET' }

export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, view: 'text', tables: {},
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
      return { ...s, meta: a.meta, status: null, tables: {}, view: 'text', curPage: 1 }
    case 'SET_STATUS':
      return { ...s, status: a.status }
    case 'SET_PAGE':
      return { ...s, curPage: a.page }
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
