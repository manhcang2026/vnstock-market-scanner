import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { findUniqueStockByName } from '../../lib/stockSearch'
import StockDetailShell from './StockDetailShell'

const navItems = [
  { to: '/', label: 'Tổng quan', short: 'Tổng quan' },
  { to: '/danh-sach', label: 'Bộ quét', short: 'DS theo dõi' },
  { to: '/so-sanh-theo-nganh', label: 'So sánh ngành', short: 'Nghiên cứu' },
  { to: '/sang-loc-co-ban', label: 'Sàng lọc cơ bản', short: 'Sàng lọc' },
]

const SYMBOL_RE = /^[A-Z0-9]{2,12}$/

function navClass({ isActive }) {
  return `nav-link${isActive ? ' is-active' : ''}`
}

export default function AppShell() {
  const [theme, setTheme] = useState(() => localStorage.getItem('ccc-theme') || 'dark')
  const [searchBusy, setSearchBusy] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, ready } = useAuth()
  const isStockDetail = /^\/co-phieu\/[^/]+\/?$/.test(location.pathname)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ccc-theme', theme)
  }, [theme])

  async function onSearch(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const rawQuery = String(form.get('q') || '').trim()
    const tickerQuery = rawQuery.toUpperCase()

    if (!rawQuery) {
      navigate('/danh-sach')
      return
    }

    if (SYMBOL_RE.test(tickerQuery)) {
      navigate(`/co-phieu/${encodeURIComponent(tickerQuery)}`)
      return
    }

    setSearchBusy(true)
    try {
      const match = await findUniqueStockByName(rawQuery)
      if (match?.symbol) {
        navigate(`/co-phieu/${encodeURIComponent(match.symbol)}`)
        return
      }
    } catch {
      // Fall through to Scanner search when metadata lookup is unavailable.
    } finally {
      setSearchBusy(false)
    }

    navigate(`/danh-sach?q=${encodeURIComponent(tickerQuery)}`)
  }

  if (isStockDetail) {
    return (
      <StockDetailShell
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        onSearch={onSearch}
        searchBusy={searchBusy}
        user={user}
        ready={ready}
      >
        <Outlet />
      </StockDetailShell>
    )
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="Chuyện Chợ Chứng">
          <span className="brand-mark">CCC</span>
          <span className="brand-copy">
            <strong>CHUYỆN CHỢ CHỨNG</strong>
            <small>Stock Intelligence</small>
          </span>
        </NavLink>

        <form className="global-search" onSubmit={onSearch}>
          <input
            name="q"
            type="search"
            placeholder="Tìm mã chứng khoán"
            autoComplete="off"
            aria-label="Tìm mã chứng khoán"
          />
          <button type="submit" disabled={searchBusy}>
            {searchBusy ? '...' : 'Tìm'}
          </button>
        </form>

        <div className="top-actions">
          <div className="trust-chip" title="Data Trust V2 sẽ nối feed-health thật ở bước sau">
            <span className="status-dot" />
            <strong>V2 DEV</strong>
            <span>React</span>
          </div>
          <button
            type="button"
            className="account-button"
            onClick={() => navigate('/dang-nhap')}
            title={user?.email || 'Tài khoản'}
          >
            <span>{ready && user ? '●' : '○'}</span>
            <strong>{!ready ? '...' : user ? 'Tài khoản' : 'Đăng nhập'}</strong>
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            aria-label="Đổi giao diện sáng/tối"
            title="Đổi giao diện sáng/tối"
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
      </header>

      <aside className="desktop-nav" aria-label="Điều hướng chính">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={navClass}>
            <span>{item.label.slice(0, 1)}</span>
            <small>{item.label}</small>
          </NavLink>
        ))}
      </aside>

      <main className="main-content">
        <Outlet />
      </main>

      <nav className="mobile-nav" aria-label="Điều hướng di động">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={navClass}>
            <span>{item.label.slice(0, 1)}</span>
            <small>{item.short}</small>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
