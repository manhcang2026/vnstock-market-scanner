import { Link } from 'react-router-dom'

const detailTabs = [
  { id: 'overview', label: 'Tổng quan' },
  { id: 'technical', label: 'CCC Intelligence', locked: true },
  { id: 'fundamental', label: 'Cơ bản' },
  { id: 'reports', label: 'BCTC' },
]

const SIGNAL_LABELS = {
  NORMAL: 'Bình thường',
  WATCHING: 'Đang theo dõi',
  FLOW_APPEARING: 'Dòng tiền xuất hiện',
  FLOW_PRICE_CONFIRMED: 'Dòng tiền & giá xác nhận',
  MOMENTUM_MAINTAINED: 'Xu hướng duy trì',
  MOMENTUM_WEAKENING: 'Động lượng suy yếu',
  SELLING_PRESSURE: 'Áp lực bán',
}

const REASON_LABELS = {
  DAY_RVOL_ELEVATED: 'Khối lượng ngày cao hơn mức cùng thời điểm',
  RVOL15_ELEVATED: 'Khối lượng 15 phút đang cao hơn nhịp thông thường',
  RVOL15_STRONG: 'Khối lượng 15 phút tăng mạnh',
  RVOL30_ELEVATED: 'Khối lượng 30 phút đang cao hơn nhịp thông thường',
  RVOL30_STRONG: 'Khối lượng 30 phút tăng mạnh',
  PRICE5_UP: 'Giá 5 phút đang tăng',
  PRICE5_STRONG_UP: 'Giá 5 phút tăng mạnh',
  PRICE5_DOWN: 'Giá 5 phút đang giảm',
  PRICE5_STRONG_DOWN: 'Giá 5 phút giảm mạnh',
  PRICE15_UP: 'Giá 15 phút đang tăng',
  PRICE15_STRONG_UP: 'Giá 15 phút tăng mạnh',
  PRICE15_DOWN: 'Giá 15 phút đang giảm',
  PRICE15_STRONG_DOWN: 'Giá 15 phút giảm mạnh',
  HIGH_VOLUME_PRICE_ABSORPTION: 'Khối lượng cao nhưng biến động giá đang được hấp thụ',
  ATO_RVOL_ELEVATED: 'Khối lượng ATO cao hơn thông thường',
  ATO_RVOL_STRONG: 'Khối lượng ATO tăng mạnh',
  ATO_GAP_UP: 'Giá ATO tạo khoảng tăng',
  ATO_GAP_STRONG_UP: 'Giá ATO tạo khoảng tăng mạnh',
  ATO_GAP_DOWN: 'Giá ATO tạo khoảng giảm',
  ATO_GAP_STRONG_DOWN: 'Giá ATO tạo khoảng giảm mạnh',
  ATC_RVOL_ELEVATED: 'Khối lượng ATC cao hơn thông thường',
  ATC_RVOL_STRONG: 'Khối lượng ATC tăng mạnh',
  ATC_PRICE_UP: 'Giá tăng trong ATC',
  ATC_PRICE_STRONG_UP: 'Giá tăng mạnh trong ATC',
  ATC_PRICE_DOWN: 'Giá chịu áp lực giảm trong ATC',
  ATC_PRICE_STRONG_DOWN: 'Giá chịu áp lực giảm mạnh trong ATC',
  ATC_VOLUME_SHARE_HIGH: 'Tỷ trọng khối lượng ATC ở mức cao',
  ATC_VOLUME_SHARE_STRONG: 'Tỷ trọng khối lượng ATC tăng mạnh',
  ABOVE_MA10: 'Giá đang trên MA10',
  BELOW_MA10: 'Giá đang dưới MA10',
  ABOVE_MA200: 'Giá đang trên MA200',
  BELOW_MA200: 'Giá đang dưới MA200',
  BASELINE_INCOMPLETE: 'Baseline chưa đủ số phiên mục tiêu',
  METRICS_UNTRUSTED: 'Một phần chỉ số đang ở trạng thái chưa tin cậy',
}

