import { Link } from 'react-router-dom'
import StockLogo from '../stock/StockLogo'
import { finiteNumber, signedDistanceForRow } from '../../lib/scannerFilters'
import { scannerSignalCue, scannerStateCue } from '../../lib/scannerData'

const MISSING = '—'

function formatNumber(value) {
  const number = finiteNumber(value)
  return number === null ? MISSING : new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(number)
}

function formatSignedPercent(value, decimals = 2) {
  const number = finiteNumber(value)
  if (number === null) return MISSING
  return `${number > 0 ? '+' : ''}${new Intl.NumberFormat('vi-VN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(number)}%`
}

function formatVolume(value) {
  const number = finiteNumber(value)
  if (number === null) return MISSING
  const magnitude = Math.abs(number)
  if (magnitude < 1000) return formatNumber(number)
  const unit = magnitude >= 1_000_000 ? 'M' : 'K'
  const scaled = number / (unit === 'M' ? 1_000_000 : 1000)
  const decimals = Math.abs(scaled) < 10 ? 2 : 1
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: decimals }).format(scaled)}${unit}`
}

function formatRvol(value) {
  const number = finiteNumber(value)
  return number === null ? MISSING : `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(number)}x`
}

function QuickMetrics({ stock }) {
  if (!stock.ccc) return MISSING
  const first = [
    finiteNumber(stock.rvol30) === null ? null : `RVOL30 ${formatRvol(stock.rvol30)}`,
    finiteNumber(stock.price15) === null ? null : `Price15 ${formatSignedPercent(stock.price15, 1)}`,
  ].filter(Boolean).join(' · ')
  const atc = [
    finiteNumber(stock.atcRvol) > 0 ? `ATC ${formatRvol(stock.atcRvol)}` : null,
    finiteNumber(stock.atcPriceImpactPct) ? formatSignedPercent(stock.atcPriceImpactPct, 1) : null,
  ].filter(Boolean).join(' · ')
  const second = atc || scannerStateCue(stock) || scannerSignalCue(stock)
  if (!first && !second) return MISSING
  return <span className="scanner-quick-metrics"><span>{first || second}</span>{first && second ? <small>{second}</small> : null}</span>
}

function SignalCue({ stock }) {
  const cue = scannerSignalCue(stock)
  return cue ? <span className="scanner-signal-cue" title={cue}>{cue}</span> : MISSING
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
        <span className="scanner-card-price"><strong>{formatNumber(stock.price)}</strong><small>{formatSignedPercent(stock.changePct)}</small></span>
      </span>
      <span className="scanner-card-grid">
        <span><small>Khối lượng</small><strong>{formatVolume(stock.volume)}</strong></span>
        <span><small>Cách MA200</small><strong>{formatSignedPercent(signedDistanceForRow(stock, 200), 1)}</strong></span>
        <span><small>{watchlist ? 'RVOL30' : 'Cách MA10'}</small><strong>{watchlist && stock.ccc ? formatRvol(stock.rvol30) : watchlist ? MISSING : formatSignedPercent(signedDistanceForRow(stock, 10), 1)}</strong></span>
        <span><small>Tín hiệu</small><strong><SignalCue stock={stock} /></strong></span>
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
                <td>{formatNumber(stock.price)}</td><td>{formatSignedPercent(stock.changePct)}</td><td>{formatVolume(stock.volume)}</td><td>{formatSignedPercent(signedDistanceForRow(stock, 200), 1)}</td>
                <td>{watchlist ? <QuickMetrics stock={stock} /> : formatSignedPercent(signedDistanceForRow(stock, 10), 1)}</td>
                <td><SignalCue stock={stock} /></td>
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
