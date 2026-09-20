import { Link } from 'react-router-dom'
import ScannerMobileFilters from './ScannerMobileFilters'
import ScannerRightRail from './ScannerRightRail'
import StockList from './StockList'

export default function ScannerResults({ mode, rows, total, summary, sortSummary, metadataStatus, q, lookupUnavailable, watchlistMessage, signedOut, page, pageCount, onPage, filterBuilder, sortBuilder, activeCount, utility }) {
  const watchlist = mode === 'watchlist'
  const advanced = mode === 'advanced'
  let emptyMessage = 'Chưa có mã cổ phiếu trong danh mục.'
  if (metadataStatus === 'loading') emptyMessage = 'Đang tải danh mục cổ phiếu…'
  if (metadataStatus === 'error') emptyMessage = 'Không thể tải danh mục cổ phiếu. Hãy thử lại sau.'
  if (metadataStatus === 'ready' && q && total === 0) emptyMessage = `Không có mã phù hợp với “${q}”.`
  if (metadataStatus === 'ready' && total > 0 && !rows.length) emptyMessage = 'Không có mã phù hợp với các điều kiện đang áp dụng.'

  return (
    <div id={`scanner-panel-${mode}`} role="tabpanel" aria-labelledby={`scanner-tab-${mode}`} className="scanner-result-panel">
      <header className="scanner-result-header">
        <span className="scanner-kicker">{watchlist ? 'ĐÃ THEO DÕI' : advanced ? 'TÌM KIẾM NÂNG CAO' : 'TOÀN THỊ TRƯỜNG'}</span>
        <h2>{watchlist ? 'Danh sách của tôi' : advanced ? 'Kết quả tìm kiếm nâng cao' : 'Kết quả toàn thị trường'}</h2>
        {advanced ? <p>Bộ lọc nhiều điều kiện và sắp xếp ưu tiên dùng chung kết quả này. Bộ lọc AI sẽ được bổ sung sau.</p> : null}
        <p className="scanner-result-summary">{summary}</p>
        {sortSummary ? <p className="scanner-sort-summary">Sắp xếp: {sortSummary}</p> : null}
        <ScannerMobileFilters filterBuilder={filterBuilder} sortBuilder={sortBuilder} activeCount={activeCount} />
      </header>
      {!watchlist && q ? <p className="scanner-query-message">{lookupUnavailable ? <>Chưa thể kiểm tra chính xác mã <strong>{q}</strong> khi tìm kiếm. {metadataStatus === 'ready' ? 'Các kết quả danh mục phù hợp hiển thị bên dưới.' : 'Hãy thử lại sau.'}</> : <>Không tìm thấy mã duy nhất cho <strong>{q}</strong>. {metadataStatus === 'ready' ? 'Các kết quả danh mục phù hợp hiển thị bên dưới.' : 'Hãy thử lại sau.'}</>}</p> : null}
      <div className="scanner-mobile-utility"><ScannerRightRail active={utility.active} onChange={utility.onChange} idPrefix="scanner-mobile-utility" /></div>
      {watchlist && signedOut ? <div className="scanner-state-action"><Link to="/dang-nhap">Đăng nhập</Link></div> : null}
      <StockList rows={rows} mode={watchlist ? 'watchlist' : 'market'} emptyMessage={watchlist ? watchlistMessage : emptyMessage} />
      {!watchlist && metadataStatus === 'ready' && pageCount > 1 ? (
        <nav className="scanner-pagination" aria-label="Phân trang kết quả">
          <button type="button" onClick={() => onPage(Math.max(1, page - 1))} disabled={page === 1}>Trước</button>
          <span>Trang {page} / {pageCount}</span>
          <button type="button" onClick={() => onPage(Math.min(pageCount, page + 1))} disabled={page === pageCount}>Sau</button>
        </nav>
      ) : null}
    </div>
  )
}
