import { useState } from 'react'
import { loadStockMetadata, normalizeSearchText } from '../../lib/stockSearch'
import { replaceMyWatchlist } from '../../lib/accountData'
import {
  addDraftSymbol,
  areWatchlistsEqual,
  formatChangeRemaining,
  formatLimit,
  normalizeSymbols,
  watchlistFriendlyError,
} from '../../lib/accountHelpers'
import StockLogo from '../stock/StockLogo'

const dateFormatter = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' })
const dateTimeFormatter = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' })

function formatDate(value, withTime = false) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return (withTime ? dateTimeFormatter : dateFormatter).format(date)
}

function searchScore(row, query) {
  const symbol = normalizeSearchText(row.symbol)
  const name = normalizeSearchText(row.display_name || row.company_name)
  if (symbol === query) return 100
  if (symbol.startsWith(query)) return 90
  if (name.startsWith(query)) return 80
  if (name.includes(query)) return 70
  return 0
}

function SetupNotice({ state }) {
  if (String(state.status || '').toUpperCase() === 'GRACE') {
    return <p className="account-banner is-warning"><strong>Gói đang chờ gia hạn.</strong> DS vẫn được giữ đến {formatDate(state.grace_end_at, true)}.</p>
  }
  if (state.setup_active) {
    return <p className="account-banner"><strong>7 ngày khởi tạo miễn phí.</strong> Có thể thêm mã đến giới hạn gói mà chưa trừ lượt đổi đến {formatDate(state.setup_window_end, true)}.</p>
  }
  if (Number(state.upgrade_free_additions_remaining) > 0 && state.upgrade_free_additions_end_at) {
    return <p className="account-banner"><strong>7 ngày bổ sung sau nâng cấp.</strong> Còn {state.upgrade_free_additions_remaining} mã miễn phí đến {formatDate(state.upgrade_free_additions_end_at, true)}.</p>
  }
  return null
}

