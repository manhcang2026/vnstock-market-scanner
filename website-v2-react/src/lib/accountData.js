import { supabase } from './supabase'

function client() {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  return supabase
}

function unwrapRpcResult(data) {
  return Array.isArray(data) && data.length === 1 ? data[0] : data
}

export async function loadMyProfile(userId) {
  const { data, error } = await client()
    .from('profiles')
    .select('display_name,phone,address,role,status,profile_completed')
    .eq('id', userId)
    .maybeSingle()
  if (error) throw error
  return data || {}
}

export async function loadMyAccessContext() {
  const { data, error } = await client().rpc('get_my_access_context')
  if (error) throw error
  return unwrapRpcResult(data) || {}
}

export async function loadMyWatchlistState() {
  const { data, error } = await client().rpc('get_my_watchlist_state')
  if (error) throw error
  return unwrapRpcResult(data) || {}
}

export async function loadActivePlans() {
  const { data, error } = await client()
    .from('plans')
    .select('id,plan_code,display_name,price_vnd,watchlist_limit,change_limit,full_market_access,email_alerts,telegram_alerts,is_recommended')
    .eq('is_active', true)
    .order('price_vnd', { ascending: true })
  if (error) throw error
  return Array.isArray(data) ? data : []
}

export async function saveMyProfile({ displayName, phone, address }) {
  const { data, error } = await client().rpc('save_my_profile', {
    p_display_name: displayName,
    p_phone: phone,
    p_address: address || null,
  })
  if (error) throw error
  return unwrapRpcResult(data)
}

export async function replaceMyWatchlist(symbols) {
  const { data, error } = await client().rpc('replace_my_watchlist', {
    p_symbols: symbols,
  })
  if (error) throw error
  return unwrapRpcResult(data) || {}
}

export async function changeMyPassword({ email, currentPassword, newPassword }) {
  const auth = client().auth
  const { error: verificationError } = await auth.signInWithPassword({
    email,
    password: currentPassword,
  })
  if (verificationError) throw verificationError

  const { data, error } = await auth.updateUser({ password: newPassword })
  if (error) throw error
  return data
}
