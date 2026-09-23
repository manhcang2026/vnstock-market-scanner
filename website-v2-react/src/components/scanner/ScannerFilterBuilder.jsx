import { FILTER_FIELDS, NUMERIC_OPERATORS, configuredCondition } from '../../lib/scannerFilters'

export default function ScannerFilterBuilder({ conditions, availability, options, onAdd, onUpdate, onRemove }) {
  return (
    <div className="scanner-builder" aria-label="Điều kiện lọc">
      {conditions.map((condition, index) => {
        const definition = FILTER_FIELDS.find((field) => field.id === condition.field)
        const available = Boolean(availability[condition.field])
        return (
          <div className="scanner-builder-rule" key={condition.id}>
            <div className="scanner-builder-rule-heading">
              <strong>Điều kiện {index + 1}</strong>
              <button type="button" className="scanner-rule-icon" aria-label={`Xóa điều kiện ${index + 1}`} onClick={() => onRemove(condition.id)}>×</button>
            </div>
            <label>
              <span>Chỉ tiêu</span>
              <select value={condition.field} onChange={(event) => onUpdate(condition.id, { field: event.target.value, operator: 'lte', value: '', valueTo: '', values: [] })}>
                {FILTER_FIELDS.map((field) => <option key={field.id} value={field.id}>{field.label}</option>)}
              </select>
            </label>
            {definition?.type === 'category' ? (
              <div className="scanner-category-options" role="group" aria-label={`Giá trị ${definition.label}`}>
                {(options[condition.field] || []).map((option) => (
                  <label key={option.value} className="scanner-check-option">
                    <input type="checkbox" value={option.value} disabled={!available} checked={condition.values?.includes(option.value) || false} onChange={(event) => onUpdate(condition.id, { values: event.target.checked ? [...(condition.values || []), option.value] : (condition.values || []).filter((value) => value !== option.value) })} />
                    <span>{option.label}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="scanner-numeric-controls">
                <label><span>So sánh</span><select value={condition.operator} disabled={!available} onChange={(event) => onUpdate(condition.id, { operator: event.target.value })}>{NUMERIC_OPERATORS.map((operator) => <option key={operator.id} value={operator.id}>{operator.label}</option>)}</select></label>
                <label><span>Giá trị</span><input type="number" inputMode="decimal" step="any" min={condition.field.startsWith('nearMa') || ['price', 'volume'].includes(condition.field) ? 0 : undefined} value={condition.value ?? ''} disabled={!available} onChange={(event) => onUpdate(condition.id, { value: event.target.value })} /></label>
                {condition.operator === 'between' ? <label><span>Đến</span><input type="number" inputMode="decimal" step="any" min={condition.field.startsWith('nearMa') || ['price', 'volume'].includes(condition.field) ? 0 : undefined} value={condition.valueTo ?? ''} disabled={!available} onChange={(event) => onUpdate(condition.id, { valueTo: event.target.value })} /></label> : null}
              </div>
            )}
            {!available ? <p className="scanner-unavailable">Chưa có dữ liệu thật cho chỉ tiêu này; điều kiện chưa áp dụng.</p> : !configuredCondition(condition) ? <p className="scanner-rule-hint">Chọn giá trị để áp dụng.</p> : null}
          </div>
        )
      })}
      <button type="button" className="scanner-builder-add" onClick={onAdd}>+ Thêm điều kiện</button>
      {!conditions.length ? <p className="scanner-rule-hint">Chưa áp dụng bộ lọc.</p> : null}
    </div>
  )
}
