import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import '../../styles/stock-detail-shell.css'

const desktopNavItems = [
  { to: '/', label: 'Tổng quan', icon: 'overview', end: true },
  { to: '/danh-sach', label: 'Scanner', icon: 'scanner' },
  { to: '/so-sanh-theo-nganh', label: 'Nghiên cứu', icon: 'research' },
  { to: '/sang-loc-co-ban', label: 'Cơ bản', icon: 'fundamental' },
]

const vnClockDesktop = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Ho_Chi_Minh',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

const vnClockMobile = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Ho_Chi_Minh',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function VietnamClock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <time className="stock-v3-clock" dateTime={now.toISOString()} title="Giờ Việt Nam">
      <span className="stock-v3-clock-desktop">{vnClockDesktop.format(now)}</span>
      <span className="stock-v3-clock-mobile">{vnClockMobile.format(now)}</span>
      <small>VN</small>
    </time>
  )
}

function Icon({ name, size = 20 }) {
  const paths = {
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    overview: <><path d="M4 13h6V4H4v9Zm10 7h6v-9h-6v9ZM4 20h6v-3H4v3Zm10-13h6V4h-6v3Z" /></>,
    scanner: <><path d="M4 5h16M7 10h10M9 15h6M11 20h2" /></>,
    research: <><path d="M4 19V9m6 10V5m6 14v-7m4 7H2" /></>,
    fundamental: <><path d="M4 20h16M6 16h3m2 0h3m2 0h2M5 12h14M7 8h10l-5-4-5 4Z" /></>,
    search: <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></>,
    moon: <><path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" /></>,
    sun: <><circle cx="12" cy="12" r="3.5" /><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    watchlist: <><path d="M6 4h12v17l-6-4-6 4V4Z" /></>,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    account: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.8 9a2.4 2.4 0 1 1 3.3 2.2c-.8.4-1.1.9-1.1 1.8m0 3h.01" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  }

  return (
    <svg
      className="stock-shell-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.overview}
    </svg>
  )
}

function ShellNavLink({ item, onClick, compact = false }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) => `stock-shell-nav-link${isActive ? ' is-active' : ''}${compact ? ' is-compact' : ''}`}
      onClick={onClick}
    >
      <Icon name={item.icon} />
      {!compact ? <span>{item.label}</span> : <span className="sr-only">{item.label}</span>}
    </NavLink>
  )
}

