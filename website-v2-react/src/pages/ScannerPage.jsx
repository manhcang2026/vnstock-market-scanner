import { useSearchParams } from 'react-router-dom'
import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function ScannerPage() {
  const [params] = useSearchParams()
  const q = params.get('q') || ''

  return (
    <div className="page">
      <PageHeader
        eyebrow="Scanner universe"
        title="Danh sách cổ phiếu"
        description="Public Market Quote sẽ hiển thị toàn scanner universe; CCC Technical Intelligence tuân entitlement phía server."
      />
      <PlaceholderPanel title="Scanner V2">
        <p>{q ? <>Đang chuẩn bị tìm mã: <strong>{q}</strong>.</> : 'Command bar, bộ lọc nhiều lớp và bảng scanner sẽ được port ở bước sau.'}</p>
      </PlaceholderPanel>
    </div>
  )
}
