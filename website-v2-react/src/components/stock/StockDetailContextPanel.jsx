function ContextRow({ label, value }) {
  return <div className="stock-v3-context-row"><dt>{label}</dt><dd>{value || '—'}</dd></div>
}

function friendlyDate(value) {
  if (!value) return '—'
  const [year, month, day] = String(value).slice(0, 10).split('-')
  return year && month && day ? `${day}/${month}/${year}` : value
}

function friendlyUpdate(quote, publicContext) {
  const latest = Math.max(
    Date.parse(publicContext?.event_at || '') || 0,
    Date.parse(quote?.updated_at || '') || 0,
  )
  if (latest) return new Date(latest).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })
  if (quote?.event_time) return `${quote.event_time}${quote.trading_date ? ` · ${friendlyDate(quote.trading_date)}` : ''}`
  return '—'
}

function recentEvent(value, now) {
  if (!value) return false
  const timestamp = new Date(value).valueOf()
  const age = now.valueOf() - timestamp
  return Number.isFinite(timestamp) && age >= -60_000 && age <= 5 * 60_000
}

export default function StockDetailContextPanel({
  quote,
  publicContext,
  publicContextError,
  liveConnected,
  marketSession,
  now,
}) {
  const marketActive = marketSession?.marketActive === true
  const feedStatus = publicContext?.feed_status
  const fresh = recentEvent(publicContext?.event_at, now)
    || recentEvent(quote?.updated_at, now)
  const healthy = marketActive
    && fresh
    && (feedStatus === 'LIVE' || (!feedStatus && Boolean(quote?.updated_at)))
  const heading = !marketActive
    ? 'Ngoài giờ giao dịch'
    : healthy ? 'Dữ liệu đang hoạt động' : 'Dữ liệu có thể chậm'
  const detail = !marketActive
    ? 'Đang hiển thị dữ liệu phiên gần nhất.'
    : healthy ? 'Bản ghi thị trường được cập nhật gần đây.' : 'Đang hiển thị bản ghi gần nhất.'

  return (
    <aside className="stock-v3-context-panel" aria-label="Trạng thái dữ liệu">
      <header className="stock-v3-context-title">Dữ liệu</header>
      <div className="stock-v3-context-body">
        <div className="stock-v3-context-heading">
          <span className={`stock-v3-status-dot${healthy ? ' is-live' : ''}`} aria-hidden="true" />
          <div>
            <strong>{heading}</strong>
            <small>{detail}</small>
            {marketActive && liveConnected ? <small className="stock-v3-live-indicator">Kết nối trực tiếp</small> : null}
          </div>
        </div>
        <dl>
          <ContextRow label="Phiên thị trường" value={marketSession?.label} />
          <ContextRow label="Ngày giao dịch" value={friendlyDate(publicContext?.trading_date || quote?.trading_date)} />
          <ContextRow label="Ghi nhận gần nhất" value={friendlyUpdate(quote, publicContext)} />
        </dl>
        {publicContextError ? <p className="stock-v3-context-note" role="status">Bối cảnh MA chưa sẵn sàng; các phần khác vẫn hiển thị.</p> : null}
      </div>
    </aside>
  )
}
