import assert from 'node:assert/strict'
import test from 'node:test'
import {
  accountRoleLabel,
  addDraftSymbol,
  areWatchlistsEqual,
  formatChangeRemaining,
  formatLimit,
  getVipDayDisplay,
  passwordFriendlyError,
  restoreWatchlistBaseline,
  validatePasswordChange,
  watchlistFriendlyError,
} from './accountHelpers.js'

test('Watchlist dirty comparison ignores order and duplicate input', () => {
  assert.equal(areWatchlistsEqual(['VIC', 'FPT'], ['fpt', 'VIC', 'VIC']), true)
  assert.equal(areWatchlistsEqual(['VIC'], ['VIC', 'FPT']), false)
})
test('adding a duplicate symbol keeps one normalized item', () => {
  assert.deepEqual(addDraftSymbol(['vic'], 'VIC'), ['VIC'])
  assert.deepEqual(addDraftSymbol(['VIC'], 'fpt'), ['FPT', 'VIC'])
})

test('undo restores an isolated normalized baseline', () => {
  const baseline = ['VIC', 'FPT']
  const restored = restoreWatchlistBaseline(baseline)
  restored.push('HPG')
  assert.deepEqual(baseline, ['VIC', 'FPT'])
  assert.deepEqual(restored, ['FPT', 'VIC', 'HPG'])
})

test('known RPC errors map to friendly messages', () => {
  assert.equal(
    watchlistFriendlyError(new Error('CHANGE_QUOTA_EXCEEDED: rejected')),
    'Không đủ lượt đổi mã để thực hiện thay đổi này.',
  )
  assert.equal(
    watchlistFriendlyError(new Error('database detail that must stay private')),
    'Không cập nhật được DS mã theo dõi. Vui lòng thử lại.',
  )
})

test('null limits and change quota render as unlimited', () => {
  assert.equal(formatLimit(null), 'Không giới hạn')
  assert.equal(formatLimit(20), '20')
  assert.equal(formatChangeRemaining(null), 'Không giới hạn')
  assert.equal(formatChangeRemaining(3), '3 lượt')
})

test('VIP Day display follows authoritative active and full-market flags', () => {
  assert.deepEqual(getVipDayDisplay({ vip_day_active: false }), {
    active: false,
    label: 'Chưa hoạt động',
  })
  assert.deepEqual(getVipDayDisplay({
    vip_day_active: true,
    vip_day_ends_at: '2026-09-25T12:00:00Z',
    effective_full_market_access: true,
  }), {
    active: true,
    label: 'VIP DAY đang hoạt động',
    endsAt: '2026-09-25T12:00:00Z',
    fullMarket: true,
  })
})

test('role labels support only the existing role contract', () => {
  assert.equal(accountRoleLabel('USER'), 'Thành viên')
  assert.equal(accountRoleLabel('ADMIN'), 'Quản trị viên')
  assert.equal(accountRoleLabel('SUPER_ADMIN'), 'Quản trị viên cấp cao')
  assert.equal(accountRoleLabel('MODERATOR'), 'Không xác định')
})

test('password change validation preserves the production three-field rules', () => {
  assert.equal(validatePasswordChange({ currentPassword: '', newPassword: '', confirmPassword: '' }), 'Vui lòng nhập đầy đủ ba ô mật khẩu.')
  assert.equal(validatePasswordChange({ currentPassword: 'old-pass', newPassword: 'short', confirmPassword: 'short' }), 'Mật khẩu mới cần tối thiểu 8 ký tự.')
  assert.equal(validatePasswordChange({ currentPassword: 'old-pass', newPassword: 'new-password', confirmPassword: 'different' }), 'Hai lần nhập mật khẩu mới chưa khớp.')
  assert.equal(validatePasswordChange({ currentPassword: 'same-password', newPassword: 'same-password', confirmPassword: 'same-password' }), 'Mật khẩu mới cần khác mật khẩu hiện tại.')
  assert.equal(validatePasswordChange({ currentPassword: 'old-password', newPassword: 'new-password', confirmPassword: 'new-password' }), '')
})

test('incorrect current password maps to the production-friendly message', () => {
  assert.equal(passwordFriendlyError(new Error('Invalid login credentials')), 'Mật khẩu hiện tại chưa đúng.')
  assert.equal(passwordFriendlyError(new Error('sensitive upstream detail')), 'Chưa đổi được mật khẩu. Vui lòng thử lại.')
})
