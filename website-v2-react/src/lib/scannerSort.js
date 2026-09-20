import { scannerFieldValue } from './scannerFilters.js'

export const SORT_FIELDS = [
  { id: 'symbol', label: 'Mã' },
  { id: 'exchange', label: 'Sàn' },
  { id: 'industry', label: 'Ngành' },
  { id: 'price', label: 'Giá' },
  { id: 'changePct', label: '% thay đổi' },
  { id: 'volume', label: 'Khối lượng' },
  { id: 'nearMa10', label: 'Khoảng cách MA10' },
  { id: 'nearMa200', label: 'Khoảng cách MA200' },
]

export function activeSortRules(rules, availability) {
  return rules.filter((rule) => availability[rule.field] && ['asc', 'desc'].includes(rule.direction))
}

export function sortScannerRows(rows, rules, availability) {
  const active = activeSortRules(rules, availability)
  if (!active.length) return rows
  return rows.map((row, index) => ({ row, index })).sort((left, right) => {
    for (const rule of active) {
      const a = scannerFieldValue(left.row, rule.field)
      const b = scannerFieldValue(right.row, rule.field)
      if (a === null && b === null) continue
      if (a === null) return 1
      if (b === null) return -1
      const comparison = typeof a === 'string' ? a.localeCompare(b, 'vi') : a - b
      if (comparison) return rule.direction === 'asc' ? comparison : -comparison
    }
    return left.index - right.index
  }).map((item) => item.row)
}

export function describeSortRule(rule) {
  if (rule.field === 'nearMa10' || rule.field === 'nearMa200') {
    return `${rule.direction === 'asc' ? 'Gần' : 'Xa'} ${rule.field === 'nearMa10' ? 'MA10' : 'MA200'} nhất`
  }
  const label = SORT_FIELDS.find((field) => field.id === rule.field)?.label || rule.field
  if (['symbol', 'exchange', 'industry'].includes(rule.field)) return `${label} ${rule.direction === 'asc' ? 'A–Z' : 'Z–A'}`
  return `${label} ${rule.direction === 'asc' ? 'thấp nhất' : 'cao nhất'}`
}
