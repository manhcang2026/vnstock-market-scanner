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

export default function TradingChart({
  bars = [],
  resolution = 5,
  onResolutionChange,
  loading = false,
}) {
  const chartRef = useRef(null)
  const wrapRef = useRef(null)
  const [showEma, setShowEma] = useState(true)
  const [showRsi, setShowRsi] = useState(true)
  const [showMacd, setShowMacd] = useState(true)
  const [cursor, setCursor] = useState(null)

  const computed = useMemo(() => {
    const closes = bars.map((bar) => Number(bar.close))
    return {
      ema7: ema(closes, 7),
      ema25: ema(closes, 25),
      ema99: ema(closes, 99),
      ema200: ema(closes, 200),
      rsi14: rsi(closes, 14),
      macd: macd(closes),
    }
  }, [bars])

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

    const emaSeries = []
    if (showEma) {
      const configs = [
        [computed.ema7, '#f2c94c', 7],
        [computed.ema25, '#db5ac5', 25],
        [computed.ema99, '#9b7bd4', 99],
        [computed.ema200, '#67cc75', 200],
      ]
      configs.forEach(([values, color, startAt]) => {
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
        series.setData(lineData(bars, values, Math.min(startAt - 1, bars.length - 1)))
        emaSeries.push(series)
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

    if (showRsi) {
      const rsiSeries = chart.addSeries(
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
      dea.setData(lineData(bars, computed.macd.signal, 25))
    }

    const panes = chart.panes()
    panes[0]?.setStretchFactor(5)
    panes[1]?.setStretchFactor(1.25)
    if (showRsi) panes[2]?.setStretchFactor(1.15)
    if (showMacd) panes[showRsi ? 3 : 2]?.setStretchFactor(1.15)

    chart.subscribeCrosshairMove((param) => {
      if (!param?.time) {
        setCursor(null)
        return
      }
      const candle = param.seriesData.get(candleSeries)
      const volume = param.seriesData.get(volumeSeries)
      if (!candle) {
        setCursor(null)
        return
      }
      setCursor({
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: volume?.value,
      })
    })

    chart.timeScale().fitContent()

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      chart.applyOptions({
        width: entry.contentRect.width,
        height: entry.contentRect.width < 640 ? 520 : 620,
      })
    })
    observer.observe(container)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [bars, computed, showEma, showRsi, showMacd, resolution])

  async function toggleFullscreen() {
    const element = wrapRef.current
    if (!element) return
    if (document.fullscreenElement) {
      await document.exitFullscreen()
      return
    }
    await element.requestFullscreen?.()
  }

  const latest = bars[bars.length - 1]
  const display = cursor || (latest
    ? {
        open: latest.open,
        high: latest.high,
        low: latest.low,
        close: latest.close,
        volume: latest.volume,
      }
    : null)

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
              onClick={() => onResolutionChange?.(item.resolution)}
              disabled={loading}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="indicator-group">
          <button type="button" className={showEma ? 'is-active' : ''} onClick={() => setShowEma((v) => !v)}>
            EMA
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
      </div>

      {showEma ? (
        <div className="indicator-legend">
          <span className="ema7">EMA(7)</span>
          <span className="ema25">EMA(25)</span>
          <span className="ema99">EMA(99)</span>
          <span className="ema200">EMA(200)</span>
        </div>
      ) : null}

      <div className="terminal-chart" ref={chartRef} />

      <div className="terminal-attribution">
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
          TradingView Lightweight Charts™ © 2025 TradingView, Inc.
        </a>
      </div>
    </div>
  )
}
