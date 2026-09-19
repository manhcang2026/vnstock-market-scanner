import { Link } from 'react-router-dom'

const STATE_LABELS = {
  WATCHING: 'Đang theo dõi',
  FLOW_APPEARING: 'Dòng tiền xuất hiện',
  FLOW_PRICE_CONFIRMED: 'Dòng tiền & giá xác nhận',
  MOMENTUM_MAINTAINED: 'Xu hướng duy trì',
  MOMENTUM_WEAKENING: 'Động lượng suy yếu',
  SELLING_PRESSURE: 'Áp lực bán',
}

function shortTime(value) {
  if (!value) return '—'
  const match = String(value).match(/T?(\d{2}:\d{2})/)
  return match?.[1] || '—'
}

export default function StockDetailSignalRail({ radar, radarError }) {
  const groups = Array.isArray(radar?.groups) ? radar.groups : []
  const activeGroups = groups.filter(group => Number(group.total) > 0)
  const hasVisibleItems = activeGroups.some(group => (group.items || []).length > 0)
  const identityMessage = radar?.identity_scope === 'UNAVAILABLE'
    ? 'Danh sách mã chi tiết chưa sẵn sàng.'
    : !hasVisibleItems ? 'Chưa có mã chi tiết trong phạm vi đang xem.' : ''

  return (
    <aside className="stock-v3-signal-rail stock-v3-radar" aria-label="CCC Radar thị trường">
      <header>
        <span className="stock-v3-section-kicker">CCC Radar</span>
        <strong>Tín hiệu thị trường</strong>
      </header>

      {radarError && !radar ? (
        <p className="stock-v3-radar-state is-error">{radarError}</p>
      ) : null}
      {radarError && radar ? (
        <p className="stock-v3-radar-state is-warning">Đang giữ trạng thái gần nhất · {radarError}</p>
      ) : null}
      {!radar && !radarError ? (
        <p className="stock-v3-radar-state">Đang tải trạng thái thị trường…</p>
      ) : null}
      {radar && !activeGroups.length ? (
        <p className="stock-v3-radar-state">Chưa có tín hiệu hiện tại cần chú ý.</p>
      ) : null}
      {radar && activeGroups.length > 0 && identityMessage ? (
        <p className="stock-v3-radar-state is-secondary">{identityMessage}</p>
      ) : null}

      <div className="stock-v3-radar-groups">
        {activeGroups.map((group) => (
          <section key={group.state} className={`stock-v3-radar-group is-${String(group.state).toLowerCase()}`}>
            <div className="stock-v3-radar-group-title">
              <strong>{STATE_LABELS[group.state] || group.state}</strong>
              <b>{group.total}</b>
            </div>
            {(group.items || []).slice(0, 4).map((item) => (
              <Link key={item.symbol} to={`/co-phieu/${item.symbol}`}>
                <strong>{item.symbol}</strong>
                <time>{shortTime(item.state_changed_at || item.event_at)}</time>
              </Link>
            ))}
            {Number(group.hidden) > 0 ? <small>+{group.hidden} mã khác</small> : null}
          </section>
        ))}
      </div>

      {radar?.identity_scope !== 'FULL_MARKET' ? (
        <Link className="stock-v3-radar-cta" to="/danh-sach">
          Quản lý phạm vi theo dõi
        </Link>
      ) : null}
    </aside>
  )
}