const FRESHNESS_LABELS = {
  CURRENT: 'Mới nhất',
  LAGGING: 'Chậm 1 kỳ',
  STALE: 'Dữ liệu cũ',
  NO_DATA: 'Chưa có dữ liệu',
}

function Metric({ label, value, supporting }) {
  return (
    <article className="stock-v3-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {supporting ? <small>{supporting}</small> : null}
    </article>
  )
}

function formatValue(value, digits = 2, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: digits }).format(Number(value))}${suffix}`
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${formatValue(number, 2, '%')}`
}

function moneyBillions(value) {
  return value === null || value === undefined ? '—' : `${formatValue(value, 0)} tỷ`
}

function CccPanel({ ready, user, accessLoading, accessError, access, ccc, cccError, cccLoading }) {
  if (!ready || accessLoading) return <div className="stock-v3-tab-message"><strong>Đang kiểm tra phạm vi CCC…</strong></div>
  if (accessError || (cccError && !ccc)) return <div className="stock-v3-tab-message"><strong className="is-error">{accessError || cccError}</strong></div>
  if (!user || !access?.technical_allowed) {
    return (
      <div className="stock-v3-ccc-lock">
        <span aria-hidden="true">🔒</span>
        <strong>Mã này chưa nằm trong phạm vi CCC Technical của bạn.</strong>
        <p>Biểu đồ, MA, dữ liệu cơ bản và BCTC vẫn được sử dụng miễn phí.</p>
        <Link to="/danh-sach">Quản lý / thay mã trong danh sách</Link>
      </div>
    )
  }
  if (cccLoading || !ccc) return <div className="stock-v3-tab-message"><strong>Đang tải CCC Intelligence…</strong></div>

  const reasons = (ccc.reason_codes || []).map(code => REASON_LABELS[code] || 'Có thêm điều kiện kỹ thuật từ CCC Engine')
  const showAuction = [ccc.ato_rvol, ccc.atc_rvol, ccc.atc_price_impact_pct].some(value => value !== null && value !== undefined)
  return (
    <div className="stock-v3-ccc-panel">
      {cccError ? <p className="stock-v3-inline-warning">Đang giữ trạng thái gần nhất · {cccError}</p> : null}
      <section className={`stock-v3-ccc-state is-${String(ccc.signal_direction || 'neutral').toLowerCase()}`}>
        <span>CCC Current State</span>
        <h3>{SIGNAL_LABELS[ccc.signal_state] || ccc.signal_state || '—'}</h3>
        <div><b>{ccc.signal_direction || 'NEUTRAL'}</b><strong>Mức {ccc.signal_level ?? '—'}</strong></div>
        {ccc.signal_summary_vi ? <p>{ccc.signal_summary_vi}</p> : null}
        {ccc.state_changed_at ? <small>Đổi trạng thái: {new Date(ccc.state_changed_at).toLocaleString('vi-VN')}</small> : null}
      </section>
      <section>
        <h3>Dòng tiền</h3>
        <div className="stock-v3-intel-grid">
          <Metric label="DayRVOL" value={formatValue(ccc.day_rvol, 2, 'x')} />
          <Metric label="RVOL15" value={formatValue(ccc.rvol15, 2, 'x')} />
          <Metric label="RVOL30" value={formatValue(ccc.rvol30, 2, 'x')} />
          <Metric label="Baseline" value={`${ccc.baseline_sessions_used ?? '—'}/${ccc.baseline_target_sessions ?? '—'} phiên`} supporting={ccc.metrics_trusted ? 'Dữ liệu tin cậy' : ccc.quality_status || 'Đang đánh giá'} />
        </div>
      </section>
      <section>
        <h3>Động lượng</h3>
        <div className="stock-v3-intel-grid is-two">
          <Metric label="Price5" value={formatPercent(ccc.price5_pct)} />
          <Metric label="Price15" value={formatPercent(ccc.price15_pct)} />
        </div>
      </section>
      {showAuction ? (
        <section>
          <h3>Auction Intelligence</h3>
          <div className="stock-v3-intel-grid">
            <Metric label="ATO RVOL" value={formatValue(ccc.ato_rvol, 2, 'x')} supporting={ccc.ato_baseline_quality} />
            <Metric label="ATC RVOL" value={formatValue(ccc.atc_rvol, 2, 'x')} supporting={ccc.atc_baseline_quality} />
            <Metric label="Tác động giá ATC" value={formatPercent(ccc.atc_price_impact_pct)} />
          </div>
        </section>
      ) : null}
      {reasons.length ? (
        <section className="stock-v3-reasons">
          <h3>Vì sao CCC đang đánh giá như vậy?</h3>
          <ul>{reasons.map((reason, index) => <li key={`${reason}-${index}`}>{reason}</li>)}</ul>
        </section>
      ) : null}
    </div>
  )
}

