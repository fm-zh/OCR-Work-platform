// 頁碼字串 ⇄ 排序去重的頁碼陣列。縮圖打勾與頁碼輸入共用同一份選取狀態。

export function parseRange(input: string, maxPage: number): number[] {
  const set = new Set<number>()
  for (const raw of input.split(',')) {
    const part = raw.trim()
    if (!part) continue
    const m = part.match(/^(\d+)\s*-\s*(\d+)$/)
    if (m) {
      const a = Number(m[1])
      const b = Number(m[2])
      if (a <= b) for (let n = a; n <= b; n++) add(set, n, maxPage)
    } else if (/^\d+$/.test(part)) {
      add(set, Number(part), maxPage)
    }
  }
  return [...set].sort((x, y) => x - y)
}

function add(set: Set<number>, n: number, maxPage: number) {
  if (n >= 1 && n <= maxPage) set.add(n)
}

export function formatRange(pages: number[]): string {
  const s = [...pages].sort((a, b) => a - b)
  const out: string[] = []
  let i = 0
  while (i < s.length) {
    let j = i
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++
    out.push(i === j ? `${s[i]}` : `${s[i]}-${s[j]}`)
    i = j + 1
  }
  return out.join(',')
}
