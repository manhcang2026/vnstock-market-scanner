import { useState } from 'react'
import ScannerFilterBuilder from './ScannerFilterBuilder'
import ScannerSortBuilder from './ScannerSortBuilder'

export default function ScannerMobileFilters({ filterBuilder, sortBuilder, activeCount }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="scanner-mobile-filters">
      <button type="button" aria-expanded={open} aria-controls="scanner-mobile-filter-panel" onClick={() => setOpen((value) => !value)}>
        Bộ lọc{activeCount ? ` (${activeCount})` : ''}
      </button>
      {open ? (
        <div id="scanner-mobile-filter-panel" className="scanner-mobile-filter-panel">
          <h3>Bộ lọc</h3>
          <ScannerFilterBuilder {...filterBuilder} />
          <h3>Sắp xếp</h3>
          <ScannerSortBuilder {...sortBuilder} />
        </div>
      ) : null}
    </div>
  )
}
