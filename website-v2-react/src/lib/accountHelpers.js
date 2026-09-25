const KNOWN_WATCHLIST_ERRORS = [
  ['WATCHLIST_LIMIT_EXCEEDED', 'Số mã vượt giới hạn của gói hiện tại.'],
  ['CHANGE_QUOTA_EXCEEDED', 'Không đủ lượt đổi mã để thực hiện thay đổi này.'],
  ['INVALID_SYMBOL', 'Có mã không thuộc danh sách cổ phiếu hiện tại.'],
  ['SUBSCRIPTION_SUSPENDED', 'Tài khoản đang tạm ngưng quyền thay đổi DS mã theo dõi.'],
  ['NO_CURRENT_SUBSCRIPTION', 'Không tìm thấy gói thành viên đang hoạt động.'],
  ['AUTH_REQUIRED', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'],
]

export function normalizeSymbols(symbols) {
  return [...new Set((Array.isArray(symbols) ? symbols : [])
    .map((symbol) => String(symbol || '').trim().toUpperCase())
    .filter(Boolean))]
    .sort((left, right) => left.localeCompare(right))
}
export function areWatchlistsEqual(left, right) {
  const normalizedLeft = normalizeSymbols(left)
  const normalizedRight = normalizeSymbols(right)
  return normalizedLeft.length === normalizedRight.length
    && normalizedLeft.every((symbol, index) => symbol === normalizedRight[index])
}

export function addDraftSymbol(symbols, symbol) {
  const normalizedSymbol = String(symbol || '').trim().toUpperCase()
  const current = normalizeSymbols(symbols)
  if (!normalizedSymbol || current.includes(normalizedSymbol)) return current
  return normalizeSymbols([...current, normalizedSymbol])
}

export function restoreWatchlistBaseline(baseline) {
  return normalizeSymbols(baseline)
}

export function watchlistFriendlyError(error) {
  const message = String(error?.message || error || '')
  const match = KNOWN_WATCHLIST_ERRORS.find(([code]) => message.includes(code))
  return match?.[1] || 'Không cập nhật được DS mã theo dõi. Vui lòng thử lại.'
}

export function validatePasswordChange({ currentPassword, newPassword, confirmPassword }) {
  if (!currentPassword || !newPassword || !confirmPassword) {
    return 'Vui lòng nhập đầy đủ ba ô mật khẩu.'
  }
  if (newPassword.length < 8) return 'Mật khẩu mới cần tối thiểu 8 ký tự.'
  if (newPassword !== confirmPassword) return 'Hai lần nhập mật khẩu mới chưa khớp.'
  if (newPassword === currentPassword) return 'Mật khẩu mới cần khác mật khẩu hiện tại.'
  return ''
}

export function passwordFriendlyError(error) {
  const message = String(error?.message || '').toLowerCase()
  if (message.includes('invalid login credentials')) return 'Mật khẩu hiện tại chưa đúng.'
  if (message.includes('password') && (message.includes('weak') || message.includes('characters') || message.includes('at least'))) {
    return 'Mật khẩu mới chưa đạt yêu cầu bảo mật.'
  }
  return 'Chưa đổi được mật khẩu. Vui lòng thử lại.'
}

export function formatLimit(value) {
  return value == null ? 'Không giới hạn' : String(Math.max(0, Number(value) || 0))
}

export function formatChangeRemaining(value) {
  return value == null ? 'Không giới hạn' : `${Math.max(0, Number(value) || 0)} lượt`
}

export function getVipDayDisplay(context) {
  if (context?.vip_day_active !== true) return { active: false, label: 'Chưa hoạt động' }
  return {
    active: true,
    label: 'VIP DAY đang hoạt động',
    endsAt: context.vip_day_ends_at || null,
    fullMarket: context.effective_full_market_access === true,
  }
}

export function accountRoleLabel(role) {
  switch (String(role || '').toUpperCase()) {
    case 'USER': return 'Thành viên'
    case 'ADMIN': return 'Quản trị viên'
    case 'SUPER_ADMIN': return 'Quản trị viên cấp cao'
    default: return 'Không xác định'
  }
}

export function validateProfile({ displayName, phone, address }) {
  const normalizedName = String(displayName || '').trim()
  const phoneDigits = String(phone || '').replace(/[^0-9]/g, '')
  const normalizedAddress = String(address || '').trim()

  if (normalizedName.length < 2 || normalizedName.length > 100) {
    return 'Họ và tên cần từ 2 đến 100 ký tự.'
  }
  if (phoneDigits.length < 8 || phoneDigits.length > 15) {
    return 'Số điện thoại chưa hợp lệ.'
  }
  if (normalizedAddress.length > 500) return 'Địa chỉ tối đa 500 ký tự.'
  return ''
}
