import { Link } from 'react-router-dom'
import StockLogo from '../stock/StockLogo'

const MISSING = '—'

function StockIdentity({ stock }) {
  return (
    <span className="scanner-identity">
      <StockLogo symbol={stock.symbol} />
      <span className="scanner-identity-copy">
        <span><strong>{stock.symbol}</strong><small>{stock.exchange || MISSING}</small></span>
        <span className="scanner-company-name">{stock.display_name || stock.company_name || stock.symbol}</span>
      </span>
    </span>
  )
}

function StockListCard({ stock, mode }) {
  const watchlist = mode === 'watchlist'
  return (
    <Link className="scanner-stock-card" to={`/co-phieu/${encodeURIComponent(stock.symbol)}`} aria-label={`Xem cổ phiếu ${stock.symbol}`}>
      <span className="scanner-card-top">
        <StockIdentity stock={stock} />
        <span className="scanner-card-price"><strong>{MISSING}</strong><small>{MISSING}</small></span>
      </span>
      <span className="scanner-card-grid">
        <span><small>Khối lượng</small><strong>{MISSING}</strong></span>
        <span><small>Cách MA200</small><strong>{MISSING}</strong></span>
        <span><small>{watchlist ? 'RVOL30' : 'Cách MA10'}</small><strong>{MISSING}</strong></span>
        <span><small>Tín hiệu</small><strong>{MISSING}</strong></span>
      </span>
    </Link>
  )
}

export default function StockList({ rows, mode, emptyMessage }) {
  const watchlist = mode === 'watchlist'
  return (
    <>
      <div className="scanner-table-wrap">
        <table className="scanner-table">
          <thead><tr>
            <th scope="col">CÔNG TY</th>
            <th scope="col">GIÁ</th>
            <th scope="col">% THAY ĐỔI</th>
            <th scope="col">KHỐI LƯỢNG</th>
            <th scope="col">CÁCH MA200</th>
            <th scope="col">{watchlist ? 'CCC NHANH' : 'CÁCH MA10'}</th>
            <th scope="col">TÍN HIỆU</th>
          </tr></thead>
          <tbody>
            {rows.length ? rows.map((stock) => (
              <tr key={stock.symbol}>
                <td><Link className="scanner-company-link" to={`/co-phieu/${encodeURIComponent(stock.symbol)}`} aria-label={`Xem cổ phiếu ${stock.symbol}`}><StockIdentity stock={stock} /></Link></td>
                <td>{MISSING}</td><td>{MISSING}</td><td>{MISSING}</td><td>{MISSING}</td>
                <td>{watchlist ? <span className="scanner-quick-metrics"><span>RVOL30 {MISSING} · Price15 {MISSING}</span><small>Current State / ATC {MISSING}</small></span> : MISSING}</td>
                <td>{MISSING}</td>
              </tr>
            )) : <tr><td colSpan={7} className="scanner-table-empty">{emptyMessage}</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="scanner-cards">
        {rows.length ? rows.map((stock) => <StockListCard key={stock.symbol} stock={stock} mode={mode} />) : <p className="scanner-card-empty">{emptyMessage}</p>}
      </div>
    </>
  )
}
