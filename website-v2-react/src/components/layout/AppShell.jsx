import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { findStockMetadataBySymbol, findUniqueStockByName } from '../../lib/stockSearch'

const navItems = [
  { to: '/', label: 'Tổng quan', icon: 'home' },
  { to: '/thi-truong', label: 'Thị trường', icon: 'market' },
  { to: '/danh-sach', label: 'Đã theo dõi', icon: 'watchlist' },
  { to: '/kham-pha', label: 'Khám phá', icon: 'discover' },
  { to: '/tin-tuc', label: 'Tin tức / Bài viết', icon: 'news' },
  { to: '/cong-dong', label: 'Cộng đồng', icon: 'community' },
  { to: '/hoc-vien', label: 'Học viện', icon: 'academy' },
]

const mobileItems = navItems.slice(0, 4)
const morePaths = ['/tin-tuc', '/cong-dong', '/hoc-vien', '/tai-khoan', '/mod', '/admin']
const SYMBOL_RE = /^[A-Z0-9]{2,12}$/

const iconPaths = {
  home: 'M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5M9 21v-7h6v7',
  market: 'M4 19V9m5 10V5m5 14v-7m5 7V3',
  watchlist: 'M6 3h12v18l-6-4-6 4V3Z',
  discover: 'm14.5 9.5-3 5-5 3 3-5 5-3ZM12 2v2m0 16v2M2 12h2m16 0h2',
  news: 'M5 4h14v16H5V4Zm3 4h8M8 12h8M8 16h5',
  community: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-1a2.5 2.5 0 1 0 0-5M3 20c0-4 2-6 5-6s5 2 5 6m1-6c3 0 5 2 5 6',
  academy: 'm3 8 9-5 9 5-9 5-9-5Zm4 3v5c3 2 7 2 10 0v-5',
  shield: 'M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6l-7-3Zm-3 9 2 2 4-4',
  admin: 'M12 3 4 7v5c0 4.5 3 7.5 8 9 5-1.5 8-4.5 8-9V7l-8-4Zm0 5v8m-4-4h8',
  ai: 'M12 3v3m0 12v3M3 12h3m12 0h3m-5.6-5.4-2.1 2.1m-2.6 6.6-2.1 2.1m8.8 0-2.1-2.1m-2.6-6.6L8.6 6.6M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
  bell: 'M18 9a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7Zm-8 10h4',
  help: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm-3-13a3 3 0 1 1 4 2.8c-1 .5-1 1.2-1 2.2m0 3h.01',
  settings: 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8-3.5 2-1-2-4-2.2.5a8 8 0 0 0-1.3-1.3L17 4l-4-2-1 2a8 8 0 0 0-2 0L9 2 5 4l.5 2.2a8 8 0 0 0-1.3 1.3L2 7l-2 4 2 1a8 8 0 0 0 0 2l-2 1 2 4 2.2-.5a8 8 0 0 0 1.3 1.3L5 22l4 2 1-2a8 8 0 0 0 2 0l1 2 4-2-.5-2.2a8 8 0 0 0 1.3-1.3L20 19l2-4-2-1a8 8 0 0 0 0-2Z',
  account: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21c0-4 3-6 8-6s8 2 8 6',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
}

function ShellIcon({ name }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d={iconPaths[name]} /></svg>
}

function navClass({ isActive }) {
  return `nav-link${isActive ? ' is-active' : ''}`
}

function roleItems(role) {
  if (role === 'admin') {
    return [
      { to: '/mod', label: 'Mod Dashboard', icon: 'shield' },
      { to: '/admin', label: 'Admin Dashboard', icon: 'admin' },
    ]
  }
  return role === 'mod' ? [{ to: '/mod', label: 'Mod Dashboard', icon: 'shield' }] : []
}

function Navigation({ onNavigate, role }) {
  const roleNavigation = roleItems(role)
  return (
    <>
      <div className="nav-section">
        <span className="nav-section-label">Không gian làm việc</span>
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={navClass} onClick={onNavigate}>
            <span><ShellIcon name={item.icon} /></span>
            <strong>{item.label}</strong>
          </NavLink>
        ))}
      </div>
      <div className="nav-section nav-personal">
        <span className="nav-section-label">Danh sách của tôi</span>
        <Link to="/danh-sach" className="nav-link" onClick={onNavigate}>
          <span><ShellIcon name="watchlist" /></span>
          <strong>Danh sách theo dõi</strong>
        </Link>
      </div>
      {roleNavigation.length ? (
        <div className="nav-section nav-role">
          <span className="nav-section-label">Quản trị</span>
          {roleNavigation.map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass} onClick={onNavigate}>
              <span><ShellIcon name={item.icon} /></span>
              <strong>{item.label}</strong>
            </NavLink>
          ))}
        </div>
      ) : null}
    </>
  )
}

