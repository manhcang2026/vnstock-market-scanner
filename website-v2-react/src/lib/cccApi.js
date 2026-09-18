const API_BASE = import.meta.env.VITE_CCC_API_BASE || '/api/v2'

async function requestJson(path, { token, signal } = {}) {
  const headers = {}
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(`${API_BASE}${path}`, { headers, signal })
  let body = null

  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (!response.ok) {
    const error = new Error(body?.message || body?.error || `HTTP ${response.status}`)
    error.status = response.status
    error.body = body
    throw error
  }

  return body
}

export function fetchQuote(symbol, options) {
  return requestJson(`/quote/${encodeURIComponent(symbol)}`, options)
}

export function fetchTechnicalAccess(symbol, options) {
  return requestJson(`/access/${encodeURIComponent(symbol)}`, options)
}

export function fetchPublicStockContext(symbol, options) {
  return requestJson(`/stock-detail/${encodeURIComponent(symbol)}`, options)
}

export function fetchCccIntelligence(symbol, options) {
  return requestJson(`/ccc/${encodeURIComponent(symbol)}`, options)
}

export function fetchRadar(options) {
  return requestJson('/radar', options)
}

export function fetchChart(symbol, query = '', options) {
  const suffix = query ? `?${query}` : ''
  return requestJson(`/chart/${encodeURIComponent(symbol)}${suffix}`, options)
}
