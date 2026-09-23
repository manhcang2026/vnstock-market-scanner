const panels = {
  ai: { label: 'AI Search', title: 'Tìm cổ phiếu bằng câu hỏi', copy: 'AI Search sẽ giúp tạo bộ lọc từ mô tả của bạn ở bước tiếp theo.' },
  community: { label: 'Cộng đồng', title: 'Cộng đồng', copy: 'Không gian thảo luận sẽ được kết nối ở bước tiếp theo.' },
}

export default function ScannerRightRail({ active, onChange, idPrefix = 'scanner-utility', className = '' }) {
  function onKeyDown(event) {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
    event.preventDefault()
    const next = active === 'ai' ? 'community' : 'ai'
    onChange(next)
    document.getElementById(`${idPrefix}-${next}`)?.focus()
  }

  return (
    <aside className={`scanner-rail scanner-right-rail ${className}`} aria-label="Tiện ích">
      <div className="scanner-utility-tabs" role="tablist" aria-label="Tiện ích danh sách">
        {Object.entries(panels).map(([id, panel]) => (
          <button key={id} id={`${idPrefix}-${id}`} type="button" role="tab" aria-selected={active === id} aria-controls={`${idPrefix}-panel-${id}`} tabIndex={active === id ? 0 : -1} onClick={() => onChange(id)} onKeyDown={onKeyDown}>{panel.label}</button>
        ))}
      </div>
      <div id={`${idPrefix}-panel-${active}`} className="scanner-rail-body" role="tabpanel" aria-labelledby={`${idPrefix}-${active}`}>
        <strong>{panels[active].title}</strong>
        <p>{panels[active].copy}</p>
        {active === 'ai' ? <input type="text" disabled aria-label="AI Search chưa sẵn sàng" placeholder="AI Search · sắp ra mắt" /> : null}
      </div>
    </aside>
  )
}
