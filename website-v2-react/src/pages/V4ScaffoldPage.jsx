import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function V4ScaffoldPage({ title }) {
  return (
    <div className="page v4-scaffold-page">
      <PageHeader
        eyebrow="CCC V4"
        title={title}
        description="Khung triển khai V4 cho khu vực này đã sẵn sàng trong App Shell dùng chung."
      />
      <PlaceholderPanel title={`${title} · V4 implementation scaffold`}>
        <p>Chưa nối dữ liệu hoặc chức năng backend trong bước dựng shell này.</p>
      </PlaceholderPanel>
    </div>
  )
}
