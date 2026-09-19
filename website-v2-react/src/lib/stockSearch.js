import { publicSupabase } from './publicSupabase'

let metadataPromise = null

function normalizeSearchText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
    .toUpperCase()
}

async function loadStockMetadata() {
  if (!publicSupabase) return []

  if (!metadataPromise) {
    metadataPromise = publicSupabase
      .from('stock_metadata')
      .select('symbol,display_name,company_name,exchange')
      .order('symbol')
      .then(({ data, error }) => {
        if (error) throw error
        return Array.isArray(data) ? data : []
      })
      .catch((error) => {
        metadataPromise = null
        throw error
      })
  }

  return metadataPromise
}

function scoreRow(row, normalizedQuery) {
  const symbol = normalizeSearchText(row.symbol)
  const display = normalizeSearchText(row.display_name)
  const company = normalizeSearchText(row.company_name)

  if (symbol === normalizedQuery) return 100
  if (display === normalizedQuery) return 96
  if (company === normalizedQuery) return 94
  if (display.startsWith(normalizedQuery)) return 90
  if (company.startsWith(normalizedQuery)) return 88
  if (display.includes(normalizedQuery)) return 82
  if (company.includes(normalizedQuery)) return 80
  return 0
}

export async function findUniqueStockByName(query) {
  const normalizedQuery = normalizeSearchText(query)
  if (!normalizedQuery) return null

  const rows = await loadStockMetadata()
  const candidates = rows
    .map((row) => ({ row, score: scoreRow(row, normalizedQuery) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.row.symbol.localeCompare(b.row.symbol))

  if (candidates.length === 0) return null

  const bestScore = candidates[0].score
  const best = candidates.filter((item) => item.score === bestScore)

  // Auto-open only when the best textual match is unique.
  if (best.length !== 1) return null

  return best[0].row
}

export async function findStockMetadataBySymbol(symbol) {
  const normalizedSymbol = normalizeSearchText(symbol)
  if (!normalizedSymbol) return null

  const rows = await loadStockMetadata()
  return rows.find((row) => normalizeSearchText(row.symbol) === normalizedSymbol) || null
}
