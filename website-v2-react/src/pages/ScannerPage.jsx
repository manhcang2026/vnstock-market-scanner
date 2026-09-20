import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import ScannerResults from '../components/scanner/ScannerResults'
import ScannerShell from '../components/scanner/ScannerShell'
import ScannerTabs from '../components/scanner/ScannerTabs'
import { publicSupabase } from '../lib/publicSupabase'
import { activeConditions, applyScannerFilters, categoryOptions, describeCondition, fieldAvailability } from '../lib/scannerFilters'
import { activeSortRules, describeSortRule, sortScannerRows } from '../lib/scannerSort'
import { loadStockMetadata, normalizeSearchText } from '../lib/stockSearch'
import '../styles/scanner.css'

const PAGE_SIZE = 50

export default function ScannerPage() {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const lookupUnavailable = params.get('lookup') === 'unavailable'
  const [tabState, setTabState] = useState(() => ({ query: q, value: q ? 'market' : 'watchlist' }))
  const activeTab = tabState.query === q ? tabState.value : q ? 'market' : 'watchlist'
  const [pageState, setPageState] = useState(() => ({ query: q, value: 1 }))
  const page = pageState.query === q ? pageState.value : 1
  const [metadata, setMetadata] = useState(() => ({ status: publicSupabase ? 'loading' : 'error', rows: [] }))
  const [conditions, setConditions] = useState([])
  const [sortRules, setSortRules] = useState([])
  const [utilityTab, setUtilityTab] = useState('ai')
  const nextRuleId = useRef(0)
  const { user, ready } = useAuth()

  useEffect(() => {
    let active = true
    if (!publicSupabase) return undefined
    loadStockMetadata()
      .then((rows) => { if (active) setMetadata({ status: 'ready', rows }) })
      .catch(() => { if (active) setMetadata({ status: 'error', rows: [] }) })
    return () => { active = false }
  }, [])

  const matchingRows = useMemo(() => {
    if (!q) return metadata.rows
    const query = normalizeSearchText(q)
    return metadata.rows.filter((stock) => [stock.symbol, stock.display_name, stock.company_name]
      .some((value) => normalizeSearchText(value).includes(query)))
  }, [metadata.rows, q])
  const sourceRows = activeTab === 'watchlist' ? [] : matchingRows
  const availability = useMemo(() => fieldAvailability(activeTab === 'watchlist' ? [] : metadata.rows), [activeTab, metadata.rows])
  const options = useMemo(() => categoryOptions(activeTab === 'watchlist' ? [] : metadata.rows), [activeTab, metadata.rows])
  const appliedConditions = activeConditions(conditions, availability)
  const appliedSorts = activeSortRules(sortRules, availability)
  const resultRows = sortScannerRows(applyScannerFilters(sourceRows, conditions, availability), sortRules, availability)
  const pageCount = Math.max(1, Math.ceil(resultRows.length / PAGE_SIZE))
  const pageRows = resultRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const filterSummary = appliedConditions.length ? appliedConditions.map(describeCondition).join(' · ') : 'Chưa áp dụng bộ lọc'
  const summary = activeTab === 'watchlist'
    ? `Danh sách theo dõi chưa kết nối · ${filterSummary}`
    : metadata.status !== 'ready'
      ? `${metadata.status === 'loading' ? 'Đang tải danh mục' : 'Danh mục chưa sẵn sàng'} · ${filterSummary}`
      : `${resultRows.length} mã${appliedConditions.length ? ' phù hợp' : ''} · ${filterSummary} · ${pageRows.length} mã trên trang này`
  const sortSummary = appliedSorts.map(describeSortRule).join(' → ')

  function resetPage() { setPageState({ query: q, value: 1 }) }

  function changeTab(tab) {
    setTabState({ query: q, value: tab })
    resetPage()
  }

  function addCondition() {
    nextRuleId.current += 1
    setConditions((items) => [...items, { id: nextRuleId.current, field: 'exchange', values: [], operator: 'lte', value: '', valueTo: '' }])
    resetPage()
  }
  function updateCondition(id, patch) {
    setConditions((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item))
    resetPage()
  }
  function removeCondition(id) {
    setConditions((items) => items.filter((item) => item.id !== id))
    resetPage()
  }
  function addSort() {
    nextRuleId.current += 1
    setSortRules((items) => [...items, { id: nextRuleId.current, field: 'symbol', direction: 'asc' }])
    resetPage()
  }
  function updateSort(id, patch) {
    setSortRules((items) => items.map((item) => item.id === id ? { ...item, ...patch } : item))
    resetPage()
  }
  function removeSort(id) {
    setSortRules((items) => items.filter((item) => item.id !== id))
    resetPage()
  }
  function moveSort(index, direction) {
    setSortRules((items) => {
      const next = [...items]
      const other = index + direction
      if (other < 0 || other >= next.length) return items
      const current = next[index]
      next[index] = next[other]
      next[other] = current
      return next
    })
    resetPage()
  }

  const filterBuilder = { conditions, availability, options, onAdd: addCondition, onUpdate: updateCondition, onRemove: removeCondition }
  const sortBuilder = { rules: sortRules, availability, onAdd: addSort, onUpdate: updateSort, onRemove: removeSort, onMove: moveSort }
  const utility = { active: utilityTab, onChange: setUtilityTab }

  const watchlistMessage = !ready
    ? 'Đang kiểm tra tài khoản…'
    : user
      ? 'Chưa thể tải danh sách theo dõi: frontend hiện chưa có đường đọc Watchlist được xác nhận.'
      : 'Đăng nhập để xem danh sách cổ phiếu đã theo dõi.'

  return (
    <ScannerShell mode={activeTab} filterBuilder={filterBuilder} sortBuilder={sortBuilder} utility={utility}>
      <div className="scanner-heading">
        <span className="scanner-kicker">SCANNER / DANH SÁCH</span>
        <h1>Danh sách cổ phiếu</h1>
      </div>
      <ScannerTabs activeTab={activeTab} onChange={changeTab} />

      <ScannerResults
        mode={activeTab} rows={pageRows} total={matchingRows.length} summary={summary} sortSummary={sortSummary}
        metadataStatus={metadata.status} q={q} lookupUnavailable={lookupUnavailable}
        watchlistMessage={watchlistMessage} signedOut={!user && ready}
        page={page} pageCount={pageCount} onPage={(value) => setPageState({ query: q, value })}
        filterBuilder={filterBuilder} sortBuilder={sortBuilder} activeCount={appliedConditions.length + appliedSorts.length} utility={utility}
      />
    </ScannerShell>
  )
}
