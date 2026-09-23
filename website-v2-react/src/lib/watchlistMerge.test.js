import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeWatchlistWithMetadata } from './watchlistMerge.js'
import { applyScannerFilters, fieldAvailability } from './scannerFilters.js'
import { sortScannerRows } from './scannerSort.js'

test('Watchlist merge preserves membership order and real metadata', () => {
  const membership = [
    { symbol: 'BBB', added_at: '2026-01-01', add_source: 'USER' },
    { symbol: 'AAA', added_at: '2026-01-02', add_source: 'USER' },
  ]
  const metadata = [
    { symbol: 'AAA', display_name: 'Công ty A', company_name: 'Công ty A đầy đủ', exchange: 'HOSE' },
    { symbol: 'BBB', display_name: 'Công ty B', company_name: 'Công ty B đầy đủ', exchange: 'HNX' },
  ]
  const merged = mergeWatchlistWithMetadata(membership, metadata)
  assert.deepEqual(merged.map((row) => row.symbol), ['BBB', 'AAA'])
  assert.equal(merged[0].display_name, 'Công ty B')
  assert.equal(merged[1].exchange, 'HOSE')
  assert.equal(merged[0].price, undefined)
})

test('Watchlist symbol remains visible when public metadata is absent', () => {
  const merged = mergeWatchlistWithMetadata([{ symbol: ' xyz ', added_at: '2026-01-01' }], [])
  assert.equal(merged[0].symbol, 'XYZ')
  assert.equal(merged[0].exchange, null)
  assert.equal(merged[0].company_name, null)
})

test('shared exchange filter and symbol/exchange sorts work on merged Watchlist', () => {
  const membership = [{ symbol: 'CCC' }, { symbol: 'AAA' }, { symbol: 'BBB' }]
  const metadata = [
    { symbol: 'AAA', exchange: 'HOSE' },
    { symbol: 'BBB', exchange: 'HNX' },
    { symbol: 'CCC', exchange: 'HOSE' },
  ]
  const rows = mergeWatchlistWithMetadata(membership, metadata)
  const availability = fieldAvailability(rows)
  assert.equal(availability.exchange, true)
  assert.equal(availability.price, false)
  const filtered = applyScannerFilters(rows, [{ field: 'exchange', values: ['HOSE'] }], availability)
  assert.deepEqual(filtered.map((row) => row.symbol), ['CCC', 'AAA'])
  assert.deepEqual(sortScannerRows(filtered, [{ field: 'symbol', direction: 'asc' }], availability).map((row) => row.symbol), ['AAA', 'CCC'])
  assert.deepEqual(sortScannerRows(rows, [{ field: 'exchange', direction: 'asc' }, { field: 'symbol', direction: 'asc' }], availability).map((row) => row.symbol), ['BBB', 'AAA', 'CCC'])
})
