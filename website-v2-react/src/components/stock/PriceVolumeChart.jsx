function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function formatPrice(value) {
  return new Intl.NumberFormat('vi-VN', {
    maximumFractionDigits: 2,
  }).format(Number(value || 0))
}

function compactVolume(value) {
  const n = Number(value || 0)
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

export default function PriceVolumeChart({ bars = [] }) {
  if (!bars.length) {
    return <div className="chart-empty">Chưa có dữ liệu biểu đồ cho phiên này.</div>
  }

  const width = 1000
  const height = 360
  const padding = { top: 28, right: 72, bottom: 34, left: 16 }
  const priceBottom = 255
  const volumeTop = 280
  const volumeBottom = 330
  const innerWidth = width - padding.left - padding.right

  const lows = bars.map((bar) => Number(bar.low))
  const highs = bars.map((bar) => Number(bar.high))
  let minPrice = Math.min(...lows)
  let maxPrice = Math.max(...highs)
  if (minPrice === maxPrice) {
    minPrice -= 1
    maxPrice += 1
  }
  const pricePad = (maxPrice - minPrice) * 0.06
  minPrice -= pricePad
  maxPrice += pricePad

  const maxVolume = Math.max(...bars.map((bar) => Number(bar.volume || 0)), 1)
  const xFor = (index) => padding.left + (innerWidth * index) / Math.max(1, bars.length - 1)
  const yForPrice = (price) => {
    const ratio = (Number(price) - minPrice) / (maxPrice - minPrice)
    return priceBottom - ratio * (priceBottom - padding.top)
  }

  const points = bars
    .map((bar, index) => `${xFor(index).toFixed(2)},${yForPrice(bar.close).toFixed(2)}`)
    .join(' ')

  const gridPrices = Array.from({ length: 5 }, (_, i) => {
    const ratio = i / 4
    return maxPrice - (maxPrice - minPrice) * ratio
  })

  const barWidth = clamp(innerWidth / bars.length * 0.7, 1, 5)
  const first = bars[0]
  const last = bars[bars.length - 1]

  return (
    <div className="price-volume-chart">
      <div className="chart-legend">
        <span>{first.minute}</span>
        <strong>Giá cuối {formatPrice(last.close)}</strong>
        <span>{last.minute}</span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Biểu đồ giá và khối lượng trong phiên"
        preserveAspectRatio="none"
      >
        {gridPrices.map((price) => {
          const y = yForPrice(price)
          return (
            <g key={price}>
              <line className="chart-grid-line" x1={padding.left} y1={y} x2={width - padding.right} y2={y} />
              <text className="chart-axis-label" x={width - padding.right + 8} y={y + 4}>
                {formatPrice(price)}
              </text>
            </g>
          )
        })}

        <polyline className="chart-price-line" fill="none" points={points} />

        {bars.map((bar, index) => {
          const x = xFor(index) - barWidth / 2
          const volume = Number(bar.volume || 0)
          const h = Math.max(1, (volume / maxVolume) * (volumeBottom - volumeTop))
          const y = volumeBottom - h
          const up = Number(bar.close) >= Number(bar.open)
          return (
            <rect
              key={`${bar.trading_date}-${bar.minute}`}
              className={up ? 'chart-volume is-up' : 'chart-volume is-down'}
              x={x}
              y={y}
              width={barWidth}
              height={h}
              rx="0.5"
            />
          )
        })}

        <line className="chart-separator" x1={padding.left} y1={volumeTop - 8} x2={width - padding.right} y2={volumeTop - 8} />
        <text className="chart-volume-label" x={padding.left} y={volumeTop + 6}>
          KL max {compactVolume(maxVolume)}
        </text>
      </svg>
    </div>
  )
}
