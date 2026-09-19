import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

// Public research queries must never inherit the signed-in user's bearer token.
export const publicSupabase = url && publishableKey
  ? createClient(url, publishableKey, {
      auth: {
        storageKey: 'ccc-public-read-anon',
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
      },
    })
  : null
