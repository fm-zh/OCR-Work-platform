/** {pageNo: text} → 下載用全文。單頁回純文字；多頁加 '===== 第 N 頁 =====' 。 */
export function combinePages(pages: Record<number, string>): string {
  const keys = Object.keys(pages).map(Number).sort((a, b) => a - b)
  if (keys.length === 0) return ''
  if (keys.length === 1) return pages[keys[0]]
  return keys.map((k) => `===== 第 ${k} 頁 =====\n${pages[k]}`).join('\n\n')
}
