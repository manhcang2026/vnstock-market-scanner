export const FILTER_FIELDS = [
  { id: 'exchange', label: 'Sàn', type: 'category' },
  { id: 'industry', label: 'Ngành', type: 'category' },
  { id: 'price', label: 'Giá', type: 'number' },
  { id: 'changePct', label: '% thay đổi', type: 'number' },
  { id: 'volume', label: 'Khối lượng', type: 'number' },
  { id: 'nearMa10', label: 'Gần MA10', type: 'number' },
  { id: 'nearMa200', label: 'Gần MA200', type: 'number' },
  { id: 'positionMa10', label: 'Vị trí so MA10', type: 'category' },
  { id: 'positionMa200', label: 'Vị trí so MA200', type: 'category' },
]

export const NUMERIC_OPERATORS = [
  { id: 'gt', label: '>' }, { id: 'gte', label: '≥' },
  { id: 'lt', label: '<' }, { id: 'lte', label: '≤' },
  { id: 'eq', label: '=' }, { id: 'between', label: 'trong khoảng' },
]

export function finiteNumber(value) {
  if (value === null || value === undefined || typeof value === 'boolean' || String(value).trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function signedMaDistancePct(price, maValue) {
  const current = finiteNumber(price)
  const ma = finiteNumber(maValue)
  if (current === null || ma === null || ma <= 0) return null
  return ((current - ma) / ma) * 100
}

export function nearMaDistancePct(price, maValue) {
  const signed = signedMaDistancePct(price, maValue)
  return signed === null ? null : Math.abs(signed)
}

export function formatSignedPct(value) {
  const number = finiteNumber(value)
  if (number === null) return '—'
  return `${number > 0 ? '+' : ''}${number.toFixed(1)}%`
}

export function signedDistanceForRow(row, period) {
  const direct = finiteNumber(row[`distanceMa${period}Pct`])
  return direct === null ? signedMaDistancePct(row.price, row[`ma${period}`]) : direct
}

export function scannerFieldValue(row, field) {
  if (field === 'symbol' || field === 'exchange' || field === 'industry') {
    const value = row[field]
    return typeof value === 'string' && value.trim() ? value.trim() : null
  }
  if (field === 'nearMa10' || field === 'nearMa200') {
    const signed = signedDistanceForRow(row, field === 'nearMa10' ? 10 : 200)
    return signed === null ? null : Math.abs(signed)
  }
  if (field === 'positionMa10' || field === 'positionMa200') {
    const signed = signedDistanceForRow(row, field === 'positionMa10' ? 10 : 200)
    return signed === null || signed === 0 ? null : signed > 0 ? 'above' : 'below'
  }
  if (['price', 'changePct', 'volume'].includes(field)) return finiteNumber(row[field])
  return null
}

export function fieldAvailability(rows) {
  const fields = ['symbol', ...FILTER_FIELDS.map((field) => field.id)]
  return Object.fromEntries(fields.map((field) => [field, rows.some((row) => scannerFieldValue(row, field) !== null)]))
}

export function categoryOptions(rows) {
  const unique = (field) => [...new Set(rows.map((row) => scannerFieldValue(row, field)).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'))
  return {
    exchange: unique('exchange').map((value) => ({ value, label: value })),
    industry: unique('industry').map((value) => ({ value, label: value })),
    positionMa10: [{ value: 'above', label: 'Trên MA10' }, { value: 'below', label: 'Dưới MA10' }],
    positionMa200: [{ value: 'above', label: 'Trên MA200' }, { value: 'below', label: 'Dưới MA200' }],
  }
}

export function configuredCondition(condition) {
  const definition = FILTER_FIELDS.find((field) => field.id === condition.field)
  if (!definition) return false
  if (definition.type === 'category') return Array.isArray(condition.values) && condition.values.length > 0
  const first = finiteNumber(condition.value)
  if (first === null) return false
  const nonnegative = ['price', 'volume', 'nearMa10', 'nearMa200'].includes(condition.field)
  if (nonnegative && first < 0) return false
  if (condition.operator === 'between') {
    const second = finiteNumber(condition.valueTo)
    return second !== null && (!nonnegative || second >= 0) && first <= second
  }
  return NUMERIC_OPERATORS.some((operator) => operator.id === condition.operator)
}

function matchesCondition(row, condition) {
  const value = scannerFieldValue(row, condition.field)
  if (value === null) return false
  const definition = FILTER_FIELDS.find((field) => field.id === condition.field)
  if (definition.type === 'category') return condition.values.includes(value)
  const target = finiteNumber(condition.value)
  if (condition.operator === 'gt') return value > target
  if (condition.operator === 'gte') return value >= target
  if (condition.operator === 'lt') return value < target
  if (condition.operator === 'lte') return value <= target
  if (condition.operator === 'eq') return value === target
  return value >= target && value <= finiteNumber(condition.valueTo)
}

export function activeConditions(conditions, availability) {
  return conditions.filter((condition) => availability[condition.field] && configuredCondition(condition))
}

export function applyScannerFilters(rows, conditions, availability) {
  const active = activeConditions(conditions, availability)
  return rows.filter((row) => active.every((condition) => matchesCondition(row, condition)))
}

export function describeCondition(condition) {
  const definition = FILTER_FIELDS.find((field) => field.id === condition.field)
  const label = definition?.label || condition.field
  if (definition?.type === 'category') {
    const options = categoryOptions([])[condition.field] || []
    const values = condition.values.map((value) => options.find((option) => option.value === value)?.label || value)
    return `${label}: ${values.join('/')}`
  }
  const operator = NUMERIC_OPERATORS.find((item) => item.id === condition.operator)?.label || '='
  const suffix = ['changePct', 'nearMa10', 'nearMa200'].includes(condition.field) ? '%' : ''
  return condition.operator === 'between'
    ? `${label} ${condition.value}–${condition.valueTo}${suffix}`
    : `${label} ${operator} ${condition.value}${suffix}`
}
