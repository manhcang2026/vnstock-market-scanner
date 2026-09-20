export default function ScannerLeftRail({ mode }) {
  const watchlist = mode === 'watchlist'

  return (
    <aside className="scanner-rail scanner-left-rail" aria-label={watchlist ? 'Danh sách của tôi' : 'Bộ lọc'}>
      <header>
        <span className="scanner-kicker">{watchlist ? 'CÁ NHÂN' : 'TOÀN THỊ TRƯỜNG'}</span>
        <h2>{watchlist ? 'Danh sách của tôi' : 'Bộ lọc'}</h2>
      </header>
      <div className="scanner-rail-body">
        {watchlist ? (
          <p>Danh sách theo dõi sẽ xuất hiện khi nguồn dữ liệu tài khoản được kết nối.</p>
        ) : (
          <>
            <button type="button" disabled title="Bộ lọc sẽ được bổ sung ở bước tiếp theo">
              + Thêm điều kiện
            </button>
            <p>Chưa có điều kiện lọc nào được áp dụng.</p>
          </>
        )}
        <div className="scanner-rail-divider" />
        <strong>Sắp xếp</strong>
        <p>Sắp xếp nhiều tiêu chí sẽ được bổ sung ở bước tiếp theo.</p>
      </div>
    </aside>
  )
}
