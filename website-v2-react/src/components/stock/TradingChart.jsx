import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
} from 'lightweight-charts'
import '../../styles/trading-chart.css'

const TIMEFRAMES = [
  { label: '5m', resolution: 5 },
  { label: '15m', resolution: 15 },
  { label: '30m', resolution: 30 },
  { label: '1H', resolution: 60 },
  { label: '1D', resolution: 1440 },
]

function toTimestamp(bar) {
  // Lightweight Charts treats numeric timestamps as UTC. CCC source bars use
  // Vietnam exchange wall-clock time (Asia/Ho_Chi_Minh, UTC+7), so encode the
  // local date/time as a UTC-shaped timestamp to preserve the displayed clock.
  const [year, month, day] = bar.trading_date.split('-').map(Number)
  const [hour, minute] = bar.minute.split(':').map(Number)
  return Math.floor(Date.UTC(year, month - 1, day, hour, minute, 0) / 1000)
}

function priceFormat(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(Number(value))
}

function compactVolume(value) {
  const n = Number(value || 0)
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

// CCC_CHART_TOOLS_V2
// CCC_FLOATING_CANDLE_INSPECTOR_V2
function sma(values, period) {
  const out = Array(values.length).fill(null)
  if (period <= 0 || values.length < period) return out

  let sum = 0
  for (let i = 0; i < values.length; i += 1) {
    sum += Number(values[i])
    if (i >= period) sum -= Number(values[i - period])
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

function bollinger(values, period = 20, multiplier = 2) {
  const middle = sma(values, period)
  return values.map((_, index) => {
    if (index < period - 1 || middle[index] === null) return null
    const start = index - period + 1
    const mean = middle[index]
    let squared = 0
    for (let i = start; i <= index; i += 1) {
      const delta = Number(values[i]) - mean
      squared += delta * delta
    }
    const deviation = Math.sqrt(squared / period)
    return {
      middle: mean,
      upper: mean + multiplier * deviation,
      lower: mean - multiplier * deviation,
    }
  })
}

function bollingerLineData(bars, values, key) {
  return bars.flatMap((bar, index) => {
    const point = values[index]
    const value = point?.[key]
    if (value === null || value === undefined || Number.isNaN(value)) return []
    return [{ time: toTimestamp(bar), value }]
  })
}

function formatBarTime(bar, resolution) {
  if (!bar) return '—'
  const [year, month, day] = String(bar.trading_date || '').split('-')
  if (!year || !month || !day) return '—'
  if (resolution >= 1440) return `${day}/${month}/${year}`
  return `${day}/${month}/${year} ${bar.minute || ''}`.trim()
}

function signedNumber(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n > 0 ? '+' : ''}${priceFormat(n)}`
}

function signedPercent(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n > 0 ? '+' : ''}${new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)}%`
}

function ema(values, period) {
  if (!values.length) return []
  const alpha = 2 / (period + 1)
  let previous = Number(values[0])
  return values.map((raw, index) => {
    const value = Number(raw)
    previous = index === 0 ? value : value * alpha + previous * (1 - alpha)
    return previous
  })
}

function rsi(values, period = 14) {
  const out = Array(values.length).fill(null)
  if (values.length <= period) return out

  let gain = 0
  let loss = 0
  for (let i = 1; i <= period; i += 1) {
    const change = Number(values[i]) - Number(values[i - 1])
    if (change >= 0) gain += change
    else loss -= change
  }

  let avgGain = gain / period
  let avgLoss = loss / period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)

  for (let i = period + 1; i < values.length; i += 1) {
    const change = Number(values[i]) - Number(values[i - 1])
    const currentGain = Math.max(change, 0)
    const currentLoss = Math.max(-change, 0)
    avgGain = (avgGain * (period - 1) + currentGain) / period
    avgLoss = (avgLoss * (period - 1) + currentLoss) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }

  return out
}

function macd(values, fast = 12, slow = 26, signalPeriod = 9) {
  const fastLine = ema(values, fast)
  const slowLine = ema(values, slow)
  const line = values.map((_, index) => fastLine[index] - slowLine[index])
  const signal = ema(line, signalPeriod)
  const histogram = line.map((value, index) => value - signal[index])
  return { line, signal, histogram }
}

function lineData(bars, values, startAt = 0) {
  return bars.flatMap((bar, index) => {
    const value = values[index]
    if (index < startAt || value === null || value === undefined || Number.isNaN(value)) return []
    return [{ time: toTimestamp(bar), value }]
  })
}

function mergeLiveCandle(bars, liveCandle) {
  if (!liveCandle?.trading_date || !liveCandle?.minute) return bars

  const next = [...bars]
  const liveTime = toTimestamp(liveCandle)

  for (let index = next.length - 1; index >= 0; index -= 1) {
    const currentTime = toTimestamp(next[index])
    if (currentTime === liveTime) {
      next[index] = { ...next[index], ...liveCandle }
      return next
    }
    if (currentTime < liveTime) break
  }

  if (!next.length || toTimestamp(next[next.length - 1]) < liveTime) {
    next.push(liveCandle)
  }

  return next
}

// CCC_LAZY_HISTORY_V2
export default function TradingChart({
  bars = [],
  resolution = 5,
  onResolutionChange,
  loading = false,
  loadingOlder = false,
  hasMoreHistory = false,
  onNeedOlderHistory,
  liveCandle = null,
  liveConnected = false,
}) {
  const chartRef = useRef(null)
  const wrapRef = useRef(null)
  const viewportRef = useRef({ resolution: null, range: null })
  const olderRequestRef = useRef(false)
  const loadOlderCallbackRef = useRef(onNeedOlderHistory)
  const historyStatusRef = useRef({ hasMoreHistory, loadingOlder })
  const liveSeriesRef = useRef(null)
  const barLookupRef = useRef(new Map())
  const lastSeriesTimeRef = useRef(null)
  const [maVisibility, setMaVisibility] = useState(() => {
    const defaults = { 10: true, 25: true, 99: true, 200: true }
    try {
      const saved = window.localStorage.getItem('ccc-chart-ma-visibility')
      return saved ? { ...defaults, ...JSON.parse(saved) } : defaults
    } catch {
      return defaults
    }
  })
  const [showMaMenu, setShowMaMenu] = useState(false)
  const [showBollinger, setShowBollinger] = useState(() => {
    try {
      return window.localStorage.getItem('ccc-chart-bollinger') !== '0'
    } catch {
      return true
    }
  })
  const [showRsi, setShowRsi] = useState(true)
  const [showMacd, setShowMacd] = useState(true)
  const [cursor, setCursor] = useState(null)
  const [pinned, setPinned] = useState(null)

  useEffect(() => {
    loadOlderCallbackRef.current = onNeedOlderHistory
  }, [onNeedOlderHistory])

  useEffect(() => {
    historyStatusRef.current = { hasMoreHistory, loadingOlder }
    if (!loadingOlder) olderRequestRef.current = false
  }, [hasMoreHistory, loadingOlder])

  const computed = useMemo(() => {
    const closes = bars.map((bar) => Number(bar.close))
    return {
      ma10: sma(closes, 10),
      ma25: sma(closes, 25),
      ma99: sma(closes, 99),
      ma200: sma(closes, 200),
      bollinger20: bollinger(closes, 20, 2),
      rsi14: rsi(closes, 14),
      macd: macd(closes),
    }
  }, [bars])

  const liveComputed = useMemo(() => {
    const liveBars = mergeLiveCandle(bars, liveCandle)
    const closes = liveBars.map((bar) => Number(bar.close))
    return {
      bars: liveBars,
      ma10: sma(closes, 10),
      ma25: sma(closes, 25),
      ma99: sma(closes, 99),
      ma200: sma(closes, 200),
      bollinger20: bollinger(closes, 20, 2),
      rsi14: rsi(closes, 14),
      macd: macd(closes),
    }
  }, [bars, liveCandle])

  useEffect(() => {
    const container = chartRef.current
    if (!container || !bars.length) return undefined

    container.innerHTML = ''

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientWidth < 640 ? 520 : 620,
      layout: {
        background: { type: ColorType.Solid, color: '#0f1726' },
        textColor: '#8fa0b8',
        fontSize: 11,
        attributionLogo: false,
        panes: {
          enableResize: true,
          separatorColor: '#263249',
          separatorHoverColor: 'rgba(132, 146, 166, .18)',
        },
      },
      grid: {
        vertLines: { color: 'rgba(89, 105, 132, .16)' },
        horzLines: { color: 'rgba(89, 105, 132, .16)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: 'rgba(180, 191, 210, .42)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#263249',
        },
        horzLine: {
          color: 'rgba(180, 191, 210, .42)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#263249',
        },
      },
      rightPriceScale: {
        borderColor: '#263249',
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: '#263249',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        tickMarkFormatter: (time) => {
          const date = new Date(Number(time) * 1000)
          const dd = String(date.getUTCDate()).padStart(2, '0')
          const mm = String(date.getUTCMonth() + 1).padStart(2, '0')
          const hh = String(date.getUTCHours()).padStart(2, '0')
          const min = String(date.getUTCMinutes()).padStart(2, '0')
          return resolution >= 1440 ? `${dd}/${mm}` : `${hh}:${min}`
        },
        barSpacing: container.clientWidth < 640 ? 7 : 9,
        minBarSpacing: 3,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      localization: {
        priceFormatter: (value) => priceFormat(value),
        timeFormatter: (time) => {
          const date = new Date(Number(time) * 1000)
          const dd = String(date.getUTCDate()).padStart(2, '0')
          const mm = String(date.getUTCMonth() + 1).padStart(2, '0')
          const yyyy = date.getUTCFullYear()
          const hh = String(date.getUTCHours()).padStart(2, '0')
          const min = String(date.getUTCMinutes()).padStart(2, '0')
          return resolution >= 1440
            ? `${dd}/${mm}/${yyyy}`
            : `${dd}/${mm} ${hh}:${min}`
        },
      },
    })

    const candleSeries = chart.addSeries(
      CandlestickSeries,
      {
        upColor: '#20b486',
        downColor: '#ef4d64',
        wickUpColor: '#20b486',
        wickDownColor: '#ef4d64',
        borderVisible: false,
        priceLineVisible: true,
        lastValueVisible: true,
      },
      0,
    )

    const candleData = bars.map((bar) => ({
      time: toTimestamp(bar),
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    }))
    candleSeries.setData(candleData)
    lastSeriesTimeRef.current = candleData.length
      ? candleData[candleData.length - 1].time
      : null

    const maConfigs = [
      [10, computed.ma10, '#f2c94c'],
      [25, computed.ma25, '#db5ac5'],
      [99, computed.ma99, '#9b7bd4'],
      [200, computed.ma200, '#67cc75'],
    ]

    const maSeries = {}

    maConfigs.forEach(([period, values, color]) => {
      if (!maVisibility[period]) return
      const series = chart.addSeries(
        LineSeries,
        {
          color,
          lineWidth: 1.5,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        },
        0,
      )
      series.setData(lineData(bars, values, period - 1))
      maSeries[period] = series
    })

    const bbSeries = {}

    if (showBollinger) {
      const bbConfigs = [
        ['upper', '#4aa3ff', 1],
        ['middle', '#7f8ea8', 1],
        ['lower', '#4aa3ff', 1],
      ]
      bbConfigs.forEach(([key, color, lineWidth]) => {
        const series = chart.addSeries(
          LineSeries,
          {
            color,
            lineWidth,
            lineStyle: key === 'middle' ? 2 : 0,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          },
          0,
        )
        series.setData(bollingerLineData(bars, computed.bollinger20, key))
        bbSeries[key] = series
      })
    }

    const volumeSeries = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    )
    volumeSeries.setData(
      bars.map((bar) => ({
        time: toTimestamp(bar),
        value: Number(bar.volume || 0),
        color: Number(bar.close) >= Number(bar.open)
          ? 'rgba(32, 180, 134, .58)'
          : 'rgba(239, 77, 100, .58)',
      })),
    )

    let rsiSeries = null
    const macdSeries = {
      histogram: null,
      dif: null,
      dea: null,
    }

    if (showRsi) {
      rsiSeries = chart.addSeries(
        LineSeries,
        {
          color: '#f2c94c',
          lineWidth: 1.4,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerVisible: false,
        },
        2,
      )
      rsiSeries.setData(lineData(bars, computed.rsi14, 14))
    }

    if (showMacd) {
      const paneIndex = showRsi ? 3 : 2
      const macdHist = chart.addSeries(
        HistogramSeries,
        {
          priceLineVisible: false,
          lastValueVisible: false,
        },
        paneIndex,
      )
      macdSeries.histogram = macdHist
      macdHist.setData(
        bars.flatMap((bar, index) => {
          if (index < 25) return []
          const value = computed.macd.histogram[index]
          return [{
            time: toTimestamp(bar),
            value,
            color: value >= 0 ? 'rgba(32, 180, 134, .72)' : 'rgba(239, 77, 100, .72)',
          }]
        }),
      )

      const dif = chart.addSeries(
        LineSeries,
        {
          color: '#f2c94c',
          lineWidth: 1.25,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        },
        paneIndex,
      )
      macdSeries.dif = dif
      dif.setData(lineData(bars, computed.macd.line, 25))

      const dea = chart.addSeries(
        LineSeries,
        {
          color: '#db5ac5',
          lineWidth: 1.25,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        },
        paneIndex,
      )
      macdSeries.dea = dea
      dea.setData(lineData(bars, computed.macd.signal, 25))
    }

    liveSeriesRef.current = {
      candle: candleSeries,
      volume: volumeSeries,
      ma: maSeries,
      bb: bbSeries,
      rsi: rsiSeries,
      macd: macdSeries,
    }

    const panes = chart.panes()
    panes[0]?.setStretchFactor(5)
    panes[1]?.setStretchFactor(1.25)
    if (showRsi) panes[2]?.setStretchFactor(1.15)
    if (showMacd) panes[showRsi ? 3 : 2]?.setStretchFactor(1.15)

    barLookupRef.current = new Map(
      bars.map((bar) => [toTimestamp(bar), bar]),
    )

    const readPoint = (param) => {
      if (!param?.time) return null
      const candle = param.seriesData.get(candleSeries)
      const volume = param.seriesData.get(volumeSeries)
      const sourceBar = barLookupRef.current.get(Number(param.time))
      if (!candle || !sourceBar) return null
      return {
        trading_date: sourceBar.trading_date,
        minute: sourceBar.minute,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: volume?.value ?? sourceBar.volume,
      }
    }

    const handleCrosshairMove = (param) => {
      setCursor(readPoint(param))
    }

    const handleClick = (param) => {
      const point = readPoint(param)
      if (!point) {
        setPinned(null)
        return
      }

      const chartWidth = chartRef.current?.clientWidth || 0
      const chartHeight = chartRef.current?.clientHeight || 0
      const x = Number(param?.point?.x)
      const y = Number(param?.point?.y)
      const gap = 16
      const estimatedHeight = 230

      let inspectorStyle
      if (
        Number.isFinite(x)
        && Number.isFinite(y)
        && chartWidth > 0
        && chartHeight > 0
      ) {
        const top = Math.max(
          8,
          Math.min(
            y - 18,
            Math.max(8, chartHeight - estimatedHeight - 8),
          ),
        )

        inspectorStyle = x < chartWidth / 2
          ? {
              left: `${Math.min(x + gap, chartWidth - 8)}px`,
              right: 'auto',
              top: `${top}px`,
              transform: 'none',
            }
          : {
              left: `${Math.max(x - gap, 8)}px`,
              right: 'auto',
              top: `${top}px`,
              transform: 'translateX(-100%)',
            }
      }

      setPinned({
        ...point,
        inspectorStyle,
      })
    }

    chart.subscribeCrosshairMove(handleCrosshairMove)
    chart.subscribeClick(handleClick)

    const timeScale = chart.timeScale()

    const handleVisibleTimeRangeChange = (range) => {
      if (!range) return
      viewportRef.current = {
        resolution,
        range,
      }
    }

    const handleVisibleLogicalRangeChange = (range) => {
      if (!range || range.from > 12) return
      const status = historyStatusRef.current
      if (!status.hasMoreHistory || status.loadingOlder || olderRequestRef.current) return
      olderRequestRef.current = true
      loadOlderCallbackRef.current?.()
    }

    timeScale.subscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange)
    timeScale.subscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange)

    const previousViewport = viewportRef.current
    if (
      previousViewport.resolution === resolution
      && previousViewport.range
    ) {
      timeScale.setVisibleRange(previousViewport.range)
    } else {
      viewportRef.current = { resolution, range: null }
      timeScale.fitContent()
    }

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      chart.applyOptions({
        width: entry.contentRect.width,
        height: entry.contentRect.width < 640 ? 520 : 620,
      })
    })
    observer.observe(container)

    return () => {
      liveSeriesRef.current = null
      lastSeriesTimeRef.current = null
      observer.disconnect()
      timeScale.unsubscribeVisibleTimeRangeChange(handleVisibleTimeRangeChange)
      timeScale.unsubscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange)
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      chart.unsubscribeClick(handleClick)
      chart.remove()
    }
  }, [bars, computed, maVisibility, showBollinger, showRsi, showMacd, resolution])

  useEffect(() => {
    const refs = liveSeriesRef.current
    const liveBars = liveComputed.bars
    const index = liveBars.length - 1
    const bar = liveBars[index]

    if (!refs || !liveCandle || !bar || index < 0) return

    const time = toTimestamp(bar)
    const lastSeriesTime = lastSeriesTimeRef.current

    if (lastSeriesTime !== null && time < lastSeriesTime) {
      return
    }

    lastSeriesTimeRef.current = time
    barLookupRef.current.set(time, bar)

    refs.candle?.update({
      time,
      open: Number(bar.open),
      high: Number(bar.high),
      low: Number(bar.low),
      close: Number(bar.close),
    })

    refs.volume?.update({
      time,
      value: Number(bar.volume || 0),
      color: Number(bar.close) >= Number(bar.open)
        ? 'rgba(32, 180, 134, .58)'
        : 'rgba(239, 77, 100, .58)',
    })

    const maValues = {
      10: liveComputed.ma10[index],
      25: liveComputed.ma25[index],
      99: liveComputed.ma99[index],
      200: liveComputed.ma200[index],
    }

    Object.entries(maValues).forEach(([period, value]) => {
      if (value === null || value === undefined || Number.isNaN(value)) return
      refs.ma?.[period]?.update({ time, value })
    })

    const bb = liveComputed.bollinger20[index]
    if (bb) {
      refs.bb?.upper?.update({ time, value: bb.upper })
      refs.bb?.middle?.update({ time, value: bb.middle })
      refs.bb?.lower?.update({ time, value: bb.lower })
    }

    const rsiValue = liveComputed.rsi14[index]
    if (rsiValue !== null && rsiValue !== undefined && !Number.isNaN(rsiValue)) {
      refs.rsi?.update({ time, value: rsiValue })
    }

    if (index >= 25) {
      const histogram = liveComputed.macd.histogram[index]
      const dif = liveComputed.macd.line[index]
      const dea = liveComputed.macd.signal[index]

      refs.macd?.histogram?.update({
        time,
        value: histogram,
        color: histogram >= 0
          ? 'rgba(32, 180, 134, .72)'
          : 'rgba(239, 77, 100, .72)',
      })
      refs.macd?.dif?.update({ time, value: dif })
      refs.macd?.dea?.update({ time, value: dea })
    }
  }, [liveCandle, liveComputed])

  function toggleMa(period) {
    setMaVisibility((current) => {
      const next = { ...current, [period]: !current[period] }
      try {
        window.localStorage.setItem('ccc-chart-ma-visibility', JSON.stringify(next))
      } catch {
        // Local preference persistence is best-effort.
      }
      return next
    })
  }

  function toggleBollinger() {
    setShowBollinger((current) => {
      const next = !current
      try {
        window.localStorage.setItem('ccc-chart-bollinger', next ? '1' : '0')
      } catch {
        // Local preference persistence is best-effort.
      }
      return next
    })
  }

  async function toggleFullscreen() {
    const element = wrapRef.current
    if (!element) return
    if (document.fullscreenElement) {
      await document.exitFullscreen()
      return
    }
    await element.requestFullscreen?.()
  }

  const liveBars = liveComputed.bars
  const latest = liveBars[liveBars.length - 1]
  const activePinned = pinned && liveBars.some(
    (bar) => bar.trading_date === pinned.trading_date && bar.minute === pinned.minute,
  ) ? pinned : null
  const display = activePinned || cursor || (latest
    ? {
        trading_date: latest.trading_date,
        minute: latest.minute,
        open: latest.open,
        high: latest.high,
        low: latest.low,
        close: latest.close,
        volume: latest.volume,
      }
    : null)

  const latestIndex = liveBars.length - 1
  const latestBb = latestIndex >= 0 ? liveComputed.bollinger20[latestIndex] : null
  const pinnedChange = activePinned
    ? Number(activePinned.close) - Number(activePinned.open)
    : null
  const pinnedPercent = activePinned && Number(activePinned.open) !== 0
    ? (pinnedChange / Number(activePinned.open)) * 100
    : null
  const pinnedDirection = pinnedChange > 0
    ? 'is-positive'
    : pinnedChange < 0
      ? 'is-negative'
      : ''

  const inspectorStyle = activePinned?.inspectorStyle

  return (
    <div className="trading-terminal" ref={wrapRef}>
      <div className="terminal-toolbar">
        <div className="timeframe-group" aria-label="Khung thời gian">
          <span className="toolbar-caption">Thời gian</span>
          {TIMEFRAMES.map((item) => (
            <button
              key={item.resolution}
              type="button"
              className={resolution === item.resolution ? 'is-active' : ''}
              onClick={() => {
                setPinned(null)
                onResolutionChange?.(item.resolution)
              }}
              disabled={loading}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="indicator-group">
          <div className="ma-control">
            <button
              type="button"
              className={Object.values(maVisibility).some(Boolean) ? 'is-active' : ''}
              onClick={() => setShowMaMenu((value) => !value)}
              aria-expanded={showMaMenu}
            >
              MA ▾
            </button>
            {showMaMenu ? (
              <div className="ma-menu">
                {[10, 25, 99, 200].map((period) => (
                  <button
                    key={period}
                    type="button"
                    className={maVisibility[period] ? 'is-enabled' : ''}
                    onClick={() => toggleMa(period)}
                  >
                    <span className={`ma-swatch ma${period}`} />
                    <span>MA{period}</span>
                    <b>{maVisibility[period] ? '✓' : ''}</b>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className={showBollinger ? 'is-active' : ''}
            onClick={toggleBollinger}
            title="Bollinger Bands (20, 2)"
          >
            BB
          </button>
          <button type="button" className={showRsi ? 'is-active' : ''} onClick={() => setShowRsi((v) => !v)}>
            RSI
          </button>
          <button type="button" className={showMacd ? 'is-active' : ''} onClick={() => setShowMacd((v) => !v)}>
            MACD
          </button>
          <button type="button" className="fullscreen-button" onClick={toggleFullscreen} title="Toàn màn hình">
            ⛶
          </button>

        </div>
      </div>

      <div className="terminal-readout">
        {display ? (
          <>
            <span>O <b>{priceFormat(display.open)}</b></span>
            <span>H <b>{priceFormat(display.high)}</b></span>
            <span>L <b>{priceFormat(display.low)}</b></span>
            <span>C <b>{priceFormat(display.close)}</b></span>
            <span>Vol <b>{compactVolume(display.volume)}</b></span>
          </>
        ) : (
          <span>Chưa có dữ liệu OHLC</span>
        )}
        {loading ? <em>Đang đổi khung…</em> : null}
        {!loading && loadingOlder ? <em>Đang tải thêm lịch sử…</em> : null}
        {liveConnected ? <em title="WebSocket cập nhật mỗi ~3 giây">● LIVE 3s</em> : null}
      </div>

      {(Object.values(maVisibility).some(Boolean) || showBollinger) ? (
        <div className="indicator-legend">
          {maVisibility[10] ? (
            <span className="ma10">MA(10) {priceFormat(liveComputed.ma10[latestIndex])}</span>
          ) : null}
          {maVisibility[25] ? (
            <span className="ma25">MA(25) {priceFormat(liveComputed.ma25[latestIndex])}</span>
          ) : null}
          {maVisibility[99] ? (
            <span className="ma99">MA(99) {priceFormat(liveComputed.ma99[latestIndex])}</span>
          ) : null}
          {maVisibility[200] ? (
            <span className="ma200">MA(200) {priceFormat(liveComputed.ma200[latestIndex])}</span>
          ) : null}
          {showBollinger ? (
            <span className="bb20">
              BB(20,2) {latestBb
                ? `${priceFormat(latestBb.lower)} / ${priceFormat(latestBb.middle)} / ${priceFormat(latestBb.upper)}`
                : '—'}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="terminal-chart-wrap">
        <div className="terminal-chart" ref={chartRef} />
        {activePinned ? (
          <aside
            className="candle-inspector"
            aria-label="Thông số nến đã chọn"
            style={inspectorStyle}
          >
            <div className="inspector-title">
              <strong>{formatBarTime(activePinned, resolution)}</strong>
              <span>OHLCV</span>
            </div>
            <dl>
              <div><dt>Mở</dt><dd>{priceFormat(activePinned.open)}</dd></div>
              <div><dt>Cao</dt><dd>{priceFormat(activePinned.high)}</dd></div>
              <div><dt>Thấp</dt><dd>{priceFormat(activePinned.low)}</dd></div>
              <div><dt>Đóng</dt><dd>{priceFormat(activePinned.close)}</dd></div>
              <div><dt>Thay đổi</dt><dd className={pinnedDirection}>{signedNumber(pinnedChange)}</dd></div>
              <div><dt>% thay đổi</dt><dd className={pinnedDirection}>{signedPercent(pinnedPercent)}</dd></div>
              <div><dt>Khối lượng</dt><dd>{compactVolume(activePinned.volume)}</dd></div>
            </dl>
          </aside>
        ) : null}
      </div>


      <div className="terminal-attribution">
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™ © 2025 TradingView, Inc.
        </a>
      </div>
    </div>
  )
}
