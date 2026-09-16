import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Tổng quan', short: 'Tổng quan' },
  { to: '/danh-sach', label: 'Bộ quét', short: 'DS theo dõi' },
  { to: '/so-sanh-theo-nganh', label: 'So sánh ngành', short: 'Nghiên cứu' },
  { to: '/sang-loc-co-ban', label: 'Sàng lọc cơ bản', short: 'Sàng lọc' },
]

function navClass({ isActive }) {
  return `nav-link${isActive ? ' is-active' : ''}`
}

export default function AppShell() {
  const [theme, setTheme] = useState(() => localStorage.getItem('ccc-theme') || 'dark')
  const navigate = useNavigate()

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ccc-theme', theme)
  }, [theme])

  function onSearch(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const query = String(form.get('q') || '').trim().toUpperCase()
    navigate(query ? `/danh-sach?q=${encodeURIComponent(query)}` : '/danh-sach')
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
          <button type="submit">Tìm</button>
        </form>

        <div className="top-actions">
          <div className="trust-chip" title="Data Trust V2 sẽ nối feed-health thật ở bước sau">
            <span className="status-dot" />
            <strong>V2 DEV</strong>
            <span>React</span>
          </div>
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
