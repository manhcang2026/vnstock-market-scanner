function ContextRow({ label, value }) {
  return <div className="stock-v3-context-row"><dt>{label}</dt><dd>{value || '—'}</dd></div>
}

function friendlyDate(value) {
  if (!value) return '—'
  const [year, month, day] = String(value).slice(0, 10).split('-')
  return year && month && day ? `${day}/${month}/${year}` : value
}

function friendlyUpdate(quote, publicContext) {
  const eventAt = publicContext?.event_at
  if (eventAt) {
    const date = new Date(eventAt)
    if (!Number.isNaN(date.valueOf())) return date.toLocaleString('vi-VN')
  }
  if (quote?.event_time) return `${quote.event_time}${quote.trading_date ? ` · ${friendlyDate(quote.trading_date)}` : ''}`
  return '—'
}

export default function StockDetailContextPanel({
  quote,
  publicContext,
  liveConnected,
  marketSession,
}) {
  const healthy = liveConnected || ['CONNECTED', 'EXPECTED_IDLE'].includes(publicContext?.feed_status)
  return (
    <aside className="stock-v3-context-panel" aria-label="Trạng thái dữ liệu">
      <header className="stock-v3-context-title">Dữ liệu</header>
      <div className="stock-v3-context-body">
        <div className="stock-v3-context-heading">
          <span className={`stock-v3-status-dot${healthy ? ' is-live' : ''}`} />
          <div>
            <strong>{healthy ? 'Dữ liệu đang hoạt động' : 'Dữ liệu có thể chậm'}</strong>
            <small>{liveConnected ? 'Nến hiện tại đang được cập nhật.' : 'Đang hiển thị bản ghi gần nhất.'}</small>
          </div>
        </div>
        <dl>
          <ContextRow label="Phiên thị trường" value={marketSession?.label} />
          <ContextRow label="Ngày giao dịch" value={friendlyDate(publicContext?.trading_date || quote?.trading_date)} />
          <ContextRow label="Ghi nhận gần nhất" value={friendlyUpdate(quote, publicContext)} />
        </dl>
      </div>
    </aside>
  )
}