export default function AccountWatchlistCard({ watchlistState, access, onSaved }) {
  const watchlist = watchlistState.data || {}
  const authoritativeSymbols = normalizeSymbols(watchlist.symbols)
  const authoritativeKey = authoritativeSymbols.join('\u0000')
  const [editor, setEditor] = useState(null)
  const editorMatches = editor?.sourceKey === authoritativeKey
  const baseline = editorMatches ? editor.baseline : authoritativeSymbols
  const draft = editorMatches ? editor.draft : authoritativeSymbols
  const [query, setQuery] = useState('')
  const [metadata, setMetadata] = useState([])
  const [searchState, setSearchState] = useState({ loading: false, error: '' })
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState({ type: '', message: '' })

  const hasLimit = Object.prototype.hasOwnProperty.call(watchlist, 'watchlist_limit')
    || Object.prototype.hasOwnProperty.call(access || {}, 'watchlist_limit')
  const limit = Object.prototype.hasOwnProperty.call(watchlist, 'watchlist_limit')
    ? watchlist.watchlist_limit
    : access?.watchlist_limit
  const dirty = !areWatchlistsEqual(baseline, draft)
  const metadataMap = new Map()
  ;[...(watchlist.items || []), ...metadata].forEach((row) => {
    const symbol = String(row?.symbol || '').toUpperCase()
    if (symbol && !metadataMap.has(symbol)) metadataMap.set(symbol, row)
  })
  const normalizedQuery = normalizeSearchText(query)
  const suggestions = normalizedQuery
    ? metadata
      .map((row) => ({ row, score: searchScore(row, normalizedQuery) }))
      .filter(({ row, score }) => score > 0 && !draft.includes(String(row.symbol || '').toUpperCase()))
      .sort((left, right) => right.score - left.score || left.row.symbol.localeCompare(right.row.symbol))
      .slice(0, 7)
      .map(({ row }) => row)
    : []

  async function ensureMetadata() {
    if (metadata.length || searchState.loading) return
    setSearchState({ loading: true, error: '' })
    try {
      setMetadata(await loadStockMetadata())
      setSearchState({ loading: false, error: '' })
    } catch {
      setSearchState({ loading: false, error: 'Không tải được dữ liệu tìm mã lúc này.' })
    }
  }

  function addSymbol(row) {
    if (limit != null && draft.length >= Number(limit)) {
      setFeedback({ type: 'error', message: 'DS mã theo dõi đã đạt giới hạn của gói hiện tại.' })
      return
    }
    setEditor({ sourceKey: authoritativeKey, baseline, draft: addDraftSymbol(draft, row.symbol) })
    setQuery('')
    setFeedback({ type: '', message: '' })
  }

  async function save() {
    if (!dirty || saving) return
    setSaving(true)
    setFeedback({ type: '', message: '' })
    try {
      const result = await replaceMyWatchlist(normalizeSymbols(draft))
      const savedSymbols = normalizeSymbols(result.symbols || draft)
      await onSaved({ ...result, symbols: savedSymbols })
      setEditor(null)
      setFeedback({ type: 'success', message: 'Đã lưu DS mã theo dõi thành công.' })
    } catch (error) {
      setFeedback({ type: 'error', message: watchlistFriendlyError(error) })
    } finally {
      setSaving(false)
    }
  }

  const changeRemaining = Object.prototype.hasOwnProperty.call(watchlist, 'change_remaining')
    ? formatChangeRemaining(watchlist.change_remaining)
    : '—'
  const normalizedStatus = String(watchlist.status || '').toUpperCase()
  const statusLabel = watchlistState.loading
    ? 'Đang tải'
    : watchlist.setup_active
      ? 'Đang khởi tạo'
      : normalizedStatus === 'SUSPENDED'
        ? 'Tạm ngưng'
        : normalizedStatus === 'GRACE'
          ? 'Chờ gia hạn'
          : normalizedStatus === 'ACTIVE'
            ? 'Đang hoạt động'
            : '—'

  return (
    <section id="account-watchlist" className="account-card account-watchlist-card">
      <header className="account-card-heading">
        <div>
          <span className="account-kicker">DS MÃ THEO DÕI & LƯỢT ĐỔI</span>
          <h2>Danh sách mã theo dõi</h2>
          <p>Danh sách được giữ xuyên suốt gói; hàng tháng chỉ reset lượt đổi mã.</p>
        </div>
        <span className={`account-status ${normalizedStatus === 'SUSPENDED' || normalizedStatus === 'GRACE' ? 'is-pending' : 'is-ok'}`}>{statusLabel}</span>
      </header>

      {watchlistState.loading ? <p className="account-panel-note">Đang tải DS mã theo dõi…</p> : null}
      {watchlistState.error ? <p className="account-feedback is-error" role="alert">{watchlistState.error}</p> : null}

      {watchlistState.data ? (
        <>
          <div className="account-metrics">
            <div><span>Đang theo dõi</span><strong>{draft.length}{hasLimit && limit != null ? `/${formatLimit(limit)}` : ''}</strong></div>
            <div><span>Lượt đổi còn lại</span><strong>{changeRemaining}</strong></div>
            <div><span>Reset tiếp theo</span><strong>{formatDate(watchlist.cycle_end)}</strong></div>
          </div>

          <SetupNotice state={watchlist} />
          {watchlist.vip_day_active ? (
            <p className="account-banner is-vip"><strong>VIP DAY đang hoạt động.</strong> Quyền CCC toàn thị trường mở đến {formatDate(watchlist.vip_day_ends_at, true)}; DS và quota cá nhân không thay đổi.</p>
          ) : null}
          {feedback.message ? <p className={`account-feedback is-${feedback.type}`} role={feedback.type === 'error' ? 'alert' : 'status'}>{feedback.message}</p> : null}

          <div className="account-watchlist-editor">
            <label className="account-search-label" htmlFor="account-watchlist-search">Thêm mã vào DS theo dõi</label>
            <input
              id="account-watchlist-search"
              className="account-search-input"
              type="search"
              inputMode="search"
              autoComplete="off"
              placeholder="Gõ mã hoặc tên công ty, ví dụ VIC…"
              value={query}
              onFocus={ensureMetadata}
              onChange={(event) => {
                setQuery(event.target.value)
                ensureMetadata()
              }}
            />
            {query ? (
              <div className="account-search-results">
                {searchState.loading ? <p>Đang tải dữ liệu tìm kiếm…</p> : null}
                {searchState.error ? <p className="is-error">{searchState.error}</p> : null}
                {!searchState.loading && !searchState.error && suggestions.length === 0 ? <p>Không có mã mới phù hợp.</p> : null}
                {suggestions.map((row) => (
                  <button key={row.symbol} type="button" onClick={() => addSymbol(row)}>
                    <StockLogo symbol={row.symbol} />
                    <span><strong>{row.symbol}</strong><small>{row.display_name || row.company_name || 'Tên công ty đang cập nhật'} · {row.exchange || '—'}</small></span>
                    <b>+ Thêm</b>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="account-watchlist-list-heading">
              <span>Mã đang theo dõi</span>
              <small>{dirty ? 'Có thay đổi chưa lưu' : 'Chưa có thay đổi'}</small>
            </div>
            <div className="account-symbol-list">
              {draft.length === 0 ? <p className="account-empty-row">Chưa có mã nào trong DS mã theo dõi.</p> : null}
              {draft.map((symbol) => {
                const row = metadataMap.get(symbol) || {}
                return (
                  <article key={symbol}>
                    <StockLogo symbol={symbol} />
                    <div>
                      <strong>{symbol}</strong>
                      <span>{row.display_name || row.company_name || 'Tên công ty đang cập nhật'}</span>
                      <small>{row.exchange || '—'}{row.locked ? ' · Đang giữ, ngoài phạm vi kỹ thuật' : ''}</small>
                    </div>
                    <button type="button" onClick={() => {
                      setEditor({ sourceKey: authoritativeKey, baseline, draft: draft.filter((item) => item !== symbol) })
                      setFeedback({ type: '', message: '' })
                    }} aria-label={`Xóa ${symbol}`}>×</button>
                  </article>
                )
              })}
            </div>
          </div>

          <div className="account-watchlist-actions">
            <button type="button" className="account-secondary" disabled={!dirty || saving} onClick={() => {
              setEditor(null)
              setQuery('')
              setFeedback({ type: '', message: '' })
            }}>Hoàn tác</button>
            <button type="button" className="account-primary" disabled={!dirty || saving} onClick={save}>{saving ? 'Đang lưu…' : 'Lưu DS mã theo dõi'}</button>
          </div>
          <p className="account-rule-note">Trong cửa sổ khởi tạo, hệ thống áp dụng quyền thêm miễn phí theo dữ liệu trả về. Sau đó, mỗi mã mới thêm có thể dùng lượt đổi; xóa mã không tốn lượt. Hệ thống sẽ xác nhận toàn bộ quy tắc khi lưu.</p>
        </>
      ) : null}
    </section>
  )
}
