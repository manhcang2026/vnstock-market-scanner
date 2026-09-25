import { useState } from 'react'
import { accountRoleLabel, passwordFriendlyError, validatePasswordChange } from '../../lib/accountHelpers'
import { changeMyPassword } from '../../lib/accountData'

export default function AccountSecurityPanel({ user, profile, logoutError, onLogout }) {
  const provider = String(user?.app_metadata?.provider || 'email').toLowerCase()
  const canChangePassword = provider !== 'google'
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ currentPassword: '', newPassword: '', confirmPassword: '' })
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState({ type: '', message: '' })

  async function changePassword(event) {
    event.preventDefault()
    const validationError = validatePasswordChange(form)
    if (validationError) {
      setFeedback({ type: 'error', message: validationError })
      return
    }
    setBusy(true)
    setFeedback({ type: '', message: '' })
    try {
      await changeMyPassword({
        email: user.email,
        currentPassword: form.currentPassword,
        newPassword: form.newPassword,
      })
      setForm({ currentPassword: '', newPassword: '', confirmPassword: '' })
      setOpen(false)
      setFeedback({ type: 'success', message: 'Đổi mật khẩu thành công.' })
    } catch (error) {
      setFeedback({ type: 'error', message: passwordFriendlyError(error) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section id="account-security" className="account-card account-compact-card">
      <header className="account-card-heading">
        <div><span className="account-kicker">BẢO MẬT</span><h2>Đăng nhập & phiên</h2><p>Quản lý tài khoản hiện tại.</p></div>
      </header>
      {feedback.message ? <p className={`account-feedback is-${feedback.type}`} role={feedback.type === 'error' ? 'alert' : 'status'}>{feedback.message}</p> : null}
      {logoutError ? <p className="account-feedback is-error" role="alert">{logoutError}</p> : null}
      <dl className="account-security-list">
        <div><dt>Phương thức</dt><dd>{provider === 'google' ? 'Google' : 'Email & mật khẩu'}</dd></div>
        <div><dt>Vai trò</dt><dd>{accountRoleLabel(profile?.role)}</dd></div>
        <div><dt>Trạng thái</dt><dd>{profile?.status || '—'}</dd></div>
      </dl>
      {canChangePassword ? (
        <button type="button" className="account-secondary" onClick={() => {
          setOpen((value) => !value)
          setFeedback({ type: '', message: '' })
        }}>Đổi mật khẩu</button>
      ) : <p className="account-panel-note">Mật khẩu được quản lý bởi tài khoản Google.</p>}
      {open ? (
        <form className="account-password-form" onSubmit={changePassword}>
          <label><span>Mật khẩu hiện tại</span><input type="password" autoComplete="current-password" minLength="8" value={form.currentPassword} onChange={(event) => setForm((current) => ({ ...current, currentPassword: event.target.value }))} required /></label>
          <label><span>Mật khẩu mới</span><input type="password" autoComplete="new-password" minLength="8" value={form.newPassword} onChange={(event) => setForm((current) => ({ ...current, newPassword: event.target.value }))} required /></label>
          <label><span>Nhập lại mật khẩu mới</span><input type="password" autoComplete="new-password" minLength="8" value={form.confirmPassword} onChange={(event) => setForm((current) => ({ ...current, confirmPassword: event.target.value }))} required /></label>
          <button className="account-primary" type="submit" disabled={busy}>{busy ? 'Đang đổi…' : 'Xác nhận đổi mật khẩu'}</button>
        </form>
      ) : null}
      <button type="button" className="account-secondary is-danger" onClick={onLogout}>Đăng xuất</button>
    </section>
  )
}
