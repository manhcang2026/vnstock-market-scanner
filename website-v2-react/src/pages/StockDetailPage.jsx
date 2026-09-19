import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  fetchCccIntelligence,
  fetchChart,
  fetchPublicStockContext,
  fetchQuote,
  fetchRadar,
  fetchTechnicalAccess,
} from '../lib/cccApi'
import { fetchFinancialContext, fetchQuarterlyFinancials } from '../lib/financialData'
import { findStockMetadataBySymbol } from '../lib/stockSearch'
import StockDetailV3View from '../components/stock/StockDetailV3View'
import '../styles/stock-detail.css'

const TradingChart = lazy(() => import('../components/stock/TradingChart'))

const SYMBOL_RE = /^[A-Z0-9]{2,12}$/
const ALLOWED_RESOLUTIONS = new Set([5, 15, 30, 60, 1440])

// CCC_LAZY_HISTORY_V2
const LOOKBACK_DAYS = {
  5: 7,
  15: 30,
  30: 60,
  60: 120,
  1440: 730,
}

const HISTORY_FLOOR = '2026-01-05'

const HISTORY_EXPAND_DAYS = {
  5: 30,
  15: 60,
  30: 90,
  60: 120,
  1440: 365,
}

function subtractDays(dateText, days) {
  const [year, month, day] = dateText.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCDate(date.getUTCDate() - days)
  return date.toISOString().slice(0, 10)
}

function daysBetween(fromDate, toDate) {
  const from = new Date(`${fromDate}T00:00:00Z`)
  const to = new Date(`${toDate}T00:00:00Z`)
  return Math.max(0, Math.ceil((to - from) / 86_400_000))
}

const CHART_CACHE_TTL_MS = 30_000
const CHART_CACHE_MAX = 100
const BACKGROUND_REFRESH_MS = 30_000
const LIVE_RECONNECT_DELAYS_MS = [2_000, 4_000, 8_000, 16_000, 30_000]
const chartResponseCache = new Map()
const chartRequestCache = new Map()
let nextChartAuthScope = 0

function getCachedChart(key) {
  const item = chartResponseCache.get(key)
  if (!item) return null
  if (Date.now() - item.savedAt > CHART_CACHE_TTL_MS) {
    chartResponseCache.delete(key)
    return null
  }
  return item.data
}

function putCachedChart(key, data) {
  if (chartResponseCache.size >= CHART_CACHE_MAX) {
    const firstKey = chartResponseCache.keys().next().value
    if (firstKey) chartResponseCache.delete(firstKey)
  }
  chartResponseCache.set(key, { data, savedAt: Date.now() })
}

function chartRequestFor(
  symbol,
  chartDate,
  resolution,
  lookbackDays = LOOKBACK_DAYS[resolution] ?? 30,
) {
  const chartFrom = subtractDays(chartDate, lookbackDays)
  const key = `${symbol}:${chartFrom}:${chartDate}:${resolution}`
  const query = `from=${encodeURIComponent(chartFrom)}&to=${encodeURIComponent(chartDate)}&resolution=${resolution}`
  return { key, query, chartFrom }
}

function loadChartCached({ key, symbol, query, token }) {
  const cached = getCachedChart(key)
  if (cached) return Promise.resolve(cached)

  const inFlight = chartRequestCache.get(key)
  if (inFlight) return inFlight

  const request = fetchChart(symbol, query, { token })
    .then((data) => {
      putCachedChart(key, data)
      return data
    })
    .finally(() => {
      chartRequestCache.delete(key)
    })

  chartRequestCache.set(key, request)
  return request
}

