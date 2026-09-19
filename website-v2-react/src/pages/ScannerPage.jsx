import { useSearchParams } from 'react-router-dom'
import PageHeader from '../components/ui/PageHeader'
import PlaceholderPanel from '../components/ui/PlaceholderPanel'

export default function ScannerPage() {
  const [params] = useSearchParams()
  const q = params.get('q') || ''
  const lookupUnavailable = params.get('lookup') === 'unavailable'

  return (
    <div className="page">
      <PageHeader
        eyebrow="Scanner universe"
        title="Danh sách cổ phiếu"
        description="Public Market Quote sẽ hiển thị toàn scanner universe; CCC Technical Intelligence tuân entitlement phía server."
      />
      <PlaceholderPanel title="Scanner V2">
        <p>{q
          ? lookupUnavailable
            ? <>Chưa thể kiểm tra mã <strong>{q}</strong> vì danh mục cổ phiếu tạm thời không sẵn sàng. Hãy thử lại sau.</>
            : <>Không tìm thấy mã duy nhất cho <strong>{q}</strong> trong danh mục cổ phiếu. Bộ quét chi tiết sẽ được bổ sung ở bước sau.</>
          : 'Command bar, bộ lọc nhiều lớp và bảng scanner sẽ được port ở bước sau.'}</p>
      </PlaceholderPanel>
    </div>
  )
}
