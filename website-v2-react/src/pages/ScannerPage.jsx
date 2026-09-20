import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import ScannerResults from '../components/scanner/ScannerResults'
import ScannerShell from '../components/scanner/ScannerShell'
import ScannerTabs from '../components/scanner/ScannerTabs'
import { publicSupabase } from '../lib/publicSupabase'
import { fetchScanner } from '../lib/cccApi'
import { activeConditions, applyScannerFilters, categoryOptions, describeCondition, fieldAvailability } from '../lib/scannerFilters'
import { mergeScannerRows, normalizeScannerResponse } from '../lib/scannerData'
import { activeSortRules, describeSortRule, sortScannerRows } from '../lib/scannerSort'
import { loadStockMetadata, normalizeSearchText } from '../lib/stockSearch'
import { loadMyWatchlist } from '../lib/watchlistData'
import { mergeWatchlistWithMetadata } from '../lib/watchlistMerge'
import '../styles/scanner.css'

const PAGE_SIZE = 50
const SCANNER_REFRESH_MS = 60_000
// Browser-memory capability check; a reload permits a fresh probe of a newer VPS.
let scannerCapabilityUnavailable = false

export default function ScannerPage() {
  const auth = useAuth()
  const authScope = !auth.ready ? 'pending' : auth.user?.id ? `user:${auth.user.id}` : 'signed-out'
  return <ScannerPageContent key={authScope} auth={auth} />
}

