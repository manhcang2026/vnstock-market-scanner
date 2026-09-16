import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function IndustryPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="Public Fundamental Research"
        title="So sánh theo ngành"
        description="Màn nghiên cứu cơ bản tiếp tục công khai và tách biệt khỏi CCC Technical Intelligence."
      />
      <PlaceholderPanel title="So sánh doanh nghiệp">
        <p>Dữ liệu financial_latest và metadata sẽ được nối lại sau khi shell React được chốt.</p>
      </PlaceholderPanel>
    </div>
  )
}
