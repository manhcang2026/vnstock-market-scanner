import { supabase } from './supabase'

export async function loadMyWatchlist(expectedUserId) {
  if (!expectedUserId) return null
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')

  const { data: sessionData, error: sessionError } = await supabase.auth.getSession()
  if (sessionError) throw sessionError
  if (!sessionData?.session?.access_token || sessionData.session.user?.id !== expectedUserId) return null

  const { data, error } = await supabase
    .from('user_watchlist')
    .select('symbol,added_at,add_source,base_active')
    .eq('base_active', true)
    .order('added_at', { ascending: true })

  if (error) throw error
  if (!Array.isArray(data)) throw new Error('Phản hồi danh sách theo dõi không hợp lệ.')
  return data
}
