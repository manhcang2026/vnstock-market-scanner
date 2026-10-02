import test from 'node:test'
import assert from 'node:assert/strict'
import { applyScannerFilters, fieldAvailability, signedDistanceForRow } from './scannerFilters.js'
import { sortScannerRows } from './scannerSort.js'
import {
  mergeScannerRows, normalizeScannerResponse, normalizeScannerRow,
  scannerStateCue,
} from './scannerData.js'
import { cccDirectionLabel, cccStatePresentation, cccStateSignature, isStatePresentationDegraded, meterSignalLevel, validSignalLevel } from './cccState.js'
import { mergeWatchlistWithMetadata } from './watchlistMerge.js'

const publicRow = {
  symbol: ' aaa ', exchange: 'HOSE', trading_date: '2026-09-18',
  event_at: '2026-09-18T10:30:00+07:00', last_price: 101.25,
  ref_price: 100, change_pct: 1.25, total_volume: 12_400,
  session_type: 'CONTINUOUS', ma10: 100, ma200: 98,
  distance_ma10_pct: -2.5, distance_ma200_pct: 3.32,
  feed_status: 'DEGRADED', quality_status: 'PARTIAL', ccc: null,
}

test('normalizes public fields and retains direct signed MA distances', () => {
  const row = normalizeScannerRow(publicRow)
  assert.equal(row.symbol, 'AAA')
  assert.equal(row.exchange, 'HOSE')
  assert.equal(row.price, 101.25)
  assert.equal(row.refPrice, 100)
  assert.equal(row.changePct, 1.25)
  assert.equal(row.volume, 12_400)
  assert.equal(row.ma10, 100)
  assert.equal(row.ma200, 98)
  assert.equal(row.tradingDate, '2026-09-18')
  assert.equal(row.eventAt, publicRow.event_at)
  assert.equal(row.sessionType, 'CONTINUOUS')
  assert.equal(row.feedStatus, 'DEGRADED')
  assert.equal(row.qualityStatus, 'PARTIAL')
  assert.equal(signedDistanceForRow(row, 10), -2.5)
  assert.equal(signedDistanceForRow(row, 200), 3.32)
})

test('null CCC exposes no protected normalized values or signal', () => {
  const row = normalizeScannerRow({ ...publicRow, signal_summary_vi: 'outside CCC', ccc: null })
  assert.equal(row.ccc, null)
  for (const field of [
    'dayRvol', 'rvol15', 'rvol30', 'price5', 'price15', 'atoRvol',
    'atcRvol', 'atcPriceImpactPct', 'signalState', 'signalLevel',
    'signalDirection', 'reasonCodes', 'signalSummary', 'metricsTrusted',
  ]) assert.equal(row[field], null, field)
  assert.equal(scannerStateCue({ ...row, signalSummary: 'forged', signalState: 'WATCHING' }), null)
  assert.equal(normalizeScannerRow({ ...publicRow, ccc: [] }).ccc, null)
})

test('authorized CCC fields normalize only from a real object', () => {
  const row = normalizeScannerRow({
    ...publicRow,
    ccc: {
      day_rvol: 1.2, rvol15: 1.3, rvol30: 1.8,
      price5_pct: -0.2, price15_pct: 0.4, ato_rvol: 1.1,
      atc_rvol: 1.7, atc_price_impact_pct: -1.2,
      signal_state: 'WATCHING', signal_level: 2,
      signal_direction: 'UP', reason_codes: ['REAL_REASON'],
      signal_summary_vi: 'Theo dõi dòng tiền', metrics_trusted: false,
    },
  })
  assert.ok(row.ccc)
  assert.deepEqual([row.dayRvol, row.rvol15, row.rvol30, row.price5, row.price15], [1.2, 1.3, 1.8, -0.2, 0.4])
  assert.deepEqual([row.atoRvol, row.atcRvol, row.atcPriceImpactPct], [1.1, 1.7, -1.2])
  assert.deepEqual([row.signalState, row.signalLevel, row.signalDirection], ['WATCHING', 2, 'UP'])
  assert.deepEqual(row.reasonCodes, ['REAL_REASON'])
  assert.equal(row.metricsTrusted, false)
  assert.equal(scannerStateCue(row), 'Theo dõi')
  assert.equal(scannerStateCue({ ...row, signalState: 'NORMAL' }), 'Bình thường')
  assert.equal(scannerStateCue({ ...row, signalSummary: 'x'.repeat(60) }), 'Theo dõi')
})

