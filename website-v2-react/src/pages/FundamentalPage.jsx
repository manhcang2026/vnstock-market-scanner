import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function FundamentalPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="Public Fundamental Research"
        title="Sàng lọc cơ bản"
        description="Giữ nguyên nguyên tắc điểm số theo phần dữ liệu có thể chấm và hiển thị rõ coverage."
      />
      <PlaceholderPanel title="Bộ lọc cơ bản">
        <p>Phần scoring và dữ liệu quý hiện chưa được port ở checkpoint foundation.</p>
      </PlaceholderPanel>
    </div>
  )
}
