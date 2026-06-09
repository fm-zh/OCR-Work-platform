import { describe, it, expect } from 'vitest'
import { parseRange, formatRange } from './pageRange'

describe('parseRange', () => {
  it('parses commas and ranges', () => {
    expect(parseRange('3,5,8-10', 30)).toEqual([3, 5, 8, 9, 10])
  })
  it('dedupes and sorts', () => {
    expect(parseRange('8,3,3,5', 30)).toEqual([3, 5, 8])
  })
  it('ignores out-of-range and zero', () => {
    expect(parseRange('0,2,99', 5)).toEqual([2])
  })
  it('ignores reversed ranges', () => {
    expect(parseRange('5-3', 30)).toEqual([])
  })
  it('tolerates spaces and trailing commas', () => {
    expect(parseRange(' 1 , 2 , ', 30)).toEqual([1, 2])
  })
  it('empty string yields empty array', () => {
    expect(parseRange('', 30)).toEqual([])
  })
})

describe('formatRange', () => {
  it('collapses consecutive runs', () => {
    expect(formatRange([3, 5, 8, 9, 10])).toBe('3,5,8-10')
  })
  it('single page', () => {
    expect(formatRange([4])).toBe('4')
  })
  it('empty array yields empty string', () => {
    expect(formatRange([])).toBe('')
  })
})
