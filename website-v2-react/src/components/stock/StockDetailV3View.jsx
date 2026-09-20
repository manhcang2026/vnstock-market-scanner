import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { describeMarketSession } from '../../lib/marketSession'
import StockLogo from './StockLogo'
import StockDetailContextPanel from './StockDetailContextPanel'
import StockDetailSignalRail from './StockDetailSignalRail'
import StockDetailTabs from './StockDetailTabs'

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
  cccUnavailable,
  cccBlockedStatus,
  cccLoading,
  radar,
  radarError,
  radarUnavailable,
  radarBlockedStatus,
  financial,
  financialError,
  financialLoading,
  quarterly,
  quarterlyError,
  quarterlyLoading,
}) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    // Refresh only presentation of session/freshness; no data request is started here.
    const timer = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const companyName = metadataLoading
    ? 'Đang tải thông tin doanh nghiệp…'
    : metadata?.display_name || metadata?.company_name || 'Thông tin doanh nghiệp chưa có'
  const exchange = quote?.exchange || metadata?.exchange || '—'
  const marketSession = describeMarketSession(quote, publicContext, now)

  return (
    <div className="stock-v3-page">
      <div className="stock-v3-workspace">
        <section className="stock-v3-identity" aria-labelledby="stock-v3-title">
          <div className="stock-v3-identity-main">
            <StockLogo symbol={symbol} />
            <div className="stock-v3-identity-copy">
              <div className="stock-v3-symbol-line">
                <h1 id="stock-v3-title">{symbol}</h1>
                <span>{exchange}</span>
                <span className={`stock-v3-session-badge${marketSession.semantic ? ' is-semantic' : ''}`}>
                  {marketSession.label}
                </span>
              </div>
              <p title={companyName}>{companyName}</p>
              <small>Cập nhật {quote?.event_time || '—'}</small>
            </div>
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

        <section className="stock-v3-chart-card" aria-label={`Biểu đồ kỹ thuật ${symbol}`}>
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
          cccUnavailable={cccUnavailable}
          cccBlockedStatus={cccBlockedStatus}
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

      <StockDetailSignalRail
        radar={radar}
        radarError={radarError}
        radarUnavailable={radarUnavailable}
        radarBlockedStatus={radarBlockedStatus}
      />

      <StockDetailContextPanel
        quote={quote}
        publicContext={publicContext}
        publicContextError={publicContextError}
        liveConnected={liveConnected}
        marketSession={marketSession}
        now={now}
      />
    </div>
  )
}