function normalizeSymbol(value) {
  return String(value || '').trim().toUpperCase()
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value))
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${formatNumber(n, 2)}%`
}

function abortError(error) {
  return error?.name === 'AbortError'
}

function chartFailure(error, token) {
  if (error?.status === 401) return {
    message: token
      ? 'Phiên đăng nhập không còn hợp lệ. Hãy đăng nhập lại để xem biểu đồ.'
      : 'Biểu đồ chưa sẵn sàng cho khách trên phiên bản API hiện tại.',
    kind: 'neutral',
  }
  if (error?.status === 403) return {
    message: 'Biểu đồ không nằm trong phạm vi được cấp quyền cho mã này.',
    kind: 'neutral',
  }
  return { message: FRIENDLY_ERRORS.chart, kind: 'error' }
}

const FRIENDLY_ERRORS = {
  quote: 'Giá thị trường tạm thời chưa sẵn sàng.',
  publicContext: 'Bối cảnh MA tạm thời chưa sẵn sàng.',
  financial: 'Dữ liệu cơ bản tạm thời chưa sẵn sàng.',
  quarterly: 'Dữ liệu BCTC tạm thời chưa sẵn sàng.',
  access: 'Chưa thể kiểm tra phạm vi CCC Technical.',
  ccc: 'CCC Intelligence tạm thời chưa sẵn sàng.',
  radar: 'CCC Radar tạm thời chưa sẵn sàng.',
  chart: 'Biểu đồ giá tạm thời chưa sẵn sàng.',
}

// CCC_LIVE_WS_REACT_V1
function liveWebSocketUrl() {
  const configured = import.meta.env.VITE_CCC_WS_URL
  if (configured) return configured

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v2/live`
}

