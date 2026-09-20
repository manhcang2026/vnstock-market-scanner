import ScannerLeftRail from './ScannerLeftRail'
import ScannerRightRail from './ScannerRightRail'

export default function ScannerShell({ mode, filterBuilder, sortBuilder, utility, children }) {
  return (
    <div className="scanner-workspace">
      <ScannerLeftRail mode={mode} filterBuilder={filterBuilder} sortBuilder={sortBuilder} />
      <section className="scanner-center" aria-label="Danh sách cổ phiếu">
        {children}
      </section>
      <ScannerRightRail active={utility.active} onChange={utility.onChange} className="scanner-desktop-utility" />
    </div>
  )
}
