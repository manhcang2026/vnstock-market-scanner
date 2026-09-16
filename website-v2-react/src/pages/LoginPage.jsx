import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import PageHeader from '../components/ui/PageHeader'

export default function LoginPage() {
  const { user, ready, authError, signInWithPassword, signInWithGoogle, signOut } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')

  async function handleEmailLogin(event) {
    event.preventDefault()
    setMessage('')
    setBusy('email')
    try {
      await signInWithPassword(email.trim(), password)
      setMessage('Đăng nhập thành công.')
    } catch (error) {
      setMessage(error?.message || 'Không đăng nhập được.')
    } finally {
      setBusy('')
    }
  }

  async function handleGoogleLogin() {
    setMessage('')
    setBusy('google')
    try {
      await signInWithGoogle()
    } catch (error) {
      setMessage(error?.message || 'Không mở được đăng nhập Google.')
      setBusy('')
    }
  }

  async function handleSignOut() {
    setBusy('signout')
    setMessage('')
    try {
      await signOut()
      setMessage('Đã đăng xuất.')
    } catch (error) {
      setMessage(error?.message || 'Không đăng xuất được.')
    } finally {
      setBusy('')
    }
  }

  if (!ready) {
    return (
      <div className="page">
        <PageHeader eyebrow="Tài khoản" title="Đang kiểm tra phiên đăng nhập…" />
      </div>
    )
  }

  if (user) {
    const provider = user.app_metadata?.provider || 'email'
    return (
      <div className="page auth-page">
        <PageHeader
          eyebrow="Supabase Auth · Connected"
          title="Tài khoản"
          description="Phiên đăng nhập này sẽ cấp JWT cho các API kỹ thuật được bảo vệ của CCC V2."
        />
        <section className="auth-card">
          <div className="auth-success">
            <span className="status-dot" />
            <div>
              <strong>Đã đăng nhập</strong>
              <p>{user.email || user.id}</p>
              <small>Provider: {provider}</small>
            </div>
          </div>
          <button type="button" className="secondary-button" disabled={busy === 'signout'} onClick={handleSignOut}>
            {busy === 'signout' ? 'Đang đăng xuất…' : 'Đăng xuất'}
          </button>
          {message ? <p className="auth-message">{message}</p> : null}
        </section>
      </div>
    )
  }

  return (
    <div className="page auth-page">
      <PageHeader
        eyebrow="Supabase Auth"
        title="Đăng nhập"
        description="Dùng cùng tài khoản Chuyện Chợ Chứng hiện tại. Mật khẩu không được lưu trong source code."
      />

      <section className="auth-card">
        <button type="button" className="google-button" disabled={Boolean(busy)} onClick={handleGoogleLogin}>
          {busy === 'google' ? 'Đang mở Google…' : 'Tiếp tục với Google'}
        </button>

        <div className="auth-divider"><span>hoặc</span></div>

        <form className="auth-form" onSubmit={handleEmailLogin}>
          <label>
            <span>Email</span>
            <input
              type="email"
              value={email}
              autoComplete="email"
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            <span>Mật khẩu</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button type="submit" className="primary-button" disabled={Boolean(busy)}>
            {busy === 'email' ? 'Đang đăng nhập…' : 'Đăng nhập bằng email'}
          </button>
        </form>

        {authError ? <p className="auth-message is-error">{authError}</p> : null}
        {message ? <p className="auth-message">{message}</p> : null}
      </section>
    </div>
  )
}
