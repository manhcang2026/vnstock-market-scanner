import ScannerRightRail from './ScannerRightRail'

export default function ScannerShell({ utility, children }) {
  return (
    <div className="scanner-workspace">
      <section className="scanner-center" aria-label="Danh sách cổ phiếu">
        {children}
      </section>
      <ScannerRightRail active={utility.active} onChange={utility.onChange} className="scanner-desktop-utility" />
    </div>
  )
}
