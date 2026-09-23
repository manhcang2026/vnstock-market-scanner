const tabs = [
  { id: 'watchlist', label: 'Đã theo dõi' },
  { id: 'market', label: 'Toàn thị trường' },
  { id: 'advanced', label: 'Tìm kiếm nâng cao' },
]

export default function ScannerTabs({ activeTab, onChange }) {
  function onKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextIndex = event.key === 'Home' ? 0
      : event.key === 'End' ? tabs.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    onChange(tabs[nextIndex].id)
    document.getElementById(`scanner-tab-${tabs[nextIndex].id}`)?.focus()
  }

  return (
    <div className="scanner-tabs" role="tablist" aria-label="Chế độ danh sách">
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          id={`scanner-tab-${tab.id}`}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`scanner-panel-${tab.id}`}
          tabIndex={activeTab === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