function ScannerPageContent({ auth }) {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const lookupUnavailable = params.get('lookup') === 'unavailable'
  const [tabState, setTabState] = useState(() => ({ query: q, value: q ? 'market' : 'watchlist' }))
  const activeTab = tabState.query === q ? tabState.value : q ? 'market' : 'watchlist'
  const [pageState, setPageState] = useState(() => ({ query: q, value: 1 }))
  const page = pageState.query === q ? pageState.value : 1
  const [metadata, setMetadata] = useState(() => ({ status: publicSupabase ? 'loading' : 'error', rows: [] }))
  const [watchlist, setWatchlist] = useState(() => ({ status: auth.ready && auth.user ? 'loading' : 'idle', rows: [] }))
  const [scanner, setScanner] = useState(() => ({ status: scannerCapabilityUnavailable ? 'unavailable' : 'idle', technicalScope: null, rows: [] }))
  const [conditions, setConditions] = useState([])
  const [sortRules, setSortRules] = useState([])
  const [utilityTab, setUtilityTab] = useState('ai')
  const nextRuleId = useRef(0)
  const { user, ready, accessToken } = auth

  useEffect(() => {
    let active = true
    if (!publicSupabase) return undefined
    loadStockMetadata()
      .then((rows) => { if (active) setMetadata({ status: 'ready', rows }) })
      .catch(() => { if (active) setMetadata({ status: 'error', rows: [] }) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!ready || !user?.id) return undefined
    let active = true
    loadMyWatchlist(user.id)
      .then((rows) => {
        if (active) setWatchlist(rows === null ? { status: 'error', rows: [] } : { status: 'ready', rows })
      })
      .catch(() => { if (active) setWatchlist({ status: 'error', rows: [] }) })
    return () => { active = false }
  }, [ready, user?.id])

  useEffect(() => {
    if (!ready || (user && !accessToken) || scannerCapabilityUnavailable) return undefined
    let active = true
    let inFlight = false
    let rerun = false
    let controller = null
    let timer = null
    const canLoad = () => document.visibilityState === 'visible' && navigator.onLine
    const clearTimer = () => { if (timer !== null) clearTimeout(timer); timer = null }
    const run = () => {
      clearTimer()
      if (!active || scannerCapabilityUnavailable || !canLoad()) return
      if (inFlight) {
        rerun = true
        controller?.abort()
        return
      }
      inFlight = true
      controller = new AbortController()
      fetchScanner({ token: accessToken || undefined, signal: controller.signal })
        .then((response) => {
          if (!active || controller?.signal.aborted) return
          const data = normalizeScannerResponse(response)
          setScanner({ status: 'ready', ...data })
        })
        .catch((error) => {
          if (!active || controller?.signal.aborted) return
          if (error?.status === 404) {
            scannerCapabilityUnavailable = true
            setScanner({ status: 'unavailable', technicalScope: null, rows: [] })
          } else if (error?.status === 401 || error?.status === 403) {
            setScanner({ status: 'error', technicalScope: null, rows: [] })
          } else {
            setScanner((current) => ({ ...current, status: 'error' }))
          }
        })
        .finally(() => {
          inFlight = false
          controller = null
          if (!active || scannerCapabilityUnavailable || !canLoad()) return
          if (rerun) {
            rerun = false
            run()
          } else {
            timer = setTimeout(run, SCANNER_REFRESH_MS)
          }
        })
    }
    const onActivity = () => {
      clearTimer()
      if (canLoad()) run()
      else controller?.abort()
    }
    document.addEventListener('visibilitychange', onActivity)
    window.addEventListener('online', onActivity)
    window.addEventListener('offline', onActivity)
    run()
    return () => {
      active = false
      clearTimer()
      controller?.abort()
      document.removeEventListener('visibilitychange', onActivity)
      window.removeEventListener('online', onActivity)
      window.removeEventListener('offline', onActivity)
    }
  }, [ready, user, accessToken])

  const directoryRows = useMemo(() => mergeScannerRows(metadata.rows, scanner.rows), [metadata.rows, scanner.rows])
  const directoryStatus = directoryRows.length ? 'ready' : metadata.status

  const matchingRows = useMemo(() => {
    if (!q) return directoryRows
    const query = normalizeSearchText(q)
    return directoryRows.filter((stock) => [stock.symbol, stock.display_name, stock.company_name]
      .some((value) => normalizeSearchText(value).includes(query)))
  }, [directoryRows, q])
  const watchlistRows = useMemo(() => mergeScannerRows(mergeWatchlistWithMetadata(watchlist.rows, metadata.rows), scanner.rows, { includeScannerOnly: false }), [watchlist.rows, metadata.rows, scanner.rows])
  const sourceRows = activeTab === 'watchlist' ? watchlistRows : matchingRows
  const availability = useMemo(() => fieldAvailability(activeTab === 'watchlist' ? watchlistRows : directoryRows), [activeTab, watchlistRows, directoryRows])
  const options = useMemo(() => categoryOptions(activeTab === 'watchlist' ? watchlistRows : directoryRows), [activeTab, watchlistRows, directoryRows])
  const appliedConditions = activeConditions(conditions, availability)
  const appliedSorts = activeSortRules(sortRules, availability)
  const resultRows = sortScannerRows(applyScannerFilters(sourceRows, conditions, availability), sortRules, availability)
  const pageCount = Math.max(1, Math.ceil(resultRows.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const pageRows = resultRows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const filterSummary = appliedConditions.length ? appliedConditions.map(describeCondition).join(' · ') : 'Chưa áp dụng bộ lọc'
  const summary = activeTab === 'watchlist'
    ? watchlist.status === 'ready'
      ? `${appliedConditions.length ? `${resultRows.length} / ${watchlistRows.length} mã phù hợp` : `${watchlistRows.length} mã theo dõi`} · ${filterSummary}`
      : `${!ready ? 'Đang kiểm tra tài khoản' : !user ? 'Đăng nhập để xem danh sách theo dõi' : watchlist.status === 'loading' ? 'Đang tải danh sách theo dõi' : 'Danh sách theo dõi chưa sẵn sàng'} · ${filterSummary}`
    : directoryStatus !== 'ready'
      ? `${directoryStatus === 'loading' ? 'Đang tải danh mục' : 'Danh mục chưa sẵn sàng'} · ${filterSummary}`
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
    : !user
      ? 'Đăng nhập để xem danh sách cổ phiếu đã theo dõi.'
      : watchlist.status === 'loading'
        ? 'Đang tải danh sách theo dõi…'
        : watchlist.status === 'error'
          ? 'Không thể tải danh sách theo dõi. Hãy thử lại sau.'
          : !watchlistRows.length
            ? 'Bạn chưa có mã nào trong danh sách theo dõi.'
            : 'Không có mã theo dõi phù hợp với các điều kiện đang áp dụng.'

  return (
    <ScannerShell mode={activeTab} filterBuilder={filterBuilder} sortBuilder={sortBuilder} utility={utility}>
      <div className="scanner-heading">
        <span className="scanner-kicker">SCANNER / DANH SÁCH</span>
        <h1>Danh sách cổ phiếu</h1>
      </div>
      <ScannerTabs activeTab={activeTab} onChange={changeTab} />

      <ScannerResults
        mode={activeTab} rows={pageRows} total={matchingRows.length} summary={summary} sortSummary={sortSummary}
        metadataStatus={directoryStatus} q={q} lookupUnavailable={lookupUnavailable}
        watchlistMessage={watchlistMessage} watchlistStatus={watchlist.status} signedOut={!user && ready}
        page={currentPage} pageCount={pageCount} onPage={(value) => setPageState({ query: q, value })}
        filterBuilder={filterBuilder} sortBuilder={sortBuilder} activeCount={appliedConditions.length + appliedSorts.length} utility={utility}
      />
    </ScannerShell>
  )
}
