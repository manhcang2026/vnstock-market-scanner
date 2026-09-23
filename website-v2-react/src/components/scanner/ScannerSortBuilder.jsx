import { SORT_FIELDS } from '../../lib/scannerSort'

export default function ScannerSortBuilder({ rules, availability, onAdd, onUpdate, onRemove, onMove }) {
  return (
    <div className="scanner-builder" aria-label="Sắp xếp theo thứ tự ưu tiên">
      {rules.map((rule, index) => (
        <div className="scanner-builder-rule" key={rule.id}>
          <div className="scanner-builder-rule-heading">
            <strong>Ưu tiên {index + 1}</strong>
            <span className="scanner-rule-actions">
              <button type="button" className="scanner-rule-icon" disabled={index === 0} aria-label={`Đưa sắp xếp ${index + 1} lên`} onClick={() => onMove(index, -1)}>↑</button>
              <button type="button" className="scanner-rule-icon" disabled={index === rules.length - 1} aria-label={`Đưa sắp xếp ${index + 1} xuống`} onClick={() => onMove(index, 1)}>↓</button>
              <button type="button" className="scanner-rule-icon" aria-label={`Xóa sắp xếp ${index + 1}`} onClick={() => onRemove(rule.id)}>×</button>
            </span>
          </div>
          <label><span>Chỉ tiêu</span><select value={rule.field} onChange={(event) => onUpdate(rule.id, { field: event.target.value, direction: 'asc' })}>{SORT_FIELDS.map((field) => <option key={field.id} value={field.id}>{field.label}</option>)}</select></label>
          <label><span>Thứ tự</span><select value={rule.direction} disabled={!availability[rule.field]} onChange={(event) => onUpdate(rule.id, { direction: event.target.value })}>
            <option value="asc">{rule.field.startsWith('nearMa') ? 'Gần nhất' : ['symbol', 'exchange', 'industry'].includes(rule.field) ? 'A–Z' : 'Thấp nhất'}</option>
            <option value="desc">{rule.field.startsWith('nearMa') ? 'Xa nhất' : ['symbol', 'exchange', 'industry'].includes(rule.field) ? 'Z–A' : 'Cao nhất'}</option>
          </select></label>
          {!availability[rule.field] ? <p className="scanner-unavailable">Chưa có dữ liệu thật cho chỉ tiêu này; sắp xếp chưa áp dụng.</p> : null}
        </div>
      ))}
      <button type="button" className="scanner-builder-add" onClick={onAdd}>+ Thêm sắp xếp</button>
      {!rules.length ? <p className="scanner-rule-hint">Chưa chọn thứ tự sắp xếp.</p> : null}
    </div>
  )
}
