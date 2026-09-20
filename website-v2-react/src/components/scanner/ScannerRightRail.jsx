import { useState } from 'react'

const panels = {
  ai: { label: 'AI Search', title: 'Tìm cổ phiếu bằng câu hỏi', copy: 'AI Search sẽ giúp tạo bộ lọc từ mô tả của bạn ở bước tiếp theo.' },
  community: { label: 'Cộng đồng', title: 'Cộng đồng', copy: 'Không gian thảo luận sẽ được kết nối ở bước tiếp theo.' },
}

export default function ScannerRightRail() {
  const [active, setActive] = useState('ai')

  function onKeyDown(event) {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
    event.preventDefault()
    const next = active === 'ai' ? 'community' : 'ai'
    setActive(next)
    document.getElementById(`scanner-utility-${next}`)?.focus()
  }

  return (
    <aside className="scanner-rail scanner-right-rail" aria-label="Tiện ích">
      <div className="scanner-utility-tabs" role="tablist" aria-label="Tiện ích danh sách">
        {Object.entries(panels).map(([id, panel]) => (
          <button key={id} id={`scanner-utility-${id}`} type="button" role="tab" aria-selected={active === id} aria-controls={`scanner-utility-panel-${id}`} tabIndex={active === id ? 0 : -1} onClick={() => setActive(id)} onKeyDown={onKeyDown}>{panel.label}</button>
        ))}
      </div>
      <div id={`scanner-utility-panel-${active}`} className="scanner-rail-body" role="tabpanel" aria-labelledby={`scanner-utility-${active}`}>
        <strong>{panels[active].title}</strong>
        <p>{panels[active].copy}</p>
        {active === 'ai' ? <input type="text" disabled aria-label="AI Search chưa sẵn sàng" placeholder="AI Search · sắp ra mắt" /> : null}
      </div>
    </aside>
  )
}
