import { Link } from 'react-router-dom'
import StockDetailContextPanel from './StockDetailContextPanel'
import StockDetailSignalRail from './StockDetailSignalRail'
import StockDetailTabs from './StockDetailTabs'

const SESSION_LABELS = {
  OPEN_AUCTION: 'ATO',
  AM_CONTINUOUS: 'Đang giao dịch',
  PM_CONTINUOUS: 'Đang giao dịch',
  CONTINUOUS: 'Đang giao dịch',
  LUNCH_BREAK: 'Nghỉ trưa',
  CLOSE_AUCTION: 'ATC',
  POST_TRADING: 'Sau phiên',
  CLOSED: 'Đóng cửa',
}

function describeMarketSession(quote, publicContext) {
  const raw = String(publicContext?.session_type || quote?.trading_session || '').trim().toUpperCase()
  if (!raw) return { label: 'Phiên chưa xác định', raw: '', semantic: false }
  if (SESSION_LABELS[raw]) return { label: SESSION_LABELS[raw], raw, semantic: true }
  return { label: 'Phiên chưa xác định', raw, semantic: false }
}

export default function StockDetailV3View({
  symbol,
  metadata,
  metadataLoading,
  quote,
  quoteLoading,
  quoteError,
  changeClass,
  formatNumber,
  formatPercent,
  chartContent,
  liveConnected,
  activeDetailTab,
  onActiveDetailTabChange,
  ready,
  user,
  accessLoading,
  accessError,
  access,
  publicContext,
  publicContextError,
  ccc,
  cccError,
  cccLoading,
  radar,
  radarError,
  financial,
  financialError,
  financialLoading,
  quarterly,
  quarterlyError,
  quarterlyLoading,
}) {
  const companyName = metadataLoading
    ? 'Đang tải thông tin doanh nghiệp…'
    : metadata?.display_name || metadata?.company_name || 'Thông tin doanh nghiệp chưa có'
  const exchange = quote?.exchange || metadata?.exchange || '—'
  const marketSession = describeMarketSession(quote, publicContext)

  return (
    <div className="stock-v3-page">
      <StockDetailSignalRail
        radar={radar}
        radarError={radarError}
      />

      <div className="stock-v3-workspace">
        <section className="stock-v3-identity" aria-labelledby="stock-v3-title">
          <div className="stock-v3-identity-copy">
            <div className="stock-v3-symbol-line">
              <h1 id="stock-v3-title">{symbol}</h1>
              <span>{exchange}</span>
              <span className={`stock-v3-session-badge${marketSession.semantic ? ' is-semantic' : ''}`}>
                {marketSession.label}
              </span>
            </div>
            <p>{companyName}</p>
            <small>
              Cập nhật {quote?.event_time || '—'}
            </small>
          </div>

          <div className="stock-v3-price-block" aria-busy={quoteLoading}>
            <span>Giá hiện tại</span>
            <div>
              <strong className={changeClass}>{quoteLoading ? '…' : formatNumber(quote?.last_price)}</strong>
              <b className={changeClass}>{quoteLoading ? 'Đang tải' : formatPercent(quote?.ratio_change)}</b>
            </div>
          </div>

          <Link className="stock-v3-back-link" to="/danh-sach">Về Scanner</Link>
        </section>

        {quoteError ? (
          <section className="stock-v3-error" role="alert">
            <strong>Không tải được Public Market Quote</strong>
            <p>{quoteError}</p>
          </section>
        ) : null}

        {publicContextError ? (
          <section className="stock-v3-error" role="status">
            <strong>Chưa tải được bối cảnh MA</strong>
            <p>{publicContextError}</p>
          </section>
        ) : null}

        <section className="stock-v3-chart-card" aria-label={`Biểu đồ kỹ thuật ${symbol}`}>
          <header className="stock-v3-chart-header">
            <h2>Diễn biến giá</h2>
          </header>
          {chartContent}
        </section>

        <StockDetailTabs
          symbol={symbol}
          quote={quote}
          quoteLoading={quoteLoading}
          formatNumber={formatNumber}
          metadata={metadata}
          publicContext={publicContext}
          ready={ready}
          user={user}
          accessLoading={accessLoading}
          accessError={accessError}
          access={access}
          ccc={ccc}
          cccError={cccError}
          cccLoading={cccLoading}
          financial={financial}
          financialError={financialError}
          financialLoading={financialLoading}
          quarterly={quarterly}
          quarterlyError={quarterlyError}
          quarterlyLoading={quarterlyLoading}
          activeTab={activeDetailTab}
          onActiveTabChange={onActiveDetailTabChange}
        />
      </div>

      <StockDetailContextPanel
        quote={quote}
        publicContext={publicContext}
        liveConnected={liveConnected}
        marketSession={marketSession}
      />
    </div>
  )
}
