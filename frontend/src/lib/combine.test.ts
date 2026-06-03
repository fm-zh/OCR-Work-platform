import { describe, it, expect } from 'vitest'
import { combinePages } from './combine'

describe('combinePages', () => {
  it('single page returns plain text', () => {
    expect(combinePages({ 1: 'hello' })).toBe('hello')
  })
  it('multi page adds headers', () => {
    const out = combinePages({ 1: 'a', 2: 'b' })
    expect(out).toContain('===== 第 1 頁 =====')
    expect(out).toContain('===== 第 2 頁 =====')
    expect(out).toContain('a')
    expect(out).toContain('b')
  })
  it('empty returns empty string', () => {
    expect(combinePages({})).toBe('')
  })
})
