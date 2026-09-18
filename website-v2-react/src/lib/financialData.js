import { supabase } from './supabase'

function numberOrNull(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!sorted.length) return null
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2
}

function scoreBand(value, bands) {
  if (value === null) return null
  return bands.find(([predicate]) => predicate(value))?.[1] ?? 0
}

function valuationScore(value, industryMedian, maximum) {
  if (value === null || industryMedian === null || value <= 0 || industryMedian <= 0) return null
  const ratio = value / industryMedian
  if (ratio <= 0.8) return maximum
  if (ratio <= 1) return Math.round(maximum * 0.8)
  if (ratio <= 1.2) return Math.round(maximum * 0.6)
  if (ratio <= 1.5) return Math.round(maximum * 0.35)
  return Math.max(1, Math.round(maximum * 0.15))
}

export function calculateFinancialScore(row, peers = []) {
  if (!row || row.data_status === 'NO_FINANCIAL_DATA') {
    return { earned: 0, available: 0, coverage: 0, label: 'Chưa có dữ liệu', parts: [] }
  }

  const parts = []
  let earned = 0
  let available = 0
  const add = (name, maximum, value, detail) => {
    if (!Number.isFinite(value)) return
    available += maximum
    earned += value
    parts.push({ name, earned: value, maximum, detail })
  }

  const py = numberOrNull(row.profit_yoy_pct)
  const iy = numberOrNull(row.income_yoy_pct)
  const pq = numberOrNull(row.profit_qoq_pct)
  const roe = numberOrNull(row.roea_pct)
  const roa = numberOrNull(row.roaa_pct)
  const debtEquity = numberOrNull(row.debt_equity_pct)
  const debtAssets = numberOrNull(row.debt_assets_pct)
  const pe = numberOrNull(row.pe)
  const pb = numberOrNull(row.pb)

  add('LNST so với cùng kỳ', 20, scoreBand(py, [[v => v >= 30, 20], [v => v >= 20, 16], [v => v >= 10, 12], [v => v >= 0, 7], [() => true, 0]]), py)
  add('Doanh thu / thu nhập so cùng kỳ', 10, scoreBand(iy, [[v => v >= 20, 10], [v => v >= 10, 8], [v => v >= 5, 5], [v => v >= 0, 3], [() => true, 0]]), iy)
  add('LNST so với quý trước', 5, scoreBand(pq, [[v => v >= 20, 5], [v => v >= 10, 4], [v => v >= 0, 3], [v => v >= -10, 1], [() => true, 0]]), pq)
  add('ROE', 20, scoreBand(roe, [[v => v >= 20, 20], [v => v >= 15, 16], [v => v >= 10, 11], [v => v >= 5, 6], [v => v >= 0, 2], [() => true, 0]]), roe)
  add('ROA', 10, scoreBand(roa, [[v => v >= 10, 10], [v => v >= 7, 8], [v => v >= 5, 6], [v => v >= 2, 3], [v => v >= 0, 1], [() => true, 0]]), roa)

  if (row.financial_model === 'NORMAL') {
    add('Nợ vay / vốn chủ', 10, scoreBand(debtEquity, [[v => v < 30, 10], [v => v < 60, 8], [v => v < 100, 5], [v => v < 150, 2], [() => true, 0]]), debtEquity)
    add('Nợ / tổng tài sản', 10, scoreBand(debtAssets, [[v => v < 30, 10], [v => v < 45, 8], [v => v < 60, 5], [v => v < 75, 2], [() => true, 0]]), debtAssets)
  }

  const medianPe = median(peers.map(item => numberOrNull(item.pe)))
  const medianPb = median(peers.map(item => numberOrNull(item.pb)))
  add('P/E so cùng ngành', 8, valuationScore(pe, medianPe, 8), pe)
  add('P/B so cùng ngành', 7, valuationScore(pb, medianPb, 7), pb)

  return {
    earned,
    available,
    coverage: available,
    label: available ? `${earned}/${available}` : 'Chưa đủ dữ liệu',
    parts,
  }
}

export async function fetchFinancialContext(symbol) {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  const { data: financial, error } = await supabase
    .from('financial_latest')
    .select('*')
    .eq('symbol', symbol)
    .maybeSingle()
  if (error) throw error
  if (!financial) return { financial: null, peers: [], score: calculateFinancialScore(null) }

  let peers = []
  if (financial.website_group) {
    const { data, error: peerError } = await supabase
      .from('financial_latest')
      .select('pe,pb,website_group')
      .eq('website_group', financial.website_group)
    if (peerError) throw peerError
    peers = data || []
  }
  return { financial, peers, score: calculateFinancialScore(financial, peers) }
}

export async function fetchQuarterlyFinancials(symbol) {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  const { data, error } = await supabase
    .from('financial_quarterly')
    .select('*')
    .eq('symbol', symbol)
    .order('year', { ascending: false })
    .order('quarter', { ascending: false })
    .limit(12)
  if (error) throw error
  return data || []
}
