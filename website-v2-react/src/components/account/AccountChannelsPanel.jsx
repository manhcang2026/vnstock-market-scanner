export default function AccountChannelsPanel({ user, accessState, plansState }) {
  const access = accessState.data || {}
  const plan = (plansState.data || []).find((item) => item.id === access.base_plan_id || item.plan_code === access.base_plan_code)

  return (
    <section className="account-card account-compact-card">
      <header className="account-card-heading">
        <div><span className="account-kicker">KÊNH NHẬN CẢNH BÁO</span><h2>Email, Telegram & Zalo</h2><p>Trạng thái kết nối hiện tại.</p></div>
      </header>
      <div className="account-channel-list">
        <div><span>Email</span><strong>{user?.email || '—'}</strong><small>{plan?.email_alerts ? 'Có trong gói' : 'Chưa bao gồm hoặc chưa có dữ liệu quyền'}</small></div>
        <div><span>Telegram</span><strong>Chưa kết nối</strong><small>{plan?.telegram_alerts ? 'Có quyền trong gói; kết nối chưa có trong React V3.' : 'Kết nối chưa có trong React V3.'}</small></div>
        <div><span>Zalo</span><strong>Chưa kết nối</strong><small>Kết nối chưa có trong React V3.</small></div>
      </div>
    </section>
  )
}
