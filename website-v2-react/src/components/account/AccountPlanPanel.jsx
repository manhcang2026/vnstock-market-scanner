import { formatChangeRemaining, formatLimit, getVipDayDisplay } from '../../lib/accountHelpers'

const dateFormatter = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' })
const cycleDateFormatter = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' })

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : dateFormatter.format(date)
}

function formatMoney(value) {
  if (value == null) return '—'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'
  return amount === 0 ? 'Miễn phí' : `${new Intl.NumberFormat('vi-VN').format(amount)}đ`
}

function formatCycleDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : cycleDateFormatter.format(date)
}

export default function AccountPlanPanel({ accessState, watchlistState, plansState }) {
  const watchlist = watchlistState.data || {}
  const access = { ...watchlist, ...(accessState.data || {}) }
  const plans = plansState.data || []
  const planCode = access.base_plan_code || watchlist.plan_code || ''
  const planId = access.base_plan_id || watchlist.plan_id || null
  const currentPlan = plans.find((plan) => (planId && String(plan.id) === String(planId)) || (planCode && plan.plan_code === planCode))
  const planName = access.base_plan_name || watchlist.plan_name || currentPlan?.display_name || 'Chưa xác định'
  const vip = getVipDayDisplay(access)
  const hasWatchlistLimit = Object.prototype.hasOwnProperty.call(access, 'watchlist_limit')
    || Object.prototype.hasOwnProperty.call(watchlist, 'watchlist_limit')
  const watchlistLimit = Object.prototype.hasOwnProperty.call(access, 'watchlist_limit') ? access.watchlist_limit : watchlist.watchlist_limit
  const hasChangeRemaining = Object.prototype.hasOwnProperty.call(watchlist, 'change_remaining')
  const changeRemaining = hasChangeRemaining ? watchlist.change_remaining : undefined
  const upgrades = plans.filter((plan) => plan.id !== currentPlan?.id && plan.plan_code !== planCode)

  return (
    <section id="account-plan" className="account-card account-plan-card">
      <header className="account-card-heading">
        <div><span className="account-kicker">GÓI HIỆN TẠI</span><h2>{planName}</h2></div>
        {planCode ? <span className="account-plan-badge">{planCode}{vip.active ? ' · VIP DAY' : ''}</span> : null}
      </header>

      {accessState.loading ? <p className="account-panel-note">Đang tải quyền tài khoản…</p> : null}
      {accessState.error ? <p className="account-feedback is-error" role="alert">{accessState.error}</p> : null}
      {accessState.data || watchlistState.data ? (
        <>
          <div className="account-plan-metrics">
            <div><span>Giá gói</span><strong>{formatMoney(currentPlan?.price_vnd)}</strong></div>
            <div><span>Quyền CCC</span><strong>{access.effective_full_market_access ? 'Toàn thị trường' : 'DS theo dõi'}</strong></div>
            <div><span>Số mã theo dõi</span><strong>{access.watchlist_count ?? watchlist.watchlist_count ?? '—'} / {hasWatchlistLimit ? formatLimit(watchlistLimit) : '—'}</strong></div>
            <div><span>Lượt đổi còn lại</span><strong>{hasChangeRemaining ? formatChangeRemaining(changeRemaining) : '—'}</strong></div>
            <div><span>Trạng thái</span><strong>{access.subscription_status || watchlist.status || '—'}</strong></div>
          </div>
          <div className="account-cycle"><span>Chu kỳ hiện tại</span><strong>{formatCycleDate(access.cycle_start)} → {formatCycleDate(access.cycle_end)}</strong></div>
        </>
      ) : null}

      <div className={`account-vip ${vip.active ? 'is-active' : ''}`}>
        <span>VIP DAY{vip.active ? ' · ĐANG HOẠT ĐỘNG' : ''}</span>
        <strong>{vip.active ? (vip.fullMarket ? 'FULL toàn thị trường đang mở' : 'Đang hoạt động') : 'Quyền tạm thời chưa hoạt động'}</strong>
        <small>{vip.active ? `Hết hạn ${formatDate(vip.endsAt)}. Gói nền và DS cá nhân vẫn giữ nguyên.` : (access.vip_day_price_vnd == null ? 'Chưa có thông tin giá từ hệ thống.' : `${formatMoney(access.vip_day_price_vnd)} · Chưa mở thanh toán trong V3.`)}</small>
      </div>

      <div className="account-upgrades">
        <div><span className="account-kicker">XEM & NÂNG CẤP</span><h3>Gói đang mở</h3><p>Chỉ hiển thị gói hoạt động từ hệ thống.</p></div>
        {plansState.loading ? <p className="account-panel-note">Đang tải danh sách gói…</p> : null}
        {plansState.error ? <p className="account-feedback is-error">{plansState.error}</p> : null}
        {upgrades.map((plan) => (
          <article key={plan.id || plan.plan_code}>
            <div><strong>{plan.display_name || plan.plan_code}</strong><small>{plan.full_market_access ? 'Toàn thị trường' : `${formatLimit(plan.watchlist_limit)} mã theo dõi`}</small></div>
            <b>{formatMoney(plan.price_vnd)}</b>
          </article>
        ))}
        <button type="button" className="account-secondary" disabled>Thanh toán sẽ được nối sau</button>
      </div>
    </section>
  )
}
