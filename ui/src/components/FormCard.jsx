import React, { useState } from 'react'

/**
 * Renders a dynamic CONFIG form card (LLM-built copy, backend-grounded fields).
 * Props:
 *   form: { title, description, fields:[{name,heading,description,example,type,required,value,error,options}], actions }
 *   onSubmit(values): structured submission
 *   onCancel(): cancel the flow
 *
 * When `form.repeatable` is set, a multi-row variant is rendered instead: the client can
 * add/remove device rows and submits them as `{ devices: [ {field: value}, ... ] }`. No
 * extra LLM call is involved — the backend merges the batch deterministically.
 */
function FormCard({ form, onSubmit, onCancel }) {
  if (form && form.repeatable) {
    return <RepeatableFormCard form={form} onSubmit={onSubmit} onCancel={onCancel} />
  }
  const init = {}
  ;(form.fields || []).forEach(f => { init[f.name] = f.value != null ? String(f.value) : '' })
  const [values, setValues] = useState(init)
  const [submitted, setSubmitted] = useState(false)

  const setField = (name, v) => setValues(prev => ({ ...prev, [name]: v }))

  const requiredNames = (form.fields || []).filter(f => f.required).map(f => f.name)
  const allRequiredFilled = requiredNames.every(n => String(values[n] ?? '').trim() !== '')

  const handleSubmit = () => {
    if (!allRequiredFilled || submitted) return
    // send only non-empty values; backend validates + re-pops if needed
    const payload = {}
    Object.entries(values).forEach(([k, v]) => { if (String(v).trim() !== '') payload[k] = v })
    setSubmitted(true)
    onSubmit(payload)
  }

  const handleClear = () => setValues(prev => {
    const cleared = {}
    Object.keys(prev).forEach(k => { cleared[k] = '' })
    return cleared
  })

  const actions = form.actions || { submit: 'Continue', clear: 'Clear', cancel: 'Cancel' }

  const inputStyle = {
    width: '100%', padding: '6px 8px', borderRadius: 4, border: '1px solid #ccc',
    fontSize: '0.9em', boxSizing: 'border-box', background: submitted ? '#f0f0f0' : '#fff'
  }

  const renderInput = (f) => {
    const common = {
      value: values[f.name] ?? '',
      disabled: submitted,
      placeholder: f.example ? `e.g. ${f.example}` : '',
      onChange: (e) => setField(f.name, e.target.value),
      style: inputStyle,
    }
    if (f.type === 'select') {
      return (
        <select {...common}>
          <option value="">— select —</option>
          {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      )
    }
    return <input type={f.type === 'number' ? 'number' : f.type === 'password' ? 'password' : 'text'} {...common} />
  }

  return (
    <div style={{ border: '1px solid #d9d9e3', borderRadius: 8, padding: 14, background: '#fafafe', margin: '4px 0', maxWidth: 460 }}>
      <div style={{ fontWeight: 'bold', fontSize: '1.05em', marginBottom: 2 }}>{form.title}</div>
      {form.description && <div style={{ color: '#666', fontSize: '0.85em', marginBottom: 10 }}>{form.description}</div>}

      {(form.fields || []).map(f => (
        <div key={f.name} style={{ marginBottom: 10 }}>
          <label style={{ display: 'block', fontSize: '0.85em', fontWeight: 600, marginBottom: 2 }}>
            {f.heading}{f.required && <span style={{ color: '#d33' }}> *</span>}
          </label>
          {f.description && <div style={{ color: '#888', fontSize: '0.78em', marginBottom: 4 }}>{f.description}</div>}
          {renderInput(f)}
          {f.error && <div style={{ color: '#d33', fontSize: '0.78em', marginTop: 3 }}>{f.error}</div>}
        </div>
      ))}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button
          onClick={handleSubmit}
          disabled={!allRequiredFilled || submitted}
          style={{
            padding: '6px 16px', borderRadius: 4, border: 'none', fontSize: '0.9em',
            cursor: (allRequiredFilled && !submitted) ? 'pointer' : 'not-allowed',
            background: (allRequiredFilled && !submitted) ? '#667eea' : '#c7c7d1',
            color: '#fff', fontWeight: 600,
          }}
        >{actions.submit}</button>
        <button onClick={handleClear} disabled={submitted}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #ccc', background: '#fff', cursor: submitted ? 'not-allowed' : 'pointer', fontSize: '0.9em' }}
        >{actions.clear}</button>
        <button onClick={() => { if (!submitted) { setSubmitted(true); onCancel() } }} disabled={submitted}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #e0a3a3', background: '#fff', color: '#c0392b', cursor: submitted ? 'not-allowed' : 'pointer', fontSize: '0.9em' }}
        >{actions.cancel}</button>
      </div>
      {submitted && <div style={{ color: '#888', fontSize: '0.78em', marginTop: 8 }}>Submitted.</div>}
    </div>
  )
}

/**
 * Multi-device variant: renders the same field set as repeatable rows. Submits
 * { devices: [ {field: value}, ... ] }. Row-level errors come back as form.row_errors
 * keyed by row index; client state (incl. passwords) is retained across re-validation.
 */
function RepeatableFormCard({ form, onSubmit, onCancel }) {
  const fields = form.fields || []
  const blankRow = () => fields.reduce((r, f) => { r[f.name] = ''; return r }, {})
  const [rows, setRows] = useState([blankRow()])
  const [submitted, setSubmitted] = useState(false)
  const rowErrors = form.row_errors || {}

  const setCell = (i, name, v) =>
    setRows(prev => prev.map((row, idx) => (idx === i ? { ...row, [name]: v } : row)))
  const addRow = () => setRows(prev => [...prev, blankRow()])
  const removeRow = (i) => setRows(prev => (prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev))

  const requiredNames = fields.filter(f => f.required).map(f => f.name)
  const rowFilled = (row) => requiredNames.every(n => String(row[n] ?? '').trim() !== '')
  // a row counts if it has any value; all non-empty rows must have their required fields.
  const nonEmptyRows = rows.filter(row => Object.values(row).some(v => String(v).trim() !== ''))
  const canSubmit = nonEmptyRows.length > 0 && nonEmptyRows.every(rowFilled) && !submitted

  const handleSubmit = () => {
    if (!canSubmit) return
    const devices = nonEmptyRows.map(row => {
      const out = {}
      Object.entries(row).forEach(([k, v]) => { if (String(v).trim() !== '') out[k] = v })
      return out
    })
    setSubmitted(true)
    onSubmit({ devices })
  }

  const actions = form.actions || {}
  const inputStyle = {
    width: '100%', padding: '6px 8px', borderRadius: 4, border: '1px solid #ccc',
    fontSize: '0.9em', boxSizing: 'border-box', background: submitted ? '#f0f0f0' : '#fff'
  }
  const renderInput = (i, f) => {
    const common = {
      value: rows[i][f.name] ?? '', disabled: submitted,
      placeholder: f.example ? `e.g. ${f.example}` : '',
      onChange: (e) => setCell(i, f.name, e.target.value), style: inputStyle,
    }
    if (f.type === 'select') {
      return (
        <select {...common}>
          <option value="">— select —</option>
          {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      )
    }
    return <input type={f.type === 'number' ? 'number' : f.type === 'password' ? 'password' : 'text'} {...common} />
  }

  return (
    <div style={{ border: '1px solid #d9d9e3', borderRadius: 8, padding: 14, background: '#fafafe', margin: '4px 0', maxWidth: 520 }}>
      <div style={{ fontWeight: 'bold', fontSize: '1.05em', marginBottom: 2 }}>{form.title}</div>
      {form.description && <div style={{ color: '#666', fontSize: '0.85em', marginBottom: 10 }}>{form.description}</div>}

      {rows.map((row, i) => (
        <div key={i} style={{ border: '1px solid #e3e3ee', borderRadius: 6, padding: 10, marginBottom: 10, background: '#fff' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontWeight: 600, fontSize: '0.85em', color: '#555' }}>Device {i + 1}</span>
            {rows.length > 1 && !submitted && (
              <button onClick={() => removeRow(i)}
                style={{ border: 'none', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '0.85em' }}>
                {actions.removeRow || 'Remove'}
              </button>
            )}
          </div>
          {fields.map(f => (
            <div key={f.name} style={{ marginBottom: 8 }}>
              <label style={{ display: 'block', fontSize: '0.82em', fontWeight: 600, marginBottom: 2 }}>
                {f.heading}{f.required && <span style={{ color: '#d33' }}> *</span>}
              </label>
              {renderInput(i, f)}
              {rowErrors[i] && rowErrors[i][f.name] && (
                <div style={{ color: '#d33', fontSize: '0.78em', marginTop: 3 }}>{rowErrors[i][f.name]}</div>
              )}
            </div>
          ))}
        </div>
      ))}

      {!submitted && (
        <button onClick={addRow}
          style={{ padding: '5px 12px', borderRadius: 4, border: '1px dashed #9a9ad1', background: '#fff', color: '#5a5ad1', cursor: 'pointer', fontSize: '0.85em', marginBottom: 10 }}>
          + {actions.addRow || 'Add device'}
        </button>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
        <button onClick={handleSubmit} disabled={!canSubmit}
          style={{
            padding: '6px 16px', borderRadius: 4, border: 'none', fontSize: '0.9em',
            cursor: canSubmit ? 'pointer' : 'not-allowed',
            background: canSubmit ? '#667eea' : '#c7c7d1', color: '#fff', fontWeight: 600,
          }}>{actions.submit || 'Continue'}</button>
        <button onClick={() => { if (!submitted) { setSubmitted(true); onCancel() } }} disabled={submitted}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #e0a3a3', background: '#fff', color: '#c0392b', cursor: submitted ? 'not-allowed' : 'pointer', fontSize: '0.9em' }}
        >{actions.cancel || 'Cancel'}</button>
      </div>
      {submitted && <div style={{ color: '#888', fontSize: '0.78em', marginTop: 8 }}>Submitted.</div>}
    </div>
  )
}

export default FormCard
