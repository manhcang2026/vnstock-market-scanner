import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function OverviewPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="CCC V2 · React foundation"
        title="Tổng quan"
        description="Khung giao diện mới đang được port theo nguyên tắc giữ 80–90% cảm giác quen thuộc của Chuyện Chợ Chứng."
      />
      <div className="kpi-grid">
        <article><small>Market Pulse</small><strong>—</strong><span>Sẽ nối realtime</span></article>
        <article><small>Dòng tiền đáng chú ý</small><strong>—</strong><span>Signal Engine V2</span></article>
        <article><small>Đã xác nhận</small><strong>—</strong><span>State machine V2</span></article>
        <article><small>Áp lực bán</small><strong>—</strong><span>Bearish branch V2</span></article>
      </div>
      <PlaceholderPanel title="Vùng discovery">
        <p>Chưa nối dữ liệu thật ở checkpoint này. Mục tiêu hiện tại là xác nhận App Shell, routing, responsive và Light/Dark hoạt động ổn định.</p>
      </PlaceholderPanel>
    </div>
  )
}
