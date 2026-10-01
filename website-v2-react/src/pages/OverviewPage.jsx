import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function OverviewPage() {
  return (
    <div className="overview-workspace">
      <section className="overview-center">
        <PageHeader
          eyebrow="CCC V4"
          title="Tổng quan"
          description="Không gian tổng hợp để hỏi CCC AI, theo dõi trạng thái CCC và quan sát thị trường."
        />
        <div className="overview-ai-panel">
          <PlaceholderPanel title="Hỏi CCC AI">
            <p>Chưa nối dữ liệu.</p>
          </PlaceholderPanel>
        </div>
        <div className="kpi-grid overview-kpi-grid">
          <article><small>Trạng thái CCC hôm nay</small><strong>—</strong><span>Chưa nối dữ liệu</span></article>
          <article><small>Watchlist của bạn</small><strong>—</strong><span>Chưa nối dữ liệu</span></article>
          <article><small>Chợ chung</small><strong>—</strong><span>Chưa nối dữ liệu</span></article>
        </div>
        <PlaceholderPanel title="Tổng quan · V4 implementation scaffold">
          <p>Các mô-đun đang ở trạng thái cấu trúc. Dữ liệu và tương tác sẽ được nối trong các bước triển khai riêng.</p>
        </PlaceholderPanel>
      </section>

      <aside className="overview-right-rail" aria-label="Ngữ cảnh Tổng quan">
        <section className="overview-context-card">
          <header><h2>Toàn cảnh thị trường</h2></header>
          <div className="overview-index-list">
            {['VN-INDEX', 'VN30', 'HNXINDEX'].map((index) => (
              <div key={index}><span>{index}</span><strong>—</strong><small>Chưa nối dữ liệu</small></div>
            ))}
          </div>
        </section>
        <section className="overview-context-card">
          <header><h2>Tin nổi bật</h2></header>
          <p>Chưa nối dữ liệu</p>
        </section>
        <section className="overview-context-card">
          <header><h2>Thông báo</h2></header>
          <p>Chưa nối dữ liệu</p>
        </section>
      </aside>
    </div>
  )
}
