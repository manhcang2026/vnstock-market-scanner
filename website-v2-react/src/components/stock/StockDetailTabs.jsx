import { useState } from 'react'

const detailTabs = [
  { id: 'overview', label: 'Tổng quan' },
  { id: 'technical', label: 'Kỹ thuật' },
  { id: 'fundamental', label: 'Cơ bản' },
  { id: 'reports', label: 'BCTC' },
]

function Metric({ label, value, supporting }) {
  return (
    <article className="stock-v3-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {supporting ? <small>{supporting}</small> : null}
    </article>
  )
}

export default function StockDetailTabs({
  quote,
  quoteLoading,
  formatNumber,
  ready,
  user,
  accessLoading,
  accessError,
  access,
}) {
  const [activeTab, setActiveTab] = useState('overview')

  return (
    <section className="stock-v3-detail-tabs">
      <div className="stock-v3-tab-list" role="tablist" aria-label="Thông tin chi tiết cổ phiếu">
        {detailTabs.map((tab) => (
          <button
            key={tab.id}
            id={`detail-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`detail-panel-${tab.id}`}
            className={activeTab === tab.id ? 'is-active' : ''}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        id={`detail-panel-${activeTab}`}
        className="stock-v3-tab-panel"
        role="tabpanel"
        aria-labelledby={`detail-tab-${activeTab}`}
      >
        {activeTab === 'overview' ? (
          <div className="stock-v3-overview-grid" aria-busy={quoteLoading}>
            <Metric
              label="Tham chiếu"
              value={quoteLoading ? '…' : formatNumber(quote?.ref_price)}
            />
            <Metric
              label="Mở cửa"
              value={quoteLoading ? '…' : formatNumber(quote?.open)}
            />
            <Metric
              label="Cao nhất"
              value={quoteLoading ? '…' : formatNumber(quote?.high)}
            />
            <Metric
              label="Thấp nhất"
              value={quoteLoading ? '…' : formatNumber(quote?.low)}
            />
            <Metric
              label="KL lũy kế"
              value={quoteLoading ? '…' : formatNumber(quote?.total_volume)}
              supporting={quote?.event_time ? `Cập nhật ${quote.event_time}` : ''}
            />
          </div>
        ) : null}

        {activeTab === 'technical' ? (
          <div className="stock-v3-tab-message">
            {!ready ? <strong>Đang kiểm tra phiên đăng nhập…</strong> : null}
            {ready && !user ? (
              <>
                <strong>Đăng nhập để mở CCC Technical Intelligence</strong>
                <p>Public Market Quote vẫn hiển thị ở phía trên.</p>
              </>
            ) : null}
            {ready && user && accessLoading ? <strong>Đang kiểm tra technical entitlement…</strong> : null}
            {accessError ? <strong className="is-error">{accessError}</strong> : null}
            {access?.technical_allowed ? (
              <strong>Đang chờ Signal Engine V2</strong>
            ) : null}
            {ready && user && access && !access.technical_allowed ? (
              <>
                <strong>CCC Technical Intelligence ngoài phạm vi hiện tại</strong>
                <p>{access.reason || 'OUTSIDE_ENTITLEMENT'}</p>
              </>
            ) : null}
          </div>
        ) : null}

        {activeTab === 'fundamental' ? (
          <div className="stock-v3-tab-message is-neutral">
            <strong>Chưa kết nối dữ liệu cơ bản cho trang này</strong>
          </div>
        ) : null}

        {activeTab === 'reports' ? (
          <div className="stock-v3-tab-message is-neutral">
            <strong>Chưa kết nối dữ liệu BCTC</strong>
          </div>
        ) : null}
      </div>
    </section>
  )
}
