const SESSION_LABELS = {
  OPEN_AUCTION: 'ATO',
  AM_CONTINUOUS: 'Đang giao dịch',
  PM_CONTINUOUS: 'Đang giao dịch',
  CONTINUOUS: 'Đang giao dịch',
  LUNCH_BREAK: 'Nghỉ trưa',
  CLOSE_AUCTION: 'ATC',
  POST_TRADING: 'Sau phiên',
  CLOSED: 'Đóng cửa',
}

const ACTIVE_SESSIONS = new Set([
  'OPEN_AUCTION', 'AM_CONTINUOUS', 'PM_CONTINUOUS', 'CONTINUOUS', 'CLOSE_AUCTION',
])

const vietnamClock = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Ho_Chi_Minh',
  weekday: 'short',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export function describeMarketSession(quote, publicContext, now = new Date()) {
  const parts = Object.fromEntries(vietnamClock.formatToParts(now).map(({ type, value }) => [type, value]))
  const today = `${parts.year}-${parts.month}-${parts.day}`
  const minuteOfDay = Number(parts.hour) * 60 + Number(parts.minute)
  const outsideHours = ['Sat', 'Sun'].includes(parts.weekday)
    || minuteOfDay < 9 * 60
    || minuteOfDay >= 15 * 60

  // A last-trading-day session is not today's market state.
  if (outsideHours) {
    return { label: 'Đóng cửa', raw: 'CLOSED', semantic: true, marketActive: false }
  }

  const source = publicContext?.session_type ? publicContext : quote
  const raw = String(source?.session_type || source?.trading_session || '').trim().toUpperCase()
  const sourceDate = String(source?.trading_date || '').slice(0, 10)
  if (sourceDate === today && SESSION_LABELS[raw]) {
    return {
      label: SESSION_LABELS[raw],
      raw,
      semantic: true,
      marketActive: ACTIVE_SESSIONS.has(raw),
    }
  }

  return { label: 'Phiên chưa xác định', raw: '', semantic: false, marketActive: true }
}
