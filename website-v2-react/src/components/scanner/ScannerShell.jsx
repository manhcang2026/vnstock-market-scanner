import ScannerLeftRail from './ScannerLeftRail'
import ScannerRightRail from './ScannerRightRail'

export default function ScannerShell({ mode, children }) {
  return (
    <div className="scanner-workspace">
      <ScannerLeftRail mode={mode} />
      <section className="scanner-center" aria-label="Danh sách cổ phiếu">
        {children}
      </section>
      <ScannerRightRail />
    </div>
  )
}
