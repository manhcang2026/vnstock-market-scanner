import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import ScannerShell from '../components/scanner/ScannerShell'
import ScannerTabs from '../components/scanner/ScannerTabs'
import StockList from '../components/scanner/StockList'
import { publicSupabase } from '../lib/publicSupabase'
import { loadStockMetadata, normalizeSearchText } from '../lib/stockSearch'
import '../styles/scanner.css'

const PAGE_SIZE = 50

export default function ScannerPage() {
  const [params] = useSearchParams()
  const q = (params.get('q') || '').trim()
  const lookupUnavailable = params.get('lookup') === 'unavailable'
  const [tabState, setTabState] = useState(() => ({ query: q, value: q ? 'market' : 'watchlist' }))
  const activeTab = tabState.query === q ? tabState.value : q ? 'market' : 'watchlist'
  const [pageState, setPageState] = useState(() => ({ query: q, value: 1 }))
  const page = pageState.query === q ? pageState.value : 1
  const [metadata, setMetadata] = useState(() => ({ status: publicSupabase ? 'loading' : 'error', rows: [] }))
  const { user, ready } = useAuth()

  useEffect(() => {
    let active = true
    if (!publicSupabase) return undefined
    loadStockMetadata()
      .then((rows) => { if (active) setMetadata({ status: 'ready', rows }) })
      .catch(() => { if (active) setMetadata({ status: 'error', rows: [] }) })
    return () => { active = false }
  }, [])

  const matchingRows = useMemo(() => {
    if (!q) return metadata.rows
    const query = normalizeSearchText(q)
    return metadata.rows.filter((stock) => [stock.symbol, stock.display_name, stock.company_name]
      .some((value) => normalizeSearchText(value).includes(query)))
  }, [metadata.rows, q])
  const pageCount = Math.max(1, Math.ceil(matchingRows.length / PAGE_SIZE))
  const pageRows = matchingRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function changeTab(tab) {
    setTabState({ query: q, value: tab })
    setPageState({ query: q, value: 1 })
  }

  let marketEmpty = 'Chưa có mã cổ phiếu trong danh mục.'
  if (metadata.status === 'loading') marketEmpty = 'Đang tải danh mục cổ phiếu…'
  if (metadata.status === 'error') marketEmpty = 'Không thể tải danh mục cổ phiếu. Hãy thử lại sau.'
  if (metadata.status === 'ready' && q && !matchingRows.length) marketEmpty = `Không có mã phù hợp với “${q}”.`

  const watchlistMessage = !ready
    ? 'Đang kiểm tra tài khoản…'
    : user
      ? 'Chưa thể tải danh sách theo dõi: frontend hiện chưa có đường đọc Watchlist được xác nhận.'
      : 'Đăng nhập để xem danh sách cổ phiếu đã theo dõi.'

  return (
    <ScannerShell mode={activeTab}>
      <div className="scanner-heading">
        <span className="scanner-kicker">SCANNER / DANH SÁCH</span>
        <h1>Danh sách cổ phiếu</h1>
      </div>
      <ScannerTabs activeTab={activeTab} onChange={changeTab} />

      {activeTab === 'watchlist' ? (
        <div id="scanner-panel-watchlist" role="tabpanel" aria-labelledby="scanner-tab-watchlist" className="scanner-result-panel">
          <header className="scanner-result-header">
            <div><span className="scanner-kicker">ĐÃ THEO DÕI</span><h2>Danh sách của tôi</h2><p>Các mã bạn theo dõi sẽ hiển thị tại đây khi nguồn Watchlist được kết nối.</p></div>
          </header>
          {!user && ready ? <div className="scanner-state-action"><Link to="/dang-nhap">Đăng nhập</Link></div> : null}
          <StockList rows={[]} mode="watchlist" emptyMessage={watchlistMessage} />
        </div>
      ) : null}

      {activeTab === 'market' ? (
        <div id="scanner-panel-market" role="tabpanel" aria-labelledby="scanner-tab-market" className="scanner-result-panel">
          <header className="scanner-result-header">
            <div><span className="scanner-kicker">TOÀN THỊ TRƯỜNG</span><h2>Kết quả toàn thị trường</h2><p>{metadata.status === 'ready' ? `Tổng ${matchingRows.length} mã phù hợp · ${pageRows.length} mã trên trang này` : 'Danh mục mã cổ phiếu từ stock_metadata'}</p></div>
          </header>
          {q ? <p className="scanner-query-message">{lookupUnavailable ? <>Chưa thể kiểm tra chính xác mã <strong>{q}</strong> khi tìm kiếm. {metadata.status === 'ready' ? 'Các kết quả danh mục phù hợp hiển thị bên dưới.' : 'Hãy thử lại sau.'}</> : <>Không tìm thấy mã duy nhất cho <strong>{q}</strong>. {metadata.status === 'ready' ? 'Các kết quả danh mục phù hợp hiển thị bên dưới.' : 'Hãy thử lại sau.'}</>}</p> : null}
          <StockList rows={pageRows} mode="market" emptyMessage={marketEmpty} />
          {metadata.status === 'ready' && pageCount > 1 ? (
            <nav className="scanner-pagination" aria-label="Phân trang toàn thị trường">
              <button type="button" onClick={() => setPageState({ query: q, value: Math.max(1, page - 1) })} disabled={page === 1}>Trước</button>
              <span>Trang {page} / {pageCount}</span>
              <button type="button" onClick={() => setPageState({ query: q, value: Math.min(pageCount, page + 1) })} disabled={page === pageCount}>Sau</button>
            </nav>
          ) : null}
        </div>
      ) : null}

      {activeTab === 'advanced' ? (
        <div id="scanner-panel-advanced" role="tabpanel" aria-labelledby="scanner-tab-advanced" className="scanner-result-panel scanner-advanced-state">
          <span className="scanner-kicker">TÌM KIẾM NÂNG CAO</span>
          <h2>Một nơi cho nhiều cách tìm cổ phiếu</h2>
          <p>Bộ lọc nhiều điều kiện, sắp xếp nhiều tiêu chí và bộ lọc tạo bằng AI sẽ cùng dùng một công cụ kết quả ở bước tiếp theo.</p>
        </div>
      ) : null}
    </ScannerShell>
  )
}