test('canonical state labels and meter levels never derive from metrics or state', () => {
  assert.deepEqual([
    'NORMAL', 'WATCHING', 'FLOW_APPEARING', 'FLOW_PRICE_CONFIRMED',
    'MOMENTUM_MAINTAINED', 'MOMENTUM_WEAKENING', 'SELLING_PRESSURE',
  ].map(state => cccStatePresentation(state).label), [
    'Bình thường', 'Theo dõi', 'Dòng tiền xuất hiện', 'Dòng tiền + giá xác nhận',
    'Động lượng duy trì', 'Động lượng suy yếu', 'Áp lực bán',
  ])
  assert.deepEqual(cccStatePresentation('UNKNOWN_STATE'), { label: 'UNKNOWN_STATE', tone: 'neutral' })
  assert.equal(validSignalLevel(null), null)
  assert.equal(meterSignalLevel(null), null)
  assert.equal(meterSignalLevel('not-a-level'), null)
  assert.equal(meterSignalLevel(3), 3)
  assert.equal(validSignalLevel(8), 8)
  assert.equal(meterSignalLevel(8), 4)
  assert.equal(cccStateSignature(null, 3), null)
  assert.equal(cccStateSignature(' watching ', 1), 'WATCHING|1')
  assert.equal(cccStateSignature('WATCHING', null), 'WATCHING|unknown')
  assert.notEqual(cccStateSignature('WATCHING', 1), cccStateSignature('WATCHING', 2))
  assert.notEqual(cccStateSignature('WATCHING', 1), cccStateSignature('SELLING_PRESSURE', 1))
  assert.equal(isStatePresentationDegraded({ qualityStatus: 'METRICS_UNTRUSTED' }), true)
  assert.equal(isStatePresentationDegraded({ metricsTrusted: false }), true)
})

test('CCC direction labels expose only canonical Vietnamese wording', () => {
  assert.equal(cccDirectionLabel('NEUTRAL'), 'Trung tính')
  assert.equal(cccDirectionLabel(' bullish '), 'Hướng tăng')
  assert.equal(cccDirectionLabel('BEARISH'), 'Hướng giảm')
  assert.equal(cccDirectionLabel('UNKNOWN_DIRECTION'), '—')
  assert.equal(cccDirectionLabel(null), '—')
})

test('response stores technical scope only as metadata', () => {
  const response = normalizeScannerResponse({
    contract_version: 'ccc-scanner-v1', technical_scope: 'FULL_MARKET',
    count: 1, rows: [publicRow],
  })
  assert.equal(response.technicalScope, 'FULL_MARKET')
  assert.equal(response.rows[0].ccc, null)
})

test('directory remains the base; missing state is null; state-only symbol stays usable', () => {
  const directory = [
    { symbol: 'AAA', display_name: 'Công ty A', exchange: 'HOSE' },
    { symbol: 'BBB', company_name: 'Công ty B', exchange: 'HNX' },
  ]
  const rows = mergeScannerRows(directory, [normalizeScannerRow(publicRow), normalizeScannerRow({ ...publicRow, symbol: 'CCC', exchange: 'UPCOM' })])
  assert.deepEqual(rows.map((row) => row.symbol), ['AAA', 'BBB', 'CCC'])
  assert.equal(rows[0].display_name, 'Công ty A')
  assert.equal(rows[0].price, 101.25)
  assert.equal(rows[1].price, null)
  assert.equal(rows[1].distanceMa200Pct, null)
  assert.equal(rows[1].ccc, null)
  assert.equal(rows[2].display_name, null)
  assert.equal(rows[2].exchange, 'UPCOM')
  assert.equal(rows[2].price, 101.25)
})

test('Watchlist membership and order merge with the same bulk rows', () => {
  const membership = [{ symbol: 'BBB' }, { symbol: 'AAA' }]
  const directory = [{ symbol: 'AAA', display_name: 'Công ty A', exchange: 'HOSE' }]
  const identities = mergeWatchlistWithMetadata(membership, directory)
  const rows = mergeScannerRows(identities, [normalizeScannerRow(publicRow)], { includeScannerOnly: false })
  assert.deepEqual(rows.map((row) => row.symbol), ['BBB', 'AAA'])
  assert.equal(rows[0].price, null)
  assert.equal(rows[1].price, 101.25)
  assert.equal(rows[1].display_name, 'Công ty A')
})

test('backend signed distance drives near MA filtering and sorting', () => {
  const rows = [
    normalizeScannerRow({ ...publicRow, symbol: 'AAA', distance_ma10_pct: -2.5 }),
    normalizeScannerRow({ ...publicRow, symbol: 'BBB', distance_ma10_pct: 0.5 }),
    normalizeScannerRow({ ...publicRow, symbol: 'CCC', distance_ma10_pct: null, ma10: null }),
  ]
  const availability = fieldAvailability(rows)
  assert.deepEqual(applyScannerFilters(rows, [{ field: 'nearMa10', operator: 'lte', value: '1' }], availability).map((row) => row.symbol), ['BBB'])
  assert.deepEqual(applyScannerFilters(rows, [{ field: 'positionMa10', values: ['below'] }], availability).map((row) => row.symbol), ['AAA'])
  assert.deepEqual(sortScannerRows(rows, [{ field: 'nearMa10', direction: 'asc' }], availability).map((row) => row.symbol), ['BBB', 'AAA', 'CCC'])
})

test('missing numeric API values remain null rather than zero', () => {
  const row = normalizeScannerRow({ symbol: 'DDD', last_price: null, total_volume: '', ccc: { rvol30: null } })
  assert.equal(row.price, null)
  assert.equal(row.volume, null)
  assert.equal(row.changePct, null)
  assert.equal(row.rvol30, null)
  assert.equal(row.metricsTrusted, null)
})
