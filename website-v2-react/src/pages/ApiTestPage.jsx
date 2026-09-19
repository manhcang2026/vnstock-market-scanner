import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import PageHeader from '../components/ui/PageHeader'
import { fetchChart, fetchQuote, fetchTechnicalAccess } from '../lib/cccApi'
import '../styles/api-test.css'

function emptyResult(label) {
  return { label, state: 'idle', status: null, body: null }
}

function success(label, body) {
  return { label, state: 'ok', status: 200, body }
}

function failure(label, error) {
  return {
    label,
    state: 'error',
    status: error?.status || 0,
    body: error?.body || { message: error?.message || 'Unknown error' },
  }
}

function summarizeChart(chart) {
  const bars = Array.isArray(chart?.bars) ? chart.bars : []
  return {
    symbol: chart?.symbol,
    count: chart?.count ?? bars.length,
    source_counts: chart?.source_counts,
    first: bars[0] ?? null,
    last: bars.length ? bars[bars.length - 1] : null,
  }
}

export default function ApiTestPage() {
  const { user, accessToken, ready } = useAuth()
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState([
    emptyResult('Public Quote'),
    emptyResult('Technical Access'),
    emptyResult('Protected Chart'),
  ])

  async function runTests() {
    setRunning(true)
    setResults([
      { ...emptyResult('Public Quote'), state: 'running' },
      { ...emptyResult('Technical Access'), state: 'running' },
      { ...emptyResult('Protected Chart'), state: 'running' },
    ])

    let quoteResult
    let accessResult
    let chartResult

    try {
      const quote = await fetchQuote('HPG')
      quoteResult = success('Public Quote', {
        symbol: quote?.symbol,
        trading_date: quote?.trading_date,
        event_time: quote?.event_time,
        last_price: quote?.last_price,
        total_volume: quote?.total_volume,
        ratio_change: quote?.ratio_change,
        source: quote?.source,
      })
    } catch (error) {
      quoteResult = failure('Public Quote', error)
    }

    try {
      const access = await fetchTechnicalAccess('HPG', { token: accessToken })
      accessResult = success('Technical Access', access)
    } catch (error) {
      accessResult = failure('Technical Access', error)
    }

    try {
      const chart = await fetchChart(
        'HPG',
        'from=2026-09-15&to=2026-09-15&resolution=1',
        { token: accessToken },
      )
      chartResult = success('Protected Chart', summarizeChart(chart))
    } catch (error) {
      chartResult = failure('Protected Chart', error)
    }

    setResults([quoteResult, accessResult, chartResult])
    setRunning(false)
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="DEV CHECKPOINT · không phải UI production"
        title="HPG API bridge test"
        description="Kiểm tra React → /api/v2 cùng origin → dev proxy hoặc Nginx → CCC realtime API → Supabase entitlement."
      />

      <section className="api-test-summary">
        <div>
          <small>Supabase session</small>
          <strong>{ready ? (user ? 'Đã đăng nhập' : 'Chưa đăng nhập') : 'Đang kiểm tra…'}</strong>
          <span>{user?.email || 'Không có user'}</span>
        </div>
        <div>
          <small>JWT</small>
          <strong>{accessToken ? 'Có' : 'Không'}</strong>
          <span>Token không được hiển thị</span>
        </div>
        <button type="button" onClick={runTests} disabled={running || !ready}>
          {running ? 'Đang test…' : 'Chạy test HPG'}
        </button>
      </section>

      <div className="api-test-grid">
        {results.map((result) => (
          <article className={`api-test-card is-${result.state}`} key={result.label}>
            <header>
              <div>
                <small>{result.label}</small>
                <strong>
                  {result.state === 'idle' ? 'Chưa chạy' : result.state === 'running' ? 'Đang gọi…' : `HTTP ${result.status}`}
                </strong>
              </div>
              <span className="api-test-state">
                {result.state === 'ok' ? 'PASS' : result.state === 'error' ? 'FAIL' : '—'}
              </span>
            </header>
            <pre>{result.body ? JSON.stringify(result.body, null, 2) : '—'}</pre>
          </article>
        ))}
      </div>

      <section className="panel">
        <div className="panel-body">
          <p>
            Kỳ vọng khi đang đăng nhập tài khoản VIP hiện tại: Quote = HTTP 200, Access = HTTP 200 với
            technical_allowed=true, Chart = HTTP 200 và có bars. Trang dev này sẽ được bỏ trước production cutover.
          </p>
        </div>
      </section>
    </div>
  )
}
