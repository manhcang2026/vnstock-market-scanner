import test from 'node:test'
import assert from 'node:assert/strict'
import {
  activeConditions, applyScannerFilters, fieldAvailability, formatSignedPct,
  nearMaDistancePct, signedMaDistancePct,
} from './scannerFilters.js'
import { sortScannerRows } from './scannerSort.js'

test('MA distance remains signed for display and absolute for proximity', () => {
  assert.equal(signedMaDistancePct(101, 100), 1)
  assert.equal(signedMaDistancePct(99, 100), -1)
  assert.equal(nearMaDistancePct(101, 100), 1)
  assert.equal(nearMaDistancePct(99, 100), 1)
  assert.equal(formatSignedPct(signedMaDistancePct(101.2, 100)), '+1.2%')
  assert.equal(formatSignedPct(signedMaDistancePct(98.8, 100)), '-1.2%')
})

test('missing price or MA is unavailable, never zero', () => {
  assert.equal(signedMaDistancePct(null, 100), null)
  assert.equal(signedMaDistancePct(100, undefined), null)
  assert.equal(signedMaDistancePct(100, 0), null)
  assert.equal(nearMaDistancePct('', 100), null)
})

test('different conditions use AND; selections within one condition use OR', () => {
  const rows = [
    { symbol: 'A', exchange: 'HOSE', industry: 'Thép' },
    { symbol: 'B', exchange: 'HNX', industry: 'Thép' },
    { symbol: 'C', exchange: 'HOSE', industry: 'Ngân hàng' },
    { symbol: 'D', exchange: 'UPCOM', industry: 'Thép' },
  ]
  const conditions = [
    { field: 'exchange', values: ['HOSE', 'HNX'] },
    { field: 'industry', values: ['Thép'] },
  ]
  assert.deepEqual(applyScannerFilters(rows, conditions, fieldAvailability(rows)).map((row) => row.symbol), ['A', 'B'])
})

test('near MA filter uses absolute distance; MA position stays separate', () => {
  const rows = [
    { symbol: 'ABOVE', price: 101, ma200: 100 },
    { symbol: 'BELOW', price: 99, ma200: 100 },
    { symbol: 'FAR', price: 105, ma200: 100 },
  ]
  const availability = fieldAvailability(rows)
  assert.deepEqual(applyScannerFilters(rows, [{ field: 'nearMa200', operator: 'lte', value: '3' }], availability).map((row) => row.symbol), ['ABOVE', 'BELOW'])
  assert.deepEqual(applyScannerFilters(rows, [{ field: 'positionMa200', values: ['above'] }], availability).map((row) => row.symbol), ['ABOVE', 'FAR'])
})

test('unavailable conditions are inactive and do not imply no matches', () => {
  const rows = [{ symbol: 'A', exchange: 'HOSE' }, { symbol: 'B', exchange: 'HNX' }]
  const condition = { field: 'nearMa200', operator: 'lte', value: '3' }
  const availability = fieldAvailability(rows)
  assert.equal(availability.nearMa200, false)
  assert.deepEqual(activeConditions([condition], availability), [])
  assert.deepEqual(applyScannerFilters(rows, [condition], availability), rows)
})

test('invalid negative proximity cannot produce a misleading empty result', () => {
  const rows = [{ symbol: 'A', price: 101, ma200: 100 }]
  assert.deepEqual(applyScannerFilters(rows, [{ field: 'nearMa200', operator: 'lte', value: '-3' }], fieldAvailability(rows)), rows)
})

test('multi-sort respects priority, tie-breaks, and missing values', () => {
  const rows = [
    { symbol: 'A', distanceMa200Pct: -1, volume: 100, changePct: 2 },
    { symbol: 'B', distanceMa200Pct: 1, volume: 200, changePct: 3 },
    { symbol: 'C', distanceMa200Pct: 1, volume: 200, changePct: 1 },
    { symbol: 'D', distanceMa200Pct: 5, volume: 900, changePct: 0 },
    { symbol: 'E', distanceMa200Pct: null, volume: 999, changePct: -1 },
  ]
  const rules = [
    { field: 'nearMa200', direction: 'asc' },
    { field: 'volume', direction: 'desc' },
    { field: 'changePct', direction: 'asc' },
  ]
  assert.deepEqual(sortScannerRows(rows, rules, fieldAvailability(rows)).map((row) => row.symbol), ['C', 'B', 'A', 'D', 'E'])
  assert.deepEqual(sortScannerRows(rows, [{ field: 'nearMa200', direction: 'desc' }], fieldAvailability(rows)).map((row) => row.symbol), ['D', 'A', 'B', 'C', 'E'])
})
