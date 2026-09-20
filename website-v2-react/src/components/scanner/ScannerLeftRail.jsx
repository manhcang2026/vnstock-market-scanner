import ScannerFilterBuilder from './ScannerFilterBuilder'
import ScannerSortBuilder from './ScannerSortBuilder'

export default function ScannerLeftRail({ mode, filterBuilder, sortBuilder }) {
  const watchlist = mode === 'watchlist'

  return (
    <aside className="scanner-rail scanner-left-rail" aria-label={watchlist ? 'Danh sách của tôi' : 'Bộ lọc'}>
      <header>
        <span className="scanner-kicker">{watchlist ? 'CÁ NHÂN' : 'SCANNER'}</span>
        <h2>{watchlist ? 'Danh sách của tôi' : 'Bộ lọc'}</h2>
      </header>
      <div className="scanner-rail-body">
        {watchlist ? <p>Danh sách theo dõi sẽ xuất hiện khi nguồn dữ liệu tài khoản được kết nối.</p> : null}
        <ScannerFilterBuilder {...filterBuilder} />
        <div className="scanner-rail-divider" />
        <strong>Sắp xếp</strong>
        <ScannerSortBuilder {...sortBuilder} />
      </div>
    </aside>
  )
}
