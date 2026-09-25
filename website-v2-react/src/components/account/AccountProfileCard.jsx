import { useState } from 'react'
import { saveMyProfile } from '../../lib/accountData'
import { validateProfile } from '../../lib/accountHelpers'

export default function AccountProfileCard({ user, profileState, onSaved }) {
  const profile = profileState.data || {}
  const authoritativeForm = {
    displayName: profile.display_name
      || user?.user_metadata?.full_name
      || user?.user_metadata?.name
      || '',
    phone: profile.phone || '',
    address: profile.address || '',
  }
  const authoritativeKey = JSON.stringify(Object.values(authoritativeForm))
  const [draft, setDraft] = useState(null)
  const form = draft?.sourceKey === authoritativeKey ? draft.values : authoritativeForm
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState({ type: '', message: '' })
  const profileStatus = profileState.loading
    ? 'Đang tải'
    : profileState.data
      ? (profile.profile_completed ? 'Đã hoàn tất' : 'Cần bổ sung')
      : 'Không khả dụng'

  function updateField(event) {
    setDraft({
      sourceKey: authoritativeKey,
      values: { ...form, [event.target.name]: event.target.value },
    })
    setFeedback({ type: '', message: '' })
  }

  async function submit(event) {
    event.preventDefault()
    const error = validateProfile(form)
    if (error) {
      setFeedback({ type: 'error', message: error })
      return
    }

    setSaving(true)
    setFeedback({ type: '', message: '' })
    let saved = false
    try {
      await saveMyProfile({
        displayName: form.displayName.trim(),
        phone: form.phone.trim(),
        address: form.address.trim(),
      })
      saved = true
      await onSaved()
      setDraft(null)
      setFeedback({ type: 'success', message: 'Đã lưu hồ sơ thành công.' })
    } catch {
      setFeedback(saved
        ? { type: 'success', message: 'Đã lưu hồ sơ; dữ liệu mới sẽ được làm mới ở lần tải tiếp theo.' }
        : { type: 'error', message: 'Không lưu được hồ sơ. Vui lòng thử lại.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section id="account-profile" className="account-card account-profile-card">
      <header className="account-card-heading">
        <div>
          <span className="account-kicker">HỒ SƠ CÁ NHÂN</span>
          <h2>Thông tin cá nhân</h2>
          <p>Cập nhật thông tin liên hệ của bạn.</p>
        </div>
        <span className={`account-status ${profile.profile_completed ? 'is-ok' : 'is-pending'}`}>
          {profileStatus}
        </span>
      </header>

      {profileState.loading ? <p className="account-panel-note">Đang tải hồ sơ…</p> : null}
      {profileState.error ? <p className="account-feedback is-error" role="alert">{profileState.error}</p> : null}
      {feedback.message ? (
        <p className={`account-feedback is-${feedback.type}`} role={feedback.type === 'error' ? 'alert' : 'status'}>
          {feedback.message}
        </p>
      ) : null}

      <form className="account-form" onSubmit={submit} noValidate>
        <label className="is-full">
          <span>Email</span>
          <input type="email" value={user?.email || ''} readOnly />
          <small>Email được quản lý bởi tài khoản đăng nhập.</small>
        </label>
        <label>
          <span>Họ và tên <b>*</b></span>
          <input name="displayName" type="text" minLength="2" maxLength="100" autoComplete="name" value={form.displayName} onChange={updateField} disabled={profileState.loading} required />
        </label>
        <label>
          <span>Số điện thoại <b>*</b></span>
          <input name="phone" type="tel" inputMode="tel" maxLength="30" autoComplete="tel" value={form.phone} onChange={updateField} disabled={profileState.loading} required />
        </label>
        <label className="is-full">
          <span>Địa chỉ <em>(không bắt buộc)</em></span>
          <textarea name="address" rows="3" maxLength="500" autoComplete="street-address" value={form.address} onChange={updateField} disabled={profileState.loading} />
        </label>
        <div className="account-form-actions is-full">
          <button className="account-primary" type="submit" disabled={saving || profileState.loading}>
            {saving ? 'Đang lưu…' : 'Lưu thay đổi'}
          </button>
        </div>
      </form>
    </section>
  )
}
