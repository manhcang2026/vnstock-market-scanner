function SignalRailState({ ready, user, accessLoading, accessError, access }) {
  if (!ready) return { tone: 'neutral', title: 'Đang kiểm tra phiên' }
  if (!user) return { tone: 'locked', title: 'Đăng nhập để xem CCC Tech' }
  if (accessLoading) return { tone: 'neutral', title: 'Đang kiểm tra quyền' }
  if (accessError) return { tone: 'warning', title: 'Chưa xác thực được quyền', copy: accessError }
  if (!access?.technical_allowed) {
    return {
      tone: 'locked',
      title: 'Ngoài phạm vi technical',
      copy: access?.reason || '',
    }
  }
  return {
    tone: 'pending',
    title: 'Đang chờ Signal Engine V2',
  }
}

export default function StockDetailSignalRail({ symbol, ready, user, accessLoading, accessError, access }) {
  const state = SignalRailState({ ready, user, accessLoading, accessError, access })

  return (
    <aside className="stock-v3-signal-rail" aria-label="Tín hiệu CCC gần đây">
      <header>
        <span className="stock-v3-section-kicker">Tín hiệu</span>
        <strong>Gần đây</strong>
      </header>
      <div className={`stock-v3-signal-item is-${state.tone}`}>
        <div className="stock-v3-signal-item-topline">
          <strong>{symbol}</strong>
          <span aria-hidden="true">—</span>
        </div>
        <p>{state.title}</p>
        {state.copy ? <small>{state.copy}</small> : null}
        <div className="stock-v3-heat-pending" aria-label="Signal level chưa có dữ liệu">
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>
    </aside>
  )
}
