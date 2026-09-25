const sections = [
  ['account-profile', 'Hồ sơ', 'Thông tin cá nhân'],
  ['account-watchlist', 'DS theo dõi', 'Mã và lượt đổi'],
  ['account-plan', 'Gói & quyền', 'Quyền hiện tại'],
  ['account-security', 'Bảo mật', 'Mật khẩu và phiên'],
]

export default function AccountLeftRail() {
  return (
    <nav className="account-section-nav" aria-label="Mục tài khoản">
      <span className="account-kicker">TÀI KHOẢN</span>
      {sections.map(([id, label, detail]) => (
        <a key={id} href={`#${id}`}>
          <strong>{label}</strong>
          <small>{detail}</small>
        </a>
      ))}
    </nav>
  )
}
