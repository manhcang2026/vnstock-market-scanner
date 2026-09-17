import { useState } from 'react'

const contextTabs = [
  { id: 'data', label: 'Dữ liệu' },
  { id: 'tech', label: 'CCC Tech' },
  { id: 'market', label: 'Thị trường' },
]

function ContextRow({ label, value }) {
  return (
    <div className="stock-v3-context-row">
      <dt>{label}</dt>
      <dd>{value || '—'}</dd>
    </div>
  )
}

export default function StockDetailContextPanel({
  quote,
  chart,
  liveConnected,
  marketSession,
  ready,
  user,
  accessLoading,
  accessError,
  access,
}) {
  const [activeTab, setActiveTab] = useState('data')

  return (
    <aside className="stock-v3-context-panel" aria-label="Bối cảnh cổ phiếu">
      <div className="stock-v3-context-tabs" role="tablist" aria-label="Nhóm dữ liệu bối cảnh">
        {contextTabs.map((tab) => (
          <button
            key={tab.id}
            id={`context-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`context-panel-${tab.id}`}
            className={activeTab === tab.id ? 'is-active' : ''}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        id={`context-panel-${activeTab}`}
        className="stock-v3-context-body"
        role="tabpanel"
        aria-labelledby={`context-tab-${activeTab}`}
      >
        {activeTab === 'data' ? (
          <>
            <div className="stock-v3-context-heading">
              <span className={`stock-v3-status-dot${liveConnected ? ' is-live' : ''}`} />
              <div>
                <strong>{liveConnected ? 'Realtime' : 'Mất kết nối realtime'}</strong>
                <small>{liveConnected ? 'Kết nối dữ liệu đang hoạt động.' : 'Dữ liệu có thể chưa được cập nhật.'}</small>
              </div>
            </div>
            <dl>
              <ContextRow label="Trạng thái phiên" value={marketSession?.label} />
              <ContextRow label="Nguồn quote" value={quote?.source} />
              <ContextRow label="Ngày giao dịch" value={quote?.trading_date} />
              <ContextRow label="Sự kiện gần nhất" value={quote?.event_time} />
              {!marketSession?.semantic && marketSession?.raw ? (
                <ContextRow label="Mã phiên nguồn" value={marketSession.raw} />
              ) : null}
              <ContextRow label="Cập nhật hệ thống" value={quote?.updated_at} />
              <ContextRow label="Số nến" value={chart?.count ?? '—'} />
            </dl>
          </>
        ) : null}

        {activeTab === 'tech' ? (
          <div className="stock-v3-context-message">
            <span className="stock-v3-section-kicker">Protected</span>
            {!ready ? <strong>Đang kiểm tra phiên…</strong> : null}
            {ready && !user ? <strong>Đăng nhập để xem phạm vi CCC Tech</strong> : null}
            {ready && user && accessLoading ? <strong>Đang xác thực quyền tại server…</strong> : null}
            {accessError ? <strong>{accessError}</strong> : null}
            {access?.technical_allowed ? (
              <>
                <strong>Đang chờ Signal Engine V2</strong>
              </>
            ) : null}
            {ready && user && access && !access.technical_allowed ? (
              <>
                <strong>Ngoài phạm vi technical</strong>
                <p>{access.reason || 'OUTSIDE_ENTITLEMENT'}</p>
              </>
            ) : null}
          </div>
        ) : null}

        {activeTab === 'market' ? (
          <div className="stock-v3-context-message is-neutral">
            <strong>Chưa kết nối dữ liệu thị trường tổng hợp</strong>
          </div>
        ) : null}
      </div>
    </aside>
  )
}