export default function StockDetailPage() {
  const params = useParams()
  const symbol = normalizeSymbol(params.symbol)
  const validSymbol = SYMBOL_RE.test(symbol)
  const { user, accessToken, ready } = useAuth()
  // An opaque, in-memory scope prevents cached protected bars crossing auth changes.
  const chartAuthScope = useMemo(() => {
    const kind = accessToken ? (user?.id ? 'member' : 'pending') : 'guest'
    return `${++nextChartAuthScope}-${kind}`
  }, [accessToken, user?.id])

  useEffect(() => {
    chartResponseCache.clear()
    chartRequestCache.clear()
  }, [chartAuthScope])

  const [resolution, setResolution] = useState(5)
  const [activeDetailTab, setActiveDetailTab] = useState('overview')
  const [metadataState, setMetadataState] = useState({ symbol: '', data: null })
  const [quoteState, setQuoteState] = useState({ symbol: '', data: null, error: '' })
  const [publicContextState, setPublicContextState] = useState({ symbol: '', data: null, error: '' })
  const [capabilityUnavailable, setCapabilityUnavailable] = useState({ stockDetail: false, ccc: false, radar: false })
  const [accessState, setAccessState] = useState({ symbol: '', authToken: '', data: null, error: '' })
  const [cccState, setCccState] = useState({ symbol: '', authToken: '', data: null, error: '', status: 0 })
  const [radarState, setRadarState] = useState({ authToken: '', data: null, error: '', status: 0 })
  const [financialState, setFinancialState] = useState({ symbol: '', data: null, error: '' })
  const [quarterlyState, setQuarterlyState] = useState({ symbol: '', data: null, error: '' })
  const [chartState, setChartState] = useState({
    key: '',
    symbol: '',
    resolution: null,
    authScope: 0,
    data: null,
    error: '',
    errorKind: '',
  })
  const [historyDepth, setHistoryDepth] = useState({})
  const [liveState, setLiveState] = useState({
    symbol: '',
    resolution: null,
    authScope: 0,
    candle: null,
    connected: false,
  })

  useEffect(() => {
    if (!validSymbol) return undefined

    let active = true
    findStockMetadataBySymbol(symbol)
      .then((data) => {
        if (active) setMetadataState({ symbol, data })
      })
      .catch(() => {
        if (active) setMetadataState({ symbol, data: null })
      })

    return () => {
      active = false
    }
  }, [symbol, validSymbol])

  useEffect(() => {
    if (!validSymbol) return undefined

    const controller = new AbortController()
    fetchQuote(symbol, { signal: controller.signal })
      .then((data) => setQuoteState({ symbol, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setQuoteState({
          symbol,
          data: null,
          error: FRIENDLY_ERRORS.quote,
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol])

  useEffect(() => {
    if (!validSymbol || capabilityUnavailable.stockDetail) return undefined
    const controller = new AbortController()
    fetchPublicStockContext(symbol, { signal: controller.signal })
      .then((data) => setPublicContextState({ symbol, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        if (error?.status === 404) {
          setCapabilityUnavailable((current) => ({ ...current, stockDetail: true }))
          setPublicContextState({ symbol, data: null, error: '' })
          return
        }
        setPublicContextState({
          symbol,
          data: null,
          error: FRIENDLY_ERRORS.publicContext,
        })
      })
    return () => controller.abort()
  }, [symbol, validSymbol, capabilityUnavailable.stockDetail])

  useEffect(() => {
    if (!validSymbol) return undefined
    let active = true
    Promise.allSettled([
      fetchFinancialContext(symbol),
      fetchQuarterlyFinancials(symbol),
    ]).then(([financialResult, quarterlyResult]) => {
      if (!active) return
      setFinancialState(financialResult.status === 'fulfilled'
        ? { symbol, data: financialResult.value, error: '' }
        : {
            symbol,
            data: null,
            error: FRIENDLY_ERRORS.financial,
          })
      setQuarterlyState(quarterlyResult.status === 'fulfilled'
        ? { symbol, data: quarterlyResult.value, error: '' }
        : {
            symbol,
            data: null,
            error: FRIENDLY_ERRORS.quarterly,
          })
    })
    return () => { active = false }
  }, [symbol, validSymbol])

  useEffect(() => {
    if (!validSymbol || !ready || !accessToken) return undefined

    const controller = new AbortController()
    fetchTechnicalAccess(symbol, { token: accessToken, signal: controller.signal })
      .then((data) => setAccessState({ symbol, authToken: accessToken, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setAccessState({
          symbol,
          authToken: accessToken,
          data: null,
          error: FRIENDLY_ERRORS.access,
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol, ready, accessToken])

  const quote = quoteState.symbol === symbol ? quoteState.data : null
  const quoteError = quoteState.symbol === symbol ? quoteState.error : ''
  const metadata = metadataState.symbol === symbol ? metadataState.data : null
  const metadataLoading = metadataState.symbol !== symbol
  const accessStateIsCurrent = (
    accessState.symbol === symbol
    && accessState.authToken === accessToken
  )
  const fetchedAccess = accessStateIsCurrent ? accessState.data : null
  const accessError = accessStateIsCurrent ? accessState.error : ''

  const access = useMemo(() => {
    if (!ready) return null
    if (!user || !accessToken) {
      return {
        technical_allowed: false,
        reason: 'AUTH_REQUIRED',
        plan_code: null,
      }
    }
    return fetchedAccess
  }, [ready, user, accessToken, fetchedAccess])

  const cccBlockedStatus = cccState.symbol === symbol && cccState.authToken === accessToken
    && [401, 403].includes(cccState.status) ? cccState.status : 0
  const radarBlockedStatus = radarState.authToken === accessToken
    && [401, 403].includes(radarState.status) ? radarState.status : 0

  useEffect(() => {
    if (
      !validSymbol
      || activeDetailTab !== 'technical'
      || !accessToken
      || !access?.technical_allowed
      || capabilityUnavailable.ccc
      || cccBlockedStatus
    ) {
      return undefined
    }

    let active = true
    let controller
    let timer

    const load = () => {
      if (document.visibilityState !== 'visible') return
      controller?.abort()
      controller = new AbortController()
      fetchCccIntelligence(symbol, { token: accessToken, signal: controller.signal })
        .then((data) => {
          if (active) setCccState({ symbol, authToken: accessToken, data, error: '', status: 0 })
        })
        .catch((error) => {
          if (active && !abortError(error)) {
            if (error?.status === 404) {
              setCapabilityUnavailable((current) => ({ ...current, ccc: true }))
              setCccState({ symbol, authToken: accessToken, data: null, error: '', status: 404 })
              stop()
              return
            }
            setCccState((current) => ({
              symbol,
              authToken: accessToken,
              data: ![401, 403].includes(error?.status)
                && current.symbol === symbol && current.authToken === accessToken
                ? current.data
                : null,
              error: error?.status === 401
                ? 'Phiên đăng nhập không còn hợp lệ.'
                : error?.status === 403
                  ? 'Mã này không nằm trong phạm vi CCC được cấp quyền.'
                  : FRIENDLY_ERRORS.ccc,
              status: error?.status || 0,
            }))
            if ([401, 403].includes(error?.status)) stop()
          }
        })
    }

    const stop = () => {
      window.clearInterval(timer)
      timer = undefined
      controller?.abort()
      controller = undefined
    }

    const start = () => {
      if (document.visibilityState !== 'visible') return
      window.clearInterval(timer)
      load()
      timer = window.setInterval(load, BACKGROUND_REFRESH_MS)
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') start()
      else stop()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    start()

    return () => {
      active = false
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      stop()
    }
  }, [
    symbol,
    validSymbol,
    activeDetailTab,
    accessToken,
    access?.technical_allowed,
    capabilityUnavailable.ccc,
    cccBlockedStatus,
  ])

  useEffect(() => {
    if (!ready || capabilityUnavailable.radar || radarBlockedStatus) return undefined

    let active = true
    let controller
    let timer

    const load = () => {
      if (document.visibilityState !== 'visible') return
      controller?.abort()
      controller = new AbortController()
      fetchRadar({ token: accessToken || undefined, signal: controller.signal })
        .then((data) => {
          if (active) setRadarState({ authToken: accessToken, data, error: '', status: 0 })
        })
        .catch((error) => {
          if (active && !abortError(error)) {
            if (error?.status === 404) {
              setCapabilityUnavailable((current) => ({ ...current, radar: true }))
              setRadarState({ authToken: accessToken, data: null, error: '', status: 404 })
              stop()
              return
            }
            setRadarState((current) => ({
              authToken: accessToken,
              data: ![401, 403].includes(error?.status) && current.authToken === accessToken
                ? current.data : null,
              error: [401, 403].includes(error?.status) ? '' : FRIENDLY_ERRORS.radar,
              status: error?.status || 0,
            }))
            if ([401, 403].includes(error?.status)) stop()
          }
        })
    }

    const stop = () => {
      window.clearInterval(timer)
      timer = undefined
      controller?.abort()
      controller = undefined
    }

    const start = () => {
      if (document.visibilityState !== 'visible') return
      window.clearInterval(timer)
      load()
      timer = window.setInterval(load, BACKGROUND_REFRESH_MS)
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') start()
      else stop()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    start()

    return () => {
      active = false
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      stop()
    }
  }, [ready, accessToken, capabilityUnavailable.radar, radarBlockedStatus])

  useEffect(() => {
    if (
      !validSymbol
      || !ALLOWED_RESOLUTIONS.has(resolution)
    ) {
      return undefined
    }

    let socket
    let reconnectTimer
    let retryIndex = 0
    let reconnectImmediately = false
    let closedByEffect = false
    let rejectedByServer = false

    const canConnect = () => (
      !closedByEffect
      && !rejectedByServer
      && document.visibilityState === 'visible'
      && navigator.onLine !== false
    )

    const clearReconnectTimer = () => {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = undefined
    }

    const markDisconnected = () => {
      setLiveState((current) => (
        current.symbol === symbol && current.resolution === resolution
          ? { ...current, connected: false }
          : current
      ))
    }

    const scheduleReconnect = () => {
      if (!canConnect() || reconnectTimer) return
      const delay = LIVE_RECONNECT_DELAYS_MS[
        Math.min(retryIndex, LIVE_RECONNECT_DELAYS_MS.length - 1)
      ]
      retryIndex += 1
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = undefined
        connect()
      }, delay)
    }

    const connect = () => {
      if (!canConnect()) return
      if (
        socket
        && (
          socket.readyState === WebSocket.CONNECTING
          || socket.readyState === WebSocket.OPEN
          || socket.readyState === WebSocket.CLOSING
        )
      ) {
        return
      }

      clearReconnectTimer()
      const currentSocket = new WebSocket(liveWebSocketUrl())
      socket = currentSocket

      currentSocket.onopen = () => {
        if (socket !== currentSocket || !canConnect()) {
          currentSocket.close(1000, 'connection paused')
          return
        }

        retryIndex = 0
        reconnectImmediately = false

        currentSocket.send(JSON.stringify({
          type: 'subscribe',
          channel: 'chart',
          symbol,
          resolution,
          ...(accessToken ? { token: accessToken } : {}),
        }))

        setLiveState({
          symbol,
          resolution,
          authScope: chartAuthScope,
          candle: null,
          connected: true,
        })
      }

      currentSocket.onmessage = (event) => {
        if (socket !== currentSocket || !canConnect()) return

        let snapshot
        try {
          snapshot = JSON.parse(event.data)
        } catch {
          return
        }

        if (
          snapshot?.type !== 'snapshot'
          || snapshot?.symbol !== symbol
          || Number(snapshot?.resolution) !== resolution
        ) {
          return
        }

        if (snapshot.quote) {
          setQuoteState({
            symbol,
            data: snapshot.quote,
            error: '',
          })
        }

        setLiveState({
          symbol,
          resolution,
          authScope: chartAuthScope,
          candle: snapshot.candle || null,
          connected: true,
        })
      }

      currentSocket.onclose = (event) => {
        if (socket !== currentSocket) return
        socket = undefined
        markDisconnected()
        if (closedByEffect) return
        if (event.code === 4401 || event.code === 4403) {
          rejectedByServer = true
          clearReconnectTimer()
          return
        }

        if (reconnectImmediately && canConnect()) {
          reconnectImmediately = false
          connect()
        } else {
          scheduleReconnect()
        }
      }

      currentSocket.onerror = () => {
        // onclose handles reconnects; keep console noise out of the product UI.
      }
    }

    const pauseConnection = (reason) => {
      reconnectImmediately = false
      clearReconnectTimer()
      markDisconnected()
      if (
        socket
        && socket.readyState !== WebSocket.CLOSED
        && socket.readyState !== WebSocket.CLOSING
      ) {
        socket.close(1000, reason)
      }
    }

    const resumeConnection = () => {
      if (!canConnect()) return
      clearReconnectTimer()
      if (socket?.readyState === WebSocket.CLOSING) {
        reconnectImmediately = true
        return
      }
      connect()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') resumeConnection()
      else pauseConnection('page hidden')
    }

    const handleOnline = () => resumeConnection()
    const handleOffline = () => pauseConnection('browser offline')

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    resumeConnection()

    return () => {
      closedByEffect = true
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      clearReconnectTimer()
      socket?.close(1000, 'route change')
    }
  }, [
    symbol,
    validSymbol,
    resolution,
    accessToken,
    chartAuthScope,
  ])

  const liveCandle = (
    liveState.symbol === symbol
    && liveState.resolution === resolution
    && liveState.authScope === chartAuthScope
  ) ? liveState.candle : null

  const liveConnected = Boolean(
    liveState.connected
    && liveState.symbol === symbol
    && liveState.resolution === resolution
    && liveState.authScope === chartAuthScope
  )

  const chartDate = quote?.trading_date || ''
  const historyDepthKey = `${symbol}:${resolution}`
  const lookbackDays = historyDepth[historyDepthKey] ?? LOOKBACK_DAYS[resolution] ?? 30
  const maxLookbackDays = chartDate ? daysBetween(HISTORY_FLOOR, chartDate) : lookbackDays
  const effectiveLookbackDays = Math.min(lookbackDays, maxLookbackDays || lookbackDays)
  const chartRequest = chartDate
    ? chartRequestFor(symbol, chartDate, resolution, effectiveLookbackDays)
    : { key: '', query: '', chartFrom: '' }
  const chartKey = chartRequest.key ? `${chartAuthScope}:${chartRequest.key}` : ''

  useEffect(() => {
    if (!validSymbol || !chartDate) return undefined
    if (!ALLOWED_RESOLUTIONS.has(resolution)) return undefined

    let active = true
    loadChartCached({
      key: chartKey,
      symbol,
      query: chartRequest.query,
      token: accessToken || undefined,
    })
      .then((data) => {
        if (active) {
          setChartState({
            key: chartKey,
            symbol,
            resolution,
            authScope: chartAuthScope,
            data,
            error: '',
            errorKind: '',
          })
        }
      })
      .catch((error) => {
        if (!active) return
        const failure = chartFailure(error, accessToken)
        setChartState((current) => ({
          key: chartKey,
          symbol,
          resolution,
          authScope: chartAuthScope,
          data: error?.status !== 401 && error?.status !== 403
            && current.authScope === chartAuthScope
            && current.symbol === symbol && current.resolution === resolution
            ? current.data
            : null,
          error: failure.message,
          errorKind: failure.kind,
        }))
      })

    return () => {
      active = false
    }
  }, [
    symbol,
    validSymbol,
    chartDate,
    chartKey,
    chartRequest.query,
    resolution,
    accessToken,
    chartAuthScope,
  ])

  if (!validSymbol) {
    return (
      <div className="page">
        <section className="stock-error-panel">
          <strong>Mã chứng khoán không hợp lệ</strong>
          <p>Hãy nhập mã từ 2 đến 12 ký tự chữ hoặc số.</p>
          <Link to="/danh-sach">Về Bộ quét</Link>
        </section>
      </div>
    )
  }

  const quoteLoading = !quote && !quoteError
  const changeClass = Number(quote?.ratio_change || 0) > 0
    ? 'is-positive'
    : Number(quote?.ratio_change || 0) < 0
      ? 'is-negative'
      : ''

  const chartStateIsCurrent = chartState.authScope === chartAuthScope
  const exactChart = chartStateIsCurrent && chartState.key === chartKey ? chartState.data : null
  const reusableChart = (
    chartStateIsCurrent
    &&
    chartState.symbol === symbol
    && chartState.resolution === resolution
  ) ? chartState.data : null
  const chart = exactChart || reusableChart
  const chartError = chartStateIsCurrent && chartState.key === chartKey && !chartState.data
    ? chartState.error
    : ''
  const bars = Array.isArray(chart?.bars) ? chart.bars : []
  const chartLoading = !chart && !chartError
  const loadingOlderHistory = Boolean(
    chart
    && chartState.symbol === symbol
    && chartState.resolution === resolution
    && chartState.key !== chartKey,
  )

  const earliestLoadedDate = bars[0]?.trading_date || ''
  const hasMoreHistory = Boolean(
    earliestLoadedDate
    && earliestLoadedDate > HISTORY_FLOOR
    && effectiveLookbackDays < maxLookbackDays,
  )

  function loadOlderHistory() {
    if (!chartDate || loadingOlderHistory || !hasMoreHistory) return

    const step = HISTORY_EXPAND_DAYS[resolution] ?? 90
    setHistoryDepth((current) => {
      const currentDepth = current[historyDepthKey] ?? LOOKBACK_DAYS[resolution] ?? 30
      const nextDepth = Math.min(maxLookbackDays, currentDepth + step)
      if (nextDepth <= currentDepth) return current
      return {
        ...current,
        [historyDepthKey]: nextDepth,
      }
    })
  }

  const accessLoading = ready && user && !fetchedAccess && !accessError
  const cccStateIsCurrent = (
    cccState.symbol === symbol
    && cccState.authToken === accessToken
  )
  const radarStateIsCurrent = radarState.authToken === accessToken

  let chartContent
  if (chartError) {
    chartContent = <div className={`detail-state${chartState.errorKind === 'neutral' ? '' : ' is-error'}`}>{chartError}</div>
  } else if (chartLoading) {
    chartContent = <div className="detail-state">Đang tải biểu đồ kỹ thuật…</div>
  } else {
    chartContent = (
      <Suspense fallback={<div className="detail-state">Đang tải chart engine…</div>}>
        <TradingChart
          key={`${chartAuthScope}:${symbol}:${resolution}`}
          bars={bars}
          resolution={resolution}
          onResolutionChange={setResolution}
          loading={chartLoading}
          loadingOlder={loadingOlderHistory}
          hasMoreHistory={hasMoreHistory}
          onNeedOlderHistory={loadOlderHistory}
          liveCandle={liveCandle}
          liveConnected={liveConnected}
        />
      </Suspense>
    )
  }

  return (
    <StockDetailV3View
      symbol={symbol}
      metadata={metadata}
      metadataLoading={metadataLoading}
      quote={quote}
      quoteLoading={quoteLoading}
      quoteError={quoteError}
      changeClass={changeClass}
      formatNumber={formatNumber}
      formatPercent={formatPercent}
      chartContent={chartContent}
      liveConnected={liveConnected}
      activeDetailTab={activeDetailTab}
      onActiveDetailTabChange={setActiveDetailTab}
      ready={ready}
      user={user}
      accessLoading={accessLoading}
      accessError={accessError}
      access={access}
      publicContext={publicContextState.symbol === symbol ? publicContextState.data : null}
      publicContextError={publicContextState.symbol === symbol ? publicContextState.error : ''}
      ccc={cccStateIsCurrent && access?.technical_allowed ? cccState.data : null}
      cccError={cccStateIsCurrent ? cccState.error : ''}
      cccUnavailable={capabilityUnavailable.ccc}
      cccBlockedStatus={cccBlockedStatus}
      cccLoading={Boolean(
        activeDetailTab === 'technical'
        && access?.technical_allowed
        && !cccStateIsCurrent
        && !capabilityUnavailable.ccc
      )}
      radar={radarStateIsCurrent && !capabilityUnavailable.radar ? radarState.data : null}
      radarError={radarStateIsCurrent ? radarState.error : ''}
      radarUnavailable={capabilityUnavailable.radar}
      radarBlockedStatus={radarBlockedStatus}
      financial={financialState.symbol === symbol ? financialState.data : null}
      financialError={financialState.symbol === symbol ? financialState.error : ''}
      financialLoading={financialState.symbol !== symbol}
      quarterly={quarterlyState.symbol === symbol ? quarterlyState.data : null}
      quarterlyError={quarterlyState.symbol === symbol ? quarterlyState.error : ''}
      quarterlyLoading={quarterlyState.symbol !== symbol}
    />
  )
}
