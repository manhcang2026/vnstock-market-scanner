const STATES = {
  NORMAL: { label: 'Bình thường', tone: 'neutral' },
  WATCHING: { label: 'Theo dõi', tone: 'watching' },
  FLOW_APPEARING: { label: 'Dòng tiền xuất hiện', tone: 'positive' },
  FLOW_PRICE_CONFIRMED: { label: 'Dòng tiền + giá xác nhận', tone: 'positive' },
  MOMENTUM_MAINTAINED: { label: 'Động lượng duy trì', tone: 'positive' },
  MOMENTUM_WEAKENING: { label: 'Động lượng suy yếu', tone: 'warning' },
  SELLING_PRESSURE: { label: 'Áp lực bán', tone: 'negative' },
}

const DIRECTIONS = {
  NEUTRAL: 'Trung tính',
  BULLISH: 'Hướng tăng',
  BEARISH: 'Hướng giảm',
}

export function cccStatePresentation(value) {
  const raw = typeof value === 'string' ? value.trim() : ''
  const key = raw.toUpperCase()
  const known = Object.hasOwn(STATES, key) ? STATES[key] : null
  return { label: known?.label || raw || '—', tone: known?.tone || 'neutral' }
}

export function cccDirectionLabel(value) {
  const key = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return DIRECTIONS[key] || '—'
}

export function validSignalLevel(value) {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value) ? value : null
}

export function meterSignalLevel(value) {
  const level = validSignalLevel(value)
  return level === null ? null : Math.min(4, Math.max(0, level))
}

export function cccStateSignature(signalState, signalLevel) {
  const state = typeof signalState === 'string' ? signalState.trim().toUpperCase() : ''
  if (!state) return null
  const level = validSignalLevel(signalLevel)
  return `${state}|${level === null ? 'unknown' : level}`
}

export function isStatePresentationDegraded({ metricsTrusted, qualityStatus, feedStatus } = {}) {
  const degraded = ['STALE', 'DEGRADED', 'MISSING', 'UNAVAILABLE', 'UNTRUSTED', 'METRICS_UNTRUSTED', 'PARTIAL', 'NO_DATA', 'DISCONNECTED']
  return metricsTrusted === false
    || degraded.includes(String(qualityStatus || '').toUpperCase())
    || degraded.includes(String(feedStatus || '').toUpperCase())
}
