import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import OverviewPage from '../pages/OverviewPage'
import ScannerPage from '../pages/ScannerPage'
import IndustryPage from '../pages/IndustryPage'
import FundamentalPage from '../pages/FundamentalPage'
import LoginPage from '../pages/LoginPage'
import ApiTestPage from '../pages/ApiTestPage'
import StockDetailPage from '../pages/StockDetailPage'
import NotFoundPage from '../pages/NotFoundPage'
import V4ScaffoldPage from '../pages/V4ScaffoldPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="thi-truong" element={<ScannerPage initialMode="market" />} />
        <Route path="danh-sach" element={<ScannerPage initialMode="watchlist" />} />
        <Route path="kham-pha" element={<V4ScaffoldPage title="Khám phá" />} />
        <Route path="tin-tuc" element={<V4ScaffoldPage title="Tin tức / Bài viết" />} />
        <Route path="cong-dong" element={<V4ScaffoldPage title="Cộng đồng" />} />
        <Route path="hoc-vien" element={<V4ScaffoldPage title="Học viện" />} />
        <Route path="tai-khoan" element={<V4ScaffoldPage title="Tài khoản & Cài đặt" />} />
        <Route path="mod" element={<V4ScaffoldPage title="Mod Dashboard" />} />
        <Route path="admin" element={<V4ScaffoldPage title="Admin Dashboard" />} />
        <Route path="so-sanh-theo-nganh" element={<IndustryPage />} />
        <Route path="sang-loc-co-ban" element={<FundamentalPage />} />
        <Route path="co-phieu/:symbol" element={<StockDetailPage />} />
        <Route path="dang-nhap" element={<LoginPage />} />
        <Route path="dev/api-test" element={<ApiTestPage />} />
        <Route path="404" element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Route>
    </Routes>
  )
}
