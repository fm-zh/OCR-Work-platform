import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

vi.mock('./api', () => ({
  MAX_UPLOAD_MB: 20,
  createJob: vi.fn(),
  startRecognize: vi.fn(),
  getStatus: vi.fn(),
  deleteJob: vi.fn(),
  pageImageUrl: () => 'about:blank',
}))

describe('App', () => {
  it('renders title and step 1', () => {
    render(<App />)
    expect(screen.getByText(/OCR-Work-platform/)).toBeTruthy()
    expect(screen.getByText(/步驟 1/)).toBeTruthy()
  })
})
