import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import AccountChannelsPanel from '../components/account/AccountChannelsPanel'
import AccountLeftRail from '../components/account/AccountLeftRail'
import AccountPlanPanel from '../components/account/AccountPlanPanel'
import AccountProfileCard from '../components/account/AccountProfileCard'
import AccountSecurityPanel from '../components/account/AccountSecurityPanel'
import AccountShell from '../components/account/AccountShell'
import AccountWatchlistCard from '../components/account/AccountWatchlistCard'
import {
  loadActivePlans,
  loadMyAccessContext,
  loadMyProfile,
  loadMyWatchlistState,
} from '../lib/accountData'
import { watchlistFriendlyError } from '../lib/accountHelpers'
import '../styles/account.css'

const loadingResource = () => ({ data: null, loading: true, error: '' })

export default function AccountPage() {
  const { user, ready, signOut } = useAuth()

  if (!ready) {
    return <div className="account-route-loading"><strong>Đang kiểm tra phiên đăng nhập…</strong></div>
  }
  if (!user) return <Navigate to="/dang-nhap" replace />

  const authScope = `user:${user.id}`
  return <AccountPageContent key={authScope} user={user} signOut={signOut} />
}

function AccountPageContent({ user, signOut }) {
  const navigate = useNavigate()
  const [profileState, setProfileState] = useState(loadingResource)
  const [accessState, setAccessState] = useState(loadingResource)
  const [watchlistState, setWatchlistState] = useState(loadingResource)
  const [plansState, setPlansState] = useState(loadingResource)
  const [endingSession, setEndingSession] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  useEffect(() => {
    let active = true

    const load = async (loader, setter, message) => {
      try {
        const data = await loader()
        if (active) setter({ data, loading: false, error: '' })
      } catch (error) {
        if (active) setter({ data: null, loading: false, error: typeof message === 'function' ? message(error) : message })
      }
    }

    load(() => loadMyProfile(user.id), setProfileState, 'Không tải được hồ sơ lúc này.')
    load(loadMyAccessContext, setAccessState, 'Không tải được quyền tài khoản lúc này.')
    load(loadMyWatchlistState, setWatchlistState, watchlistFriendlyError)
    load(loadActivePlans, setPlansState, 'Không tải được danh sách gói lúc này.')

    return () => { active = false }
  }, [user.id])

  async function refreshProfile() {
    const data = await loadMyProfile(user.id)
    setProfileState({ data, loading: false, error: '' })
  }

  async function refreshAccess() {
    try {
      const data = await loadMyAccessContext()
      setAccessState({ data, loading: false, error: '' })
    } catch {
      setAccessState((current) => ({ ...current, loading: false, error: 'Không làm mới được quyền tài khoản lúc này.' }))
    }
  }

  async function handleWatchlistSaved(result) {
    setWatchlistState({ data: result, loading: false, error: '' })
    await refreshAccess()
  }

  async function handleLogout() {
    setEndingSession(true)
    setLogoutError('')
    try {
      await signOut()
      navigate('/dang-nhap', { replace: true })
    } catch {
      setEndingSession(false)
      setLogoutError('Không đăng xuất được. Vui lòng thử lại.')
    }
  }

  if (endingSession) return <div className="account-route-loading"><strong>Đang đăng xuất…</strong></div>

  const displayName = profileState.data?.display_name
    || user.user_metadata?.full_name
    || user.user_metadata?.name
    || user.email?.split('@')[0]
    || 'Tài khoản'

  return (
    <AccountShell
      navigation={<AccountLeftRail />}
      center={(
        <>
          <header className="account-page-heading">
            <div><span className="account-kicker">TRUNG TÂM TÀI KHOẢN</span><h1>Tài khoản</h1><p>Quản lý hồ sơ, gói thành viên và thiết lập cá nhân.</p></div>
            <div className="account-identity"><span>{displayName.slice(0, 1).toUpperCase()}</span><div><strong>{displayName}</strong><small>{user.email}</small></div></div>
          </header>
          <AccountProfileCard
            user={user}
            profileState={profileState}
            onSaved={refreshProfile}
          />
          <AccountWatchlistCard
            watchlistState={watchlistState}
            access={accessState.data}
            onSaved={handleWatchlistSaved}
          />
        </>
      )}
      context={(
        <>
          <AccountPlanPanel accessState={accessState} watchlistState={watchlistState} plansState={plansState} />
          <AccountChannelsPanel user={user} accessState={accessState} plansState={plansState} />
          <AccountSecurityPanel user={user} profile={profileState.data} logoutError={logoutError} onLogout={handleLogout} />
        </>
      )}
    />
  )
}