export default function StockDetailShell({
  children,
  theme,
  onToggleTheme,
  onSearch,
  searchBusy,
  user,
  ready,
}) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const menuButtonRef = useRef(null)
  const drawerCloseRef = useRef(null)
  const moreCloseRef = useRef(null)
  const moreButtonRef = useRef(null)
  const moreSheetRef = useRef(null)
  const moreWasOpenRef = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const accountName = user?.user_metadata?.display_name
    || user?.user_metadata?.full_name
    || user?.email?.split('@')[0]
    || 'Đăng nhập'

  useEffect(() => {
    if (drawerOpen) drawerCloseRef.current?.focus()
  }, [drawerOpen])

  useEffect(() => {
    if (moreOpen) {
      moreWasOpenRef.current = true
      moreCloseRef.current?.focus()
      return
    }
    if (moreWasOpenRef.current) {
      moreWasOpenRef.current = false
      moreButtonRef.current?.focus()
    }
  }, [moreOpen])

  useEffect(() => {
    if (!drawerOpen && !moreOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return
      if (moreOpen) setMoreOpen(false)
      if (drawerOpen) {
        setDrawerOpen(false)
        menuButtonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen, moreOpen])

  function keepSheetFocus(event) {
    if (event.key !== 'Tab') return
    const focusable = [...(moreSheetRef.current?.querySelectorAll('button:not(:disabled), a[href]') || [])]
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="stock-v3-shell">
      <header className="stock-v3-header">
        <button
          ref={menuButtonRef}
          type="button"
          className="stock-header-button stock-menu-button"
          aria-label={drawerOpen ? 'Đóng menu chính' : 'Mở menu chính'}
          aria-expanded={drawerOpen}
          aria-controls="stock-v3-drawer"
          onClick={() => setDrawerOpen((value) => !value)}
        >
          <Icon name="menu" />
        </button>

        <NavLink to="/" className="stock-v3-brand" aria-label="Chuyện Chợ Chứng — Tổng quan">
          <span className="stock-v3-brand-mark">CCC</span>
          <span className="stock-v3-brand-copy">Chuyện Chợ Chứng</span>
        </NavLink>

        <form className="stock-v3-search" onSubmit={onSearch} role="search">
          <Icon name="search" size={17} />
          <input
            name="q"
            type="search"
            placeholder="Tìm mã"
            autoComplete="off"
            aria-label="Tìm mã hoặc tên công ty"
          />
          <button type="submit" disabled={searchBusy} aria-label="Tìm kiếm">
            {searchBusy ? '…' : 'Tìm'}
          </button>
        </form>

        <div className="stock-v3-header-actions">
          <VietnamClock />
          <button type="button" className="stock-header-button stock-header-utility" aria-label="Thông báo" title="Thông báo chưa được kết nối" disabled>
            <Icon name="bell" size={17} />
          </button>
          <button type="button" className="stock-header-button stock-header-utility" aria-label="Trợ giúp" title="Nội dung trợ giúp chưa có route" disabled>
            <Icon name="help" size={17} />
          </button>
          <button type="button" className="stock-header-button stock-header-utility" onClick={onToggleTheme} aria-label="Cài đặt giao diện" title="Cài đặt giao diện">
            <Icon name="settings" size={17} />
          </button>
          <button
            type="button"
            className="stock-header-account"
            onClick={() => navigate('/dang-nhap')}
            title={user?.email || 'Tài khoản'}
          >
            <Icon name="account" size={17} />
            <span>{!ready ? '…' : accountName}</span>
          </button>
          <button
            type="button"
            className="stock-header-button"
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
            title={theme === 'dark' ? 'Giao diện sáng' : 'Giao diện tối'}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>
        </div>
      </header>

      <aside className="stock-v3-nav-rail" aria-label="Điều hướng chính thu gọn">
        {desktopNavItems.map((item) => (
          <button
            key={item.to}
            type="button"
            className={`stock-shell-nav-link is-compact${location.pathname === item.to ? ' is-active' : ''}`}
            aria-label={`Mở nhãn ${item.label}`}
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            <Icon name={item.icon} />
          </button>
        ))}
      </aside>

      {drawerOpen ? (
        <>
          <button
            type="button"
            className="stock-v3-drawer-scrim"
            aria-label="Đóng menu chính"
            onClick={() => setDrawerOpen(false)}
          />
          <aside id="stock-v3-drawer" className="stock-v3-drawer" aria-label="Menu chính">
            <nav ref={drawerCloseRef} tabIndex={-1}>
              {desktopNavItems.map((item) => (
                <ShellNavLink key={item.to} item={item} onClick={() => setDrawerOpen(false)} />
              ))}
            </nav>
            <div className="stock-v3-drawer-footer">
              <button type="button" onClick={() => navigate('/dang-nhap')}>
                <Icon name="account" />
                <span>{user ? accountName : 'Đăng nhập / Tài khoản'}</span>
              </button>
            </div>
          </aside>
        </>
      ) : null}

      <main className="stock-v3-main">{children}</main>

      <nav className="stock-v3-mobile-nav" aria-label="Điều hướng di động">
        <NavLink to="/" end>
          <Icon name="overview" />
          <span>Tổng quan</span>
        </NavLink>
        <button
          ref={moreButtonRef}
          type="button"
          disabled
          title="Theo dõi chưa có route trong frontend hiện tại"
          aria-label="Theo dõi — chưa sẵn sàng"
        >
          <Icon name="watchlist" />
          <span>Theo dõi</span>
        </button>
        <NavLink to="/danh-sach">
          <Icon name="scanner" />
          <span>Scanner</span>
        </NavLink>
        <NavLink to="/so-sanh-theo-nganh">
          <Icon name="research" />
          <span>Nghiên cứu</span>
        </NavLink>
        <button
          type="button"
          aria-expanded={moreOpen}
          aria-controls="stock-v3-more-sheet"
          onClick={() => setMoreOpen(true)}
        >
          <Icon name="more" />
          <span>Thêm</span>
        </button>
      </nav>

      {moreOpen ? (
        <div className="stock-v3-sheet-layer">
          <button
            type="button"
            className="stock-v3-sheet-scrim"
            aria-label="Đóng bảng Thêm"
            onClick={() => setMoreOpen(false)}
          />
          <section
            ref={moreSheetRef}
            id="stock-v3-more-sheet"
            className="stock-v3-more-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="stock-v3-more-title"
            onKeyDown={keepSheetFocus}
          >
            <div className="stock-v3-sheet-handle" />
            <header>
              <h2 id="stock-v3-more-title">Thêm</h2>
              <button
                ref={moreCloseRef}
                type="button"
                className="stock-header-button"
                aria-label="Đóng bảng Thêm"
                onClick={() => setMoreOpen(false)}
              >
                <Icon name="close" />
              </button>
            </header>
            <button type="button" className="stock-v3-sheet-row" onClick={() => navigate('/dang-nhap')}>
              <Icon name="account" />
              <span>
                <strong>Tài khoản</strong>
                <small>{user?.email || 'Đăng nhập để quản lý tài khoản'}</small>
              </span>
              <Icon name="chevron" size={18} />
            </button>
            <NavLink className="stock-v3-sheet-row" to="/sang-loc-co-ban" onClick={() => setMoreOpen(false)}>
              <Icon name="fundamental" />
              <span>
                <strong>Sàng lọc cơ bản</strong>
                <small>Nghiên cứu doanh nghiệp theo tiêu chí</small>
              </span>
              <Icon name="chevron" size={18} />
            </NavLink>
            <button type="button" className="stock-v3-sheet-row" onClick={onToggleTheme}>
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
              <span>
                <strong>Giao diện</strong>
                <small>{theme === 'dark' ? 'Chuyển sang Sáng' : 'Chuyển sang Tối'}</small>
              </span>
              <Icon name="chevron" size={18} />
            </button>
            <button type="button" className="stock-v3-sheet-row" disabled>
              <Icon name="bell" />
              <span><strong>Thông báo</strong><small>Chưa kết nối dữ liệu thông báo</small></span>
              <Icon name="chevron" size={18} />
            </button>
            <button type="button" className="stock-v3-sheet-row" disabled>
              <Icon name="help" />
              <span><strong>Trợ giúp</strong><small>Chưa có nội dung trợ giúp</small></span>
              <Icon name="chevron" size={18} />
            </button>
          </section>
        </div>
      ) : null}
    </div>
  )
}