export default function AppShell() {
  const [searchBusy, setSearchBusy] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [now, setNow] = useState(() => new Date())
  const menuButtonRef = useRef(null)
  const drawerRef = useRef(null)
  const drawerWasOpen = useRef(false)
  const moreButtonRef = useRef(null)
  const moreSheetRef = useRef(null)
  const moreWasOpen = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, ready } = useAuth()
  const role = String(user?.app_metadata?.role || user?.user_metadata?.role || '').toLowerCase()
  const roleNavigation = roleItems(role)

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    setDrawerOpen(false)
    setMoreOpen(false)
  }, [location.pathname, location.search])

  useEffect(() => {
    if (!drawerOpen && !moreOpen) return undefined
    function onKeyDown(event) {
      if (event.key === 'Escape') {
        setDrawerOpen(false)
        setMoreOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [drawerOpen, moreOpen])

  useEffect(() => {
    if (drawerOpen) {
      drawerWasOpen.current = true
      const frame = window.requestAnimationFrame(() => drawerRef.current?.querySelector('a')?.focus())
      return () => window.cancelAnimationFrame(frame)
    }
    if (drawerWasOpen.current) {
      drawerWasOpen.current = false
      menuButtonRef.current?.focus()
    }
    return undefined
  }, [drawerOpen])

  useEffect(() => {
    if (moreOpen) {
      moreWasOpen.current = true
      const frame = window.requestAnimationFrame(() => moreSheetRef.current?.querySelector('a')?.focus())
      return () => window.cancelAnimationFrame(frame)
    }
    if (moreWasOpen.current) {
      moreWasOpen.current = false
      moreButtonRef.current?.focus()
    }
    return undefined
  }, [moreOpen])

  async function onSearch(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const rawQuery = String(form.get('q') || '').trim()
    const tickerQuery = rawQuery.toUpperCase()

    if (!rawQuery) {
      navigate('/thi-truong')
      return
    }

    setSearchBusy(true)
    try {
      const exactTicker = SYMBOL_RE.test(tickerQuery) ? await findStockMetadataBySymbol(tickerQuery) : null
      const match = exactTicker || await findUniqueStockByName(rawQuery)
      if (match?.symbol) {
        navigate(`/co-phieu/${encodeURIComponent(match.symbol)}`)
        return
      }
    } catch {
      navigate(`/thi-truong?q=${encodeURIComponent(rawQuery)}&lookup=unavailable`)
      return
    } finally {
      setSearchBusy(false)
    }

    navigate(`/thi-truong?q=${encodeURIComponent(rawQuery)}`)
  }

  const vietnamTime = new Intl.DateTimeFormat('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(now)
  const accountPath = ready && user ? '/tai-khoan' : '/dang-nhap'
  const accountLabel = !ready ? 'Đang tải tài khoản' : user ? `Tài khoản${user.email ? `: ${user.email}` : ''}` : 'Đăng nhập'
  const mobileAccountLabel = !ready ? 'Đang tải tài khoản' : user ? 'Tài khoản & Cài đặt' : 'Đăng nhập'
  const moreActive = morePaths.some((path) => location.pathname === path || location.pathname.startsWith(`${path}/`))

  function toggleDrawer() {
    setMoreOpen(false)
    setDrawerOpen((value) => !value)
  }

  function toggleMore() {
    setDrawerOpen(false)
    setMoreOpen((value) => !value)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <button ref={menuButtonRef} type="button" className="menu-button" aria-label="Mở điều hướng" aria-expanded={drawerOpen} aria-controls="mobile-drawer" onClick={toggleDrawer}>
          <span aria-hidden="true">☰</span>
        </button>

        <NavLink to="/" className="brand" aria-label="Chuyện Chợ Chứng">
          <span className="brand-mark">CCC</span>
          <span className="brand-copy"><strong>Chuyện Chợ Chứng</strong></span>
        </NavLink>

        <form className="global-search" onSubmit={onSearch} role="search">
          <input name="q" type="search" placeholder="Tìm mã chứng khoán" autoComplete="off" aria-label="Tìm mã chứng khoán" />
          <button type="submit" disabled={searchBusy} aria-label="Tìm kiếm">{searchBusy ? '…' : 'Tìm'}</button>
        </form>

        <div className="top-actions">
          <NavLink className="header-action ai-action" to="/kham-pha?tab=ai" aria-label="Mở CCC AI" title="CCC AI"><ShellIcon name="ai" /><span>AI</span></NavLink>
          <time className="vietnam-clock" dateTime={now.toISOString()} title="Giờ Việt Nam"><strong>{vietnamTime}</strong><span>Giờ VN</span></time>
          <NavLink className="header-action" to="/tai-khoan?tab=thong-bao" aria-label="Thông báo" title="Thông báo"><ShellIcon name="bell" /></NavLink>
          <NavLink className="header-action desktop-action" to="/hoc-vien" aria-label="Trợ giúp" title="Trợ giúp"><ShellIcon name="help" /></NavLink>
          <NavLink className="header-action desktop-action" to="/tai-khoan?tab=trai-nghiem" aria-label="Cài đặt" title="Cài đặt"><ShellIcon name="settings" /></NavLink>
          <NavLink className="account-button" to={accountPath} aria-label={accountLabel} title={accountLabel}><ShellIcon name="account" /><strong>{!ready ? '...' : user ? 'Tài khoản' : 'Đăng nhập'}</strong></NavLink>
        </div>
      </header>

      <aside className="desktop-nav" aria-label="Điều hướng chính"><Navigation role={role} /></aside>
      <main className="main-content"><Outlet /></main>

      <button type="button" className={`drawer-backdrop${drawerOpen ? ' is-open' : ''}`} aria-label="Đóng điều hướng" tabIndex={drawerOpen ? 0 : -1} onClick={() => setDrawerOpen(false)} />
      <aside ref={drawerRef} id="mobile-drawer" className={`mobile-drawer${drawerOpen ? ' is-open' : ''}`} aria-label="Điều hướng di động" hidden={!drawerOpen}>
        <div className="mobile-drawer-heading"><strong>Điều hướng</strong><button type="button" onClick={() => setDrawerOpen(false)} aria-label="Đóng điều hướng">×</button></div>
        <Navigation role={role} onNavigate={() => setDrawerOpen(false)} />
      </aside>

      <nav className="mobile-bottom-nav" aria-label="Lối tắt di động">
        {mobileItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `mobile-bottom-link${isActive ? ' is-active' : ''}`}>
            <ShellIcon name={item.icon} /><span>{item.to === '/danh-sach' ? 'Theo dõi' : item.label}</span>
          </NavLink>
        ))}
        <button ref={moreButtonRef} type="button" className={`mobile-bottom-link${moreActive || moreOpen ? ' is-active' : ''}`} aria-expanded={moreOpen} aria-controls="mobile-more-menu" onClick={toggleMore}>
          <ShellIcon name="more" /><span>Thêm</span>
        </button>
      </nav>

      <button type="button" className={`mobile-more-backdrop${moreOpen ? ' is-open' : ''}`} aria-label="Đóng menu thêm" tabIndex={moreOpen ? 0 : -1} onClick={() => setMoreOpen(false)} />
      <aside ref={moreSheetRef} id="mobile-more-menu" className={`mobile-more-sheet${moreOpen ? ' is-open' : ''}`} aria-label="Điều hướng bổ sung" hidden={!moreOpen}>
        <div className="mobile-more-handle" aria-hidden="true" />
        <strong>Thêm</strong>
        <nav>
          {navItems.slice(4).map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass}><span><ShellIcon name={item.icon} /></span><strong>{item.label}</strong></NavLink>
          ))}
          <NavLink to={accountPath} className={navClass}><span><ShellIcon name={ready && user ? 'settings' : 'account'} /></span><strong>{mobileAccountLabel}</strong></NavLink>
          {roleNavigation.map((item) => (
            <NavLink key={item.to} to={item.to} className={navClass}><span><ShellIcon name={item.icon} /></span><strong>{item.label}</strong></NavLink>
          ))}
        </nav>
      </aside>
    </div>
  )
}
