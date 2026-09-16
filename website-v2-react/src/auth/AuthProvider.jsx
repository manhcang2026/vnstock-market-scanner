import { useEffect, useMemo, useState } from 'react'
import { supabase } from '../lib/supabase'
import { AuthContext } from './AuthContext'

export function AuthProvider({ children }) {
  const hasSupabase = Boolean(supabase)
  const [session, setSession] = useState(null)
  const [ready, setReady] = useState(!hasSupabase)
  const [authError, setAuthError] = useState(
    hasSupabase ? '' : 'Thiếu cấu hình Supabase.',
  )

  useEffect(() => {
    if (!supabase) return undefined

    let active = true

    supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return
      if (error) setAuthError(error.message)
      setSession(data?.session ?? null)
      setReady(true)
    })

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return
      setSession(nextSession)
      setReady(true)
      setAuthError('')
    })

    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  const value = useMemo(() => {
    async function signInWithPassword(email, password) {
      if (!supabase) throw new Error('Supabase chưa được cấu hình.')
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      return data
    }

    async function signInWithGoogle() {
      if (!supabase) throw new Error('Supabase chưa được cấu hình.')
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/`,
        },
      })
      if (error) throw error
      return data
    }

    async function signOut() {
      if (!supabase) return
      const { error } = await supabase.auth.signOut()
      if (error) throw error
    }

    return {
      session,
      user: session?.user ?? null,
      accessToken: session?.access_token ?? '',
      ready,
      authError,
      signInWithPassword,
      signInWithGoogle,
      signOut,
    }
  }, [session, ready, authError])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
