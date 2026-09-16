import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="page">
      <section className="empty-page">
        <strong>Không tìm thấy trang</strong>
        <p>Đường dẫn này chưa tồn tại trong CCC V2.</p>
        <Link to="/">Về Tổng quan</Link>
      </section>
    </div>
  )
}
