export interface JobMeta {
  job_id: string
  file_name: string
  n_pages: number
  is_born_digital: boolean
  status: string
}

export interface Progress {
  message: string
  percent: number
}

export interface Sheet {
  columns: string[]
  rows: string[][]
}

export interface JobStatus {
  job_id: string
  file_name: string
  n_pages: number
  is_born_digital: boolean
  status: 'created' | 'running' | 'done' | 'error'
  progress: Progress | null
  mode: string | null
  pages: Record<string, string> | null
  error: string | null
  structure_status: 'idle' | 'running' | 'done' | 'error'
  tables: Record<string, Sheet> | null
  structure_error: string | null
}
