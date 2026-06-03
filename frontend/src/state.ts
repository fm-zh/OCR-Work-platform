import type { JobMeta, JobStatus } from './types'

export interface AppState {
  step: 1 | 2
  meta: JobMeta | null
  status: JobStatus | null
  curPage: number
  edited: Record<number, string>
}

export type Action =
  | { type: 'SET_META'; meta: JobMeta | null }
  | { type: 'SET_STATUS'; status: JobStatus | null }
  | { type: 'SET_PAGE'; page: number }
  | { type: 'EDIT'; page: number; text: string }
  | { type: 'GO'; step: 1 | 2 }
  | { type: 'RESET' }

export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, edited: {},
}

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'SET_META':
      return { ...s, meta: a.meta, status: null, edited: {}, curPage: 1 }
    case 'SET_STATUS':
      return { ...s, status: a.status }
    case 'SET_PAGE':
      return { ...s, curPage: a.page }
    case 'EDIT':
      return { ...s, edited: { ...s.edited, [a.page]: a.text } }
    case 'GO':
      return { ...s, step: a.step }
    case 'RESET':
      return initialState
  }
}
