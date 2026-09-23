export function compactVolume(value) {
  const volume = Number(value || 0)
  if (!Number.isFinite(volume)) return '0'

  const format = (unit, suffix) => {
    const scaled = volume / unit
    const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2
    return `${Number(scaled.toFixed(digits))}${suffix}`
  }

  if (volume >= 1_000_000_000) return format(1_000_000_000, 'B')
  if (volume >= 1_000_000) return format(1_000_000, 'M')
  if (volume >= 1_000) return format(1_000, 'K')
  return String(Math.round(volume))
}
