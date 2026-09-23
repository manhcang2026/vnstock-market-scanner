import { finiteNumber } from './scannerFilters.js'

const PUBLIC_NUMBERS = {
  price: 'last_price', refPrice: 'ref_price', changePct: 'change_pct',
  volume: 'total_volume', ma10: 'ma10', ma200: 'ma200',
  distanceMa10Pct: 'distance_ma10_pct', distanceMa200Pct: 'distance_ma200_pct',
}
const CCC_NUMBERS = {
  dayRvol: 'day_rvol', rvol15: 'rvol15', rvol30: 'rvol30',
  price5: 'price5_pct', price15: 'price15_pct', atoRvol: 'ato_rvol',
  atcRvol: 'atc_rvol', atcPriceImpactPct: 'atc_price_impact_pct',
  signalLevel: 'signal_level',
}
const CCC_TEXT = {
  signalState: 'signal_state', signalDirection: 'signal_direction',
  signalSummary: 'signal_summary_vi',
}
const SIGNAL_LABELS = {
  WATCHING: 'Theo dõi', FLOW_APPEARING: 'Dòng tiền xuất hiện',
  FLOW_PRICE_CONFIRMED: 'Dòng tiền xác nhận giá',
  MOMENTUM_MAINTAINED: 'Đà tăng duy trì', MOMENTUM_WEAKENING: 'Đà tăng suy yếu',
  SELLING_PRESSURE: 'Áp lực bán',
}

export function scannerSymbol(value) {
  return String(value || '').trim().toUpperCase()
}

function textOrNull(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function numberFields(source, mapping) {
  return Object.fromEntries(Object.entries(mapping).map(([target, key]) => [target, finiteNumber(source?.[key])]))
}

const EMPTY_MARKET = {
  ...numberFields(null, PUBLIC_NUMBERS),
  tradingDate: null, eventAt: null, sessionType: null,
  feedStatus: null, qualityStatus: null,
  ...numberFields(null, CCC_NUMBERS),
  signalState: null, signalLevel: null, signalDirection: null,
  signalSummary: null, reasonCodes: null, metricsTrusted: null, ccc: null,
}

export function normalizeScannerRow(row) {
  const protectedData = row?.ccc && typeof row.ccc === 'object' && !Array.isArray(row.ccc)
    ? row.ccc : null
  const ccc = protectedData ? {
    ...numberFields(protectedData, CCC_NUMBERS),
    ...Object.fromEntries(Object.entries(CCC_TEXT).map(([target, key]) => [target, textOrNull(protectedData[key])])),
    reasonCodes: Array.isArray(protectedData.reason_codes) && protectedData.reason_codes.every((code) => typeof code === 'string')
      ? protectedData.reason_codes : null,
    metricsTrusted: typeof protectedData.metrics_trusted === 'boolean' ? protectedData.metrics_trusted : null,
  } : null
  return {
    ...EMPTY_MARKET,
    symbol: scannerSymbol(row?.symbol),
    exchange: textOrNull(row?.exchange),
    ...numberFields(row, PUBLIC_NUMBERS),
    tradingDate: textOrNull(row?.trading_date),
    eventAt: textOrNull(row?.event_at),
    sessionType: textOrNull(row?.session_type),
    feedStatus: textOrNull(row?.feed_status),
    qualityStatus: textOrNull(row?.quality_status),
    ...(ccc || {}),
    ccc,
  }
}

export function normalizeScannerResponse(response) {
  if (response?.contract_version !== 'ccc-scanner-v1' || !Array.isArray(response.rows)) {
    throw new Error('Phản hồi Scanner không hợp lệ.')
  }
  return {
    technicalScope: textOrNull(response.technical_scope),
    rows: response.rows.map(normalizeScannerRow).filter((row) => row.symbol),
  }
}

export function mergeScannerRows(directoryRows, scannerRows, { includeScannerOnly = true } = {}) {
  const marketBySymbol = new Map(scannerRows.map((row) => [scannerSymbol(row.symbol), row]))
  const seen = new Set()
  const merged = directoryRows.map((identity) => {
    const symbol = scannerSymbol(identity.symbol)
    seen.add(symbol)
    const market = marketBySymbol.get(symbol)
    return {
      ...EMPTY_MARKET,
      ...market,
      ...identity,
      symbol,
      exchange: identity.exchange || market?.exchange || null,
      display_name: identity.display_name || null,
      company_name: identity.company_name || null,
    }
  })
  if (includeScannerOnly) {
    for (const [symbol, market] of marketBySymbol) {
      if (symbol && !seen.has(symbol)) merged.push({ ...market, display_name: null, company_name: null })
    }
  }
  return merged
}

export function scannerStateCue(row) {
  if (!row?.ccc) return null
  return row.signalState && !['NONE', 'NORMAL', 'UNAVAILABLE'].includes(row.signalState)
    ? SIGNAL_LABELS[row.signalState] || row.signalState : null
}

export function scannerSignalCue(row) {
  if (!row?.ccc) return null
  if (['NONE', 'NORMAL', 'UNAVAILABLE'].includes(row.signalState)) return null
  const state = scannerStateCue(row)
  if (row.signalSummary) return row.signalSummary.length > 56 && state ? state : row.signalSummary
  return state
}
