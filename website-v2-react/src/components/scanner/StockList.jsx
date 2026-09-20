import { Link } from 'react-router-dom'
import StockLogo from '../stock/StockLogo'
import { finiteNumber, formatSignedPct, signedDistanceForRow } from '../../lib/scannerFilters'

const MISSING = '—'

function formatNumber(value) {
  const number = finiteNumber(value)
  return number === null ? MISSING : new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(number)
}

function StockIdentity({ stock }) {
  return (
    <span className="scanner-identity">
      <StockLogo symbol={stock.symbol} />
      <span className="scanner-identity-copy">
        <span><strong>{stock.symbol}</strong><small>{stock.exchange || MISSING}</small></span>
        <span className="scanner-company-name">{stock.display_name || stock.company_name || MISSING}</span>
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
        <span className="scanner-card-price"><strong>{formatNumber(stock.price)}</strong><small>{formatSignedPct(stock.changePct)}</small></span>
      </span>
      <span className="scanner-card-grid">
        <span><small>Khối lượng</small><strong>{formatNumber(stock.volume)}</strong></span>
        <span><small>Cách MA200</small><strong>{formatSignedPct(signedDistanceForRow(stock, 200))}</strong></span>
        <span><small>{watchlist ? 'RVOL30' : 'Cách MA10'}</small><strong>{watchlist ? formatNumber(stock.rvol30) : formatSignedPct(signedDistanceForRow(stock, 10))}</strong></span>
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
                <td>{formatNumber(stock.price)}</td><td>{formatSignedPct(stock.changePct)}</td><td>{formatNumber(stock.volume)}</td><td>{formatSignedPct(signedDistanceForRow(stock, 200))}</td>
                <td>{watchlist ? <span className="scanner-quick-metrics"><span>RVOL30 {formatNumber(stock.rvol30)} · Price15 {formatNumber(stock.price15)}</span><small>Current State / ATC {MISSING}</small></span> : formatSignedPct(signedDistanceForRow(stock, 10))}</td>
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
