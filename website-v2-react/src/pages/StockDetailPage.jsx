import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import PriceVolumeChart from '../components/stock/PriceVolumeChart'
import { fetchChart, fetchQuote, fetchTechnicalAccess } from '../lib/cccApi'
import '../styles/stock-detail.css'

const SYMBOL_RE = /^[A-Z0-9]{2,12}$/

function normalizeSymbol(value) {
  return String(value || '').trim().toUpperCase()
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('vi-VN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value))
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${formatNumber(n, 2)}%`
}

function abortError(error) {
  return error?.name === 'AbortError'
}

export default function StockDetailPage() {
  const params = useParams()
  const symbol = normalizeSymbol(params.symbol)
  const validSymbol = SYMBOL_RE.test(symbol)
  const { user, accessToken, ready } = useAuth()

  const [quoteState, setQuoteState] = useState({ symbol: '', data: null, error: '' })
  const [accessState, setAccessState] = useState({ symbol: '', data: null, error: '' })
  const [chartState, setChartState] = useState({ key: '', data: null, error: '' })

  useEffect(() => {
    if (!validSymbol) return undefined

    const controller = new AbortController()
    fetchQuote(symbol, { signal: controller.signal })
      .then((data) => setQuoteState({ symbol, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setQuoteState({
          symbol,
          data: null,
          error: error?.message || 'Không tải được giá thị trường.',
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol])

  useEffect(() => {
    if (!validSymbol || !ready || !accessToken) return undefined

    const controller = new AbortController()
    fetchTechnicalAccess(symbol, { token: accessToken, signal: controller.signal })
      .then((data) => setAccessState({ symbol, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setAccessState({
          symbol,
          data: null,
          error: error?.message || 'Không kiểm tra được quyền kỹ thuật.',
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol, ready, accessToken])

  const quote = quoteState.symbol === symbol ? quoteState.data : null
  const quoteError = quoteState.symbol === symbol ? quoteState.error : ''
  const fetchedAccess = accessState.symbol === symbol ? accessState.data : null
  const accessError = accessState.symbol === symbol ? accessState.error : ''

  const access = useMemo(() => {
    if (!ready) return null
    if (!user || !accessToken) {
      return {
        technical_allowed: false,
        reason: 'AUTH_REQUIRED',
        plan_code: null,
      }
    }
    return fetchedAccess
  }, [ready, user, accessToken, fetchedAccess])

  const chartDate = quote?.trading_date || ''
  const chartKey = `${symbol}:${chartDate}`

  useEffect(() => {
    if (!validSymbol || !chartDate || !accessToken || !access?.technical_allowed) return undefined

    const controller = new AbortController()
    const query = `from=${encodeURIComponent(chartDate)}&to=${encodeURIComponent(chartDate)}&resolution=1`

    fetchChart(symbol, query, { token: accessToken, signal: controller.signal })
      .then((data) => setChartState({ key: chartKey, data, error: '' }))
      .catch((error) => {
        if (abortError(error)) return
        setChartState({
          key: chartKey,
          data: null,
          error: error?.message || 'Không tải được biểu đồ.',
        })
      })

    return () => controller.abort()
  }, [symbol, validSymbol, chartDate, chartKey, accessToken, access?.technical_allowed])

  if (!validSymbol) {
    return (
      <div className="page">
        <section className="stock-error-panel">
          <strong>Mã chứng khoán không hợp lệ</strong>
          <p>Hãy nhập mã từ 2 đến 12 ký tự chữ hoặc số.</p>
          <Link to="/danh-sach">Về Bộ quét</Link>
        </section>
      </div>
    )
  }

  const quoteLoading = !quote && !quoteError
  const changeClass = Number(quote?.ratio_change || 0) > 0
    ? 'is-positive'
    : Number(quote?.ratio_change || 0) < 0
      ? 'is-negative'
      : ''

  const chart = chartState.key === chartKey ? chartState.data : null
  const chartError = chartState.key === chartKey ? chartState.error : ''
  const bars = Array.isArray(chart?.bars) ? chart.bars : []

  const accessLoading = ready && user && !fetchedAccess && !accessError

  return (
    <div className="page stock-detail-page">
      <section className="stock-identity">
        <div className="stock-identity-main">
          <div className="stock-symbol-row">
            <strong>{symbol}</strong>
            {quote?.exchange ? <span>{quote.exchange}</span> : null}
            {quote?.trading_session ? <span>Phiên {quote.trading_session}</span> : null}
          </div>
          <p>
            Public Market Quote · nguồn {quote?.source || 'SSI'} · phiên {quote?.trading_date || '—'}
          </p>
        </div>
        <Link className="back-to-scanner" to="/danh-sach">← Bộ quét</Link>
      </section>

      {quoteError ? (
        <section className="stock-error-panel">
          <strong>Không tải được Public Market Quote</strong>
          <p>{quoteError}</p>
        </section>
      ) : (
        <section className="quote-strip" aria-busy={quoteLoading}>
          <article className="quote-primary">
            <small>Giá hiện tại</small>
            <strong className={changeClass}>{quoteLoading ? '…' : formatNumber(quote?.last_price)}</strong>
            <span className={changeClass}>{quoteLoading ? 'Đang tải' : formatPercent(quote?.ratio_change)}</span>
          </article>
          <article>
            <small>Khối lượng lũy kế</small>
            <strong>{quoteLoading ? '…' : formatNumber(quote?.total_volume)}</strong>
            <span>{quote?.event_time || '—'}</span>
          </article>
          <article>
            <small>Tham chiếu</small>
            <strong>{quoteLoading ? '…' : formatNumber(quote?.ref_price)}</strong>
            <span>SSI_STREAM</span>
          </article>
          <article>
            <small>Trong phiên</small>
            <strong>{quoteLoading ? '…' : `${formatNumber(quote?.low)} – ${formatNumber(quote?.high)}`}</strong>
            <span>O {formatNumber(quote?.open)} · C {formatNumber(quote?.close)}</span>
          </article>
        </section>
      )}

      <section className="stock-detail-grid">
        <div className="stock-main-column">
          <section className="detail-card">
            <header className="detail-card-header">
              <div>
                <span className="detail-eyebrow">Price / Volume</span>
                <h2>Biểu đồ trong phiên</h2>
              </div>
              {chart ? (
                <div className="chart-source">
                  {chart.count} bars · {Object.keys(chart.source_counts || {}).join(', ') || 'SSI'}
                </div>
              ) : null}
            </header>

            {!ready ? (
              <div className="detail-state">Đang kiểm tra phiên đăng nhập…</div>
            ) : !user ? (
              <div className="technical-lock">
                <strong>Đăng nhập để mở vùng kỹ thuật</strong>
                <p>Giá thị trường vẫn công khai. Biểu đồ kỹ thuật được kiểm tra quyền ở server.</p>
                <Link to="/dang-nhap">Đăng nhập</Link>
              </div>
            ) : accessLoading ? (
              <div className="detail-state">Đang kiểm tra technical entitlement…</div>
            ) : accessError ? (
              <div className="detail-state is-error">{accessError}</div>
            ) : access && !access.technical_allowed ? (
              <div className="technical-lock">
                <strong>CCC Technical Intelligence ngoài phạm vi hiện tại</strong>
                <p>Public quote vẫn hiển thị. Backend không trả technical payload cho mã ngoài entitlement.</p>
                <span>{access.reason || 'OUTSIDE_ENTITLEMENT'}</span>
              </div>
            ) : chartError ? (
              <div className="detail-state is-error">{chartError}</div>
            ) : !chart ? (
              <div className="detail-state">Đang tải biểu đồ giá/khối lượng…</div>
            ) : (
              <PriceVolumeChart bars={bars} />
            )}
          </section>
        </div>

        <section className="detail-card signal-card">
          <header className="detail-card-header">
            <div>
              <span className="detail-eyebrow">CCC Technical Intelligence</span>
              <h2>Trạng thái CCC V2</h2>
            </div>
          </header>

          {!ready ? (
            <div className="signal-state-box is-neutral">Đang kiểm tra phiên…</div>
          ) : !user ? (
            <div className="signal-state-box is-locked">
              <strong>Đăng nhập để xem</strong>
              <span>Signal state là protected technical intelligence.</span>
            </div>
          ) : accessLoading ? (
            <div className="signal-state-box is-neutral">Đang kiểm tra quyền…</div>
          ) : access?.technical_allowed ? (
            <>
              <div className="signal-state-box is-pending">
                <strong>Chờ Signal Engine V2 output</strong>
                <span>Không dùng lại ý nghĩa 2/4 · 3/4 · 4/4 của V1.</span>
              </div>
              <div className="signal-heat-placeholder" aria-label="CCC heat bar đang chờ engine">
                <span />
                <span />
                <span />
                <span />
              </div>
              <dl className="technical-meta">
                <div>
                  <dt>Quyền kỹ thuật</dt>
                  <dd>{access.reason || 'ALLOWED'}</dd>
                </div>
                <div>
                  <dt>Plan</dt>
                  <dd>{access.plan_code || '—'}</dd>
                </div>
                <div>
                  <dt>VIP tạm thời</dt>
                  <dd>{access.vip_day_active ? 'Đang hoạt động' : 'Không'}</dd>
                </div>
              </dl>
            </>
          ) : (
            <div className="signal-state-box is-locked">
              <strong>Ngoài phạm vi technical</strong>
              <span>{access?.reason || 'OUTSIDE_ENTITLEMENT'}</span>
            </div>
          )}
        </section>

        <section className="detail-card data-trust-card">
          <header className="detail-card-header">
            <div>
              <span className="detail-eyebrow">Data Trust</span>
              <h2>Dữ liệu phiên</h2>
            </div>
          </header>
          <dl className="technical-meta">
            <div>
              <dt>Quote source</dt>
              <dd>{quote?.source || '—'}</dd>
            </div>
            <div>
              <dt>Trading date</dt>
              <dd>{quote?.trading_date || '—'}</dd>
            </div>
            <div>
              <dt>Last event</dt>
              <dd>{quote?.event_time || '—'}</dd>
            </div>
            <div>
              <dt>Chart bars</dt>
              <dd>{chart?.count ?? '—'}</dd>
            </div>
          </dl>
        </section>
      </section>
    </div>
  )
}
