import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { fetchChart, fetchQuote, fetchTechnicalAccess } from '../lib/cccApi'
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
const chartResponseCache = new Map()
const chartRequestCache = new Map()

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

// CCC_LIVE_WS_REACT_V1
function liveWebSocketUrl() {
  const configured = import.meta.env.VITE_CCC_WS_URL
  if (configured) return configured

  if (
    window.location.hostname === 'localhost'
    || window.location.hostname === '127.0.0.1'
  ) {
    return 'wss://chuyenchochung.com/api/v2/live'
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/v2/live`
}

export default function StockDetailPage() {
  const params = useParams()
  const symbol = normalizeSymbol(params.symbol)
  const validSymbol = SYMBOL_RE.test(symbol)
  const { user, accessToken, ready } = useAuth()

  const [resolution, setResolution] = useState(5)
  const [metadataState, setMetadataState] = useState({ symbol: '', data: null })
  const [quoteState, setQuoteState] = useState({ symbol: '', data: null, error: '' })
  const [accessState, setAccessState] = useState({ symbol: '', data: null, error: '' })
  const [chartState, setChartState] = useState({
    key: '',
    symbol: '',
    resolution: null,
    data: null,
    error: '',
  })
  const [historyDepth, setHistoryDepth] = useState({})
  const [liveState, setLiveState] = useState({
    symbol: '',
    resolution: null,
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
          error: error?.message || 'Không tải được giá thị trường.',
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol])

  useEffect(() => {
    if (!validSymbol || !ready || !accessToken) return undefined

    const controller = new AbortController()
    fetchTechnicalAccess(symbol, { token: accessToken, signal: controller.signal })
      .then((data) => setAccessState({ symbol, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setAccessState({
          symbol,
          data: null,
          error: error?.message || 'Không kiểm tra được quyền kỹ thuật.',
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol, ready, accessToken])

  const quote = quoteState.symbol === symbol ? quoteState.data : null
  const quoteError = quoteState.symbol === symbol ? quoteState.error : ''
  const metadata = metadataState.symbol === symbol ? metadataState.data : null
  const metadataLoading = metadataState.symbol !== symbol
  const fetchedAccess = accessState.symbol === symbol ? accessState.data : null
  const accessError = accessState.symbol === symbol ? accessState.error : ''

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

  useEffect(() => {
    if (
      !validSymbol
      || !ready
      || !accessToken
      || !access?.technical_allowed
      || !ALLOWED_RESOLUTIONS.has(resolution)
    ) {
      return undefined
    }

    let socket
    let reconnectTimer
    let closedByEffect = false

    const connect = () => {
      socket = new WebSocket(liveWebSocketUrl())

      socket.onopen = () => {
        if (closedByEffect) return

        socket.send(JSON.stringify({
          type: 'subscribe',
          symbol,
          resolution,
          token: accessToken,
        }))

        setLiveState({
          symbol,
          resolution,
          candle: null,
          connected: true,
        })
      }

      socket.onmessage = (event) => {
        if (closedByEffect) return

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
          candle: snapshot.candle || null,
          connected: true,
        })
      }

      socket.onclose = (event) => {
        if (closedByEffect) return

        setLiveState((current) => (
          current.symbol === symbol && current.resolution === resolution
            ? { ...current, connected: false }
            : current
        ))

        if (event.code === 4401 || event.code === 4403) return
        reconnectTimer = window.setTimeout(connect, 2000)
      }

      socket.onerror = () => {
        // onclose handles reconnects; keep console noise out of the product UI.
      }
    }

    connect()

    return () => {
      closedByEffect = true
      window.clearTimeout(reconnectTimer)
      socket?.close(1000, 'route change')
    }
  }, [
    symbol,
    validSymbol,
    ready,
    accessToken,
    access?.technical_allowed,
    resolution,
  ])

  const liveCandle = (
    liveState.symbol === symbol
    && liveState.resolution === resolution
  ) ? liveState.candle : null

  const liveConnected = Boolean(
    liveState.connected
    && liveState.symbol === symbol
    && liveState.resolution === resolution
  )

  const chartDate = quote?.trading_date || ''
  const historyDepthKey = `${symbol}:${resolution}`
  const lookbackDays = historyDepth[historyDepthKey] ?? LOOKBACK_DAYS[resolution] ?? 30
  const maxLookbackDays = chartDate ? daysBetween(HISTORY_FLOOR, chartDate) : lookbackDays
  const effectiveLookbackDays = Math.min(lookbackDays, maxLookbackDays || lookbackDays)
  const chartRequest = chartDate
    ? chartRequestFor(symbol, chartDate, resolution, effectiveLookbackDays)
    : { key: '', query: '', chartFrom: '' }
  const chartKey = chartRequest.key

  useEffect(() => {
    if (!validSymbol || !chartDate || !accessToken || !access?.technical_allowed) return undefined
    if (!ALLOWED_RESOLUTIONS.has(resolution)) return undefined

    let active = true
    loadChartCached({
      key: chartKey,
      symbol,
      query: chartRequest.query,
      token: accessToken,
    })
      .then((data) => {
        if (active) {
          setChartState({
            key: chartKey,
            symbol,
            resolution,
            data,
            error: '',
          })
        }
      })
      .catch((error) => {
        if (!active) return
        setChartState((current) => ({
          key: chartKey,
          symbol,
          resolution,
          data: current.symbol === symbol && current.resolution === resolution
            ? current.data
            : null,
          error: error?.message || 'Không tải được biểu đồ.',
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
    access?.technical_allowed,
  ])

  useEffect(() => {
    if (!validSymbol || !chartDate || !accessToken || !access?.technical_allowed) return undefined

    const timer = window.setTimeout(() => {
      for (const nextResolution of ALLOWED_RESOLUTIONS) {
        if (nextResolution === resolution) continue
        const next = chartRequestFor(symbol, chartDate, nextResolution)
        if (getCachedChart(next.key)) continue
        loadChartCached({
          key: next.key,
          symbol,
          query: next.query,
          token: accessToken,
        }).catch(() => {})
      }
    }, 120)

    return () => window.clearTimeout(timer)
  }, [
    symbol,
    validSymbol,
    chartDate,
    resolution,
    accessToken,
    access?.technical_allowed,
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

  const exactChart = chartState.key === chartKey ? chartState.data : null
  const reusableChart = (
    chartState.symbol === symbol
    && chartState.resolution === resolution
  ) ? chartState.data : null
  const chart = exactChart || reusableChart
  const chartError = chartState.key === chartKey && !chartState.data
    ? chartState.error
    : ''
  const bars = Array.isArray(chart?.bars) ? chart.bars : []
  const chartLoading = access?.technical_allowed && !chart && !chartError
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

  let chartContent
  if (!ready) {
    chartContent = <div className="detail-state">Đang kiểm tra phiên đăng nhập…</div>
  } else if (!user) {
    chartContent = (
      <div className="technical-lock">
        <strong>Đăng nhập để mở vùng kỹ thuật</strong>
        <p>Giá thị trường vẫn công khai. Biểu đồ kỹ thuật được kiểm tra quyền ở server.</p>
        <Link to="/dang-nhap">Đăng nhập</Link>
      </div>
    )
  } else if (accessLoading) {
    chartContent = <div className="detail-state">Đang kiểm tra technical entitlement…</div>
  } else if (accessError) {
    chartContent = <div className="detail-state is-error">{accessError}</div>
  } else if (access && !access.technical_allowed) {
    chartContent = (
      <div className="technical-lock">
        <strong>CCC Technical Intelligence ngoài phạm vi hiện tại</strong>
        <p>Public quote vẫn hiển thị. Backend không trả technical payload cho mã ngoài entitlement.</p>
        <span>{access.reason || 'OUTSIDE_ENTITLEMENT'}</span>
      </div>
    )
  } else if (chartError) {
    chartContent = <div className="detail-state is-error">{chartError}</div>
  } else if (chartLoading) {
    chartContent = <div className="detail-state">Đang tải biểu đồ kỹ thuật…</div>
  } else {
    chartContent = (
      <Suspense fallback={<div className="detail-state">Đang tải chart engine…</div>}>
        <TradingChart
          key={`${symbol}:${resolution}`}
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
      chart={chart}
      chartContent={chartContent}
      liveConnected={liveConnected}
      ready={ready}
      user={user}
      accessLoading={accessLoading}
      accessError={accessError}
      access={access}
    />
  )
}