function FundamentalPanel({ financial, financialLoading, financialError }) {
  if (financialLoading) return <div className="stock-v3-tab-message"><strong>Đang tải dữ liệu cơ bản…</strong></div>
  if (financialError) return <div className="stock-v3-tab-message"><strong className="is-error">{financialError}</strong></div>
  const row = financial?.financial
  const score = financial?.score
  if (!row) return <div className="stock-v3-tab-message is-neutral"><strong>financial_latest chưa có bản ghi cho mã này.</strong></div>
  return (
    <div className="stock-v3-fundamental">
      <section className="stock-v3-score-card">
        <span>Điểm cơ bản</span>
        <strong>{score?.label || 'Chưa đủ dữ liệu'}</strong>
        <small>Chấm được {score?.available || 0}/100 điểm tối đa · độ phủ {score?.coverage || 0}%</small>
      </section>
      <div className="stock-v3-fundamental-grid">
        <Metric label="Ngành" value={row.website_group || '—'} />
        <Metric label="P/E" value={formatValue(row.pe, 2, 'x')} />
        <Metric label="P/B" value={formatValue(row.pb, 2, 'x')} />
        <Metric label="ROE" value={formatPercent(row.roea_pct)} />
        <Metric label="ROA" value={formatPercent(row.roaa_pct)} />
        <Metric label="LNST YoY" value={formatPercent(row.profit_yoy_pct)} />
        <Metric label="Doanh thu / thu nhập YoY" value={formatPercent(row.income_yoy_pct)} />
        <Metric label="LNST QoQ" value={formatPercent(row.profit_qoq_pct)} />
        <Metric label="Nợ / vốn chủ" value={formatPercent(row.debt_equity_pct)} />
        <Metric label="Nợ / tài sản" value={formatPercent(row.debt_assets_pct)} />
        <Metric label="Độ mới" value={FRESHNESS_LABELS[row.freshness_status] || row.freshness_status || row.data_status || '—'} />
      </div>
      {score?.parts?.length ? (
        <details className="stock-v3-score-details">
          <summary>Xem cấu phần điểm</summary>
          {score.parts.map(part => (
            <div key={part.name}><span>{part.name}</span><strong>{part.earned}/{part.maximum}</strong></div>
          ))}
        </details>
      ) : null}
    </div>
  )
}

