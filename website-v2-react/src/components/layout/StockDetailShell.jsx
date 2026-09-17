import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
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
          aria-label="Mở menu chính"
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
          <button
            type="button"
            className="stock-header-account"
            onClick={() => navigate('/dang-nhap')}
            title={user?.email || 'Tài khoản'}
          >
            <Icon name="account" size={17} />
            <span>{!ready ? '…' : user ? 'Tài khoản' : 'Đăng nhập'}</span>
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
          <ShellNavLink key={item.to} item={item} compact />
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
            <div className="stock-v3-drawer-header">
              <div>
                <strong>Chuyện Chợ Chứng</strong>
                <span>Stock Intelligence</span>
              </div>
              <button
                ref={drawerCloseRef}
                type="button"
                className="stock-header-button"
                aria-label="Đóng menu chính"
                onClick={() => {
                  setDrawerOpen(false)
                  menuButtonRef.current?.focus()
                }}
              >
                <Icon name="close" />
              </button>
            </div>
            <nav>
              {desktopNavItems.map((item) => (
                <ShellNavLink key={item.to} item={item} onClick={() => setDrawerOpen(false)} />
              ))}
            </nav>
            <div className="stock-v3-drawer-footer">
              <button type="button" onClick={() => navigate('/dang-nhap')}>
                <Icon name="account" />
                <span>{user ? user.email : 'Đăng nhập / Tài khoản'}</span>
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
          </section>
        </div>
      ) : null}
    </div>
  )
}
