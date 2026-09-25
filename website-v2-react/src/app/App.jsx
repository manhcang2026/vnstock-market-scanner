import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import OverviewPage from '../pages/OverviewPage'
import ScannerPage from '../pages/ScannerPage'
import IndustryPage from '../pages/IndustryPage'
import FundamentalPage from '../pages/FundamentalPage'
import LoginPage from '../pages/LoginPage'
import ApiTestPage from '../pages/ApiTestPage'
import StockDetailPage from '../pages/StockDetailPage'
import AccountPage from '../pages/AccountPage'
import NotFoundPage from '../pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="danh-sach" element={<ScannerPage />} />
        <Route path="so-sanh-theo-nganh" element={<IndustryPage />} />
        <Route path="sang-loc-co-ban" element={<FundamentalPage />} />
        <Route path="co-phieu/:symbol" element={<StockDetailPage />} />
        <Route path="tai-khoan" element={<AccountPage />} />
        <Route path="dang-nhap" element={<LoginPage />} />
        <Route path="dev/api-test" element={<ApiTestPage />} />
        <Route path="404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Route>
    </Routes>
  )
}