function ReportsPanel({ symbol, quarterly, quarterlyLoading, quarterlyError }) {
  const bctcUrl = `https://finance.vietstock.vn/${encodeURIComponent(symbol)}/tai-chinh.htm?tab=BCTT`
  return (
    <div className="stock-v3-reports">
      {quarterlyLoading ? <div className="stock-v3-tab-message"><strong>Đang tải lịch sử quý…</strong></div> : null}
      {quarterlyError ? <div className="stock-v3-tab-message"><strong className="is-error">{quarterlyError}</strong></div> : null}
      {!quarterlyLoading && !quarterlyError && !(quarterly || []).length ? (
        <div className="stock-v3-tab-message is-neutral"><strong>financial_quarterly chưa có bản ghi cho mã này.</strong></div>
      ) : null}
      {(quarterly || []).length ? (
        <div className="stock-v3-quarter-table"><table><thead><tr><th>Kỳ</th><th>Doanh thu / thu nhập</th><th>LNST</th><th>YoY</th><th>ROE</th></tr></thead><tbody>
          {quarterly.map((row, index) => <tr key={`${row.period || `${row.year}-Q${row.quarter}`}-${index}`}><td>{row.period || `${row.year} Q${row.quarter}`}</td><td>{moneyBillions(row.income_bil_vnd)}</td><td>{moneyBillions(row.parent_net_profit_bil_vnd ?? row.net_profit_bil_vnd)}</td><td>{formatPercent(row.profit_yoy_pct)}</td><td>{formatPercent(row.roea_pct)}</td></tr>)}
        </tbody></table></div>
      ) : null}
      <div className="stock-v3-bctc-link"><div><strong>Báo cáo tài chính {symbol}</strong><span>Nguồn ngoài: VietstockFinance</span></div><a href={bctcUrl} target="_blank" rel="noopener noreferrer">Xem BCTC trên Vietstock ↗</a></div>
    </div>
  )
}

export default function StockDetailTabs({
  symbol,
  quote,
  quoteLoading,
  formatNumber,
  metadata,
  publicContext,
  ready,
  user,
  accessLoading,
  accessError,
  access,
  ccc,
  cccError,
  cccLoading,
  financial,
  financialError,
  financialLoading,
  quarterly,
  quarterlyError,
  quarterlyLoading,
  activeTab,
  onActiveTabChange,
}) {
  const unlocked = Boolean(access?.technical_allowed)

  return (
    <section className="stock-v3-detail-tabs">
      <div className="stock-v3-tab-list" role="tablist" aria-label="Thông tin chi tiết cổ phiếu">
        {detailTabs.map(tab => (
          <button key={tab.id} id={`detail-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`detail-panel-${tab.id}`} className={activeTab === tab.id ? 'is-active' : ''} onClick={() => onActiveTabChange(tab.id)}>
            {tab.label}{tab.locked && !unlocked ? ' 🔒' : ''}
          </button>
        ))}
      </div>

      <div id={`detail-panel-${activeTab}`} className="stock-v3-tab-panel" role="tabpanel" aria-labelledby={`detail-tab-${activeTab}`}>
        {activeTab === 'overview' ? (
          <div className="stock-v3-overview-grid" aria-busy={quoteLoading}>
            <Metric label="Tham chiếu" value={quoteLoading ? '…' : formatNumber(quote?.ref_price)} />
            <Metric label="Mở cửa" value={quoteLoading ? '…' : formatNumber(quote?.open)} />
            <Metric label="Cao nhất" value={quoteLoading ? '…' : formatNumber(quote?.high)} />
            <Metric label="Thấp nhất" value={quoteLoading ? '…' : formatNumber(quote?.low)} />
            <Metric label="Giá hiện tại" value={quoteLoading ? '…' : formatNumber(quote?.last_price)} />
            <Metric label="KL lũy kế" value={quoteLoading ? '…' : formatNumber(quote?.total_volume)} />
            <Metric label="MA10" value={formatNumber(publicContext?.ma10)} supporting={`Cách ${formatPercent(publicContext?.distance_ma10_pct)}`} />
            <Metric label="MA200" value={formatNumber(publicContext?.ma200)} supporting={`Cách ${formatPercent(publicContext?.distance_ma200_pct)}`} />
            <Metric label="Sàn" value={quote?.exchange || metadata?.exchange || '—'} />
            <Metric label="Ngành" value={financial?.financial?.website_group || metadata?.website_group || '—'} />
          </div>
        ) : null}
        {activeTab === 'technical' ? <CccPanel {...{ ready, user, accessLoading, accessError, access, ccc, cccError, cccLoading }} /> : null}
        {activeTab === 'fundamental' ? <FundamentalPanel {...{ financial, financialLoading, financialError }} /> : null}
        {activeTab === 'reports' ? <ReportsPanel {...{ symbol, quarterly, quarterlyLoading, quarterlyError }} /> : null}
      </div>
    </section>
  )
}
