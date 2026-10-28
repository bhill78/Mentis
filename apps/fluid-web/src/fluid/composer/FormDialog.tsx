import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Id, Post } from '../store'
import { Prose } from '../../prose'
import {
  STARTER_FORMS,
  formatFormMarkdown,
  loadSavedForms,
  addOrUpdateSavedForm,
  deleteSavedForm,
  renameSavedForm,
  slugifyName,
  type BuilderFieldType,
  type FormFieldRow,
  type SavedForm,
} from './formsStorage'
import './formDialog.css'

export type FormType = 'feedback' | 'poll' | 'survey' | 'custom'

export interface FormDialogProps {
  conversation: Id | null
  convName: string
  replyTo: Id | null
  parent?: Post
  existingText: string
  onInsert: (block: string) => void
  onClose: () => void
  bind: (handler: (e: React.KeyboardEvent) => boolean) => void
}

export { formatFormMarkdown }

function isChoiceType(type: BuilderFieldType): boolean {
  return type === 'radio' || type === 'select' || type === 'multi' || type === 'rating'
}

function cloneFields(fields: FormFieldRow[]): FormFieldRow[] {
  return fields.map((f) => ({ ...f }))
}

export default function FormDialog({
  conversation: _conversation,
  convName,
  replyTo,
  parent,
  existingText,
  onInsert,
  onClose,
  bind,
}: FormDialogProps) {
  const uid = useId()
  const [savedForms, setSavedForms] = useState<SavedForm[]>(() => loadSavedForms())
  const [activeStarterId, setActiveStarterId] = useState<string>('feedback')
  const [activeSavedId, setActiveSavedId] = useState<string | null>(null)

  const initialStarter = STARTER_FORMS.find((s) => s.id === 'feedback') ?? STARTER_FORMS[0]
  const [title, setTitle] = useState(initialStarter.title)
  const [description, setDescription] = useState(initialStarter.description ?? '')
  const [fields, setFields] = useState<FormFieldRow[]>(() => cloneFields(initialStarter.fields))

  // Save / Rename prompt state
  const [isPromptingSave, setIsPromptingSave] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [isPromptingRename, setIsPromptingRename] = useState(false)
  const [renameValue, setRenameValue] = useState('')

  const titleInputRef = useRef<HTMLInputElement>(null)
  const saveInputRef = useRef<HTMLInputElement>(null)

  // Context determination
  const postRef = parent?.number != null ? `Post #${parent.number}` : (replyTo ? `Post #${replyTo.slice(4, 10)}` : null)
  const convRef = parent?.home_name ?? convName ?? 'this conversation'
  const contextDisplay = replyTo
    ? `Replying to ${postRef} in ${convRef}`
    : `Conversation: ${convRef}`

  const selectStarter = (starterId: string) => {
    const starter = STARTER_FORMS.find((s) => s.id === starterId)
    if (!starter) return
    setActiveStarterId(starterId)
    setActiveSavedId(null)
    setTitle(starter.title)
    setDescription(starter.description ?? '')
    setFields(cloneFields(starter.fields))
    setIsPromptingSave(false)
    setIsPromptingRename(false)
  }

  const selectSaved = (savedId: string) => {
    if (!savedId) {
      selectStarter(activeStarterId || 'feedback')
      return
    }
    const found = savedForms.find((f) => f.id === savedId)
    if (!found) return
    setActiveSavedId(savedId)
    setActiveStarterId('')
    setTitle(found.title)
    setDescription(found.description ?? '')
    setFields(cloneFields(found.fields))
    setIsPromptingSave(false)
    setIsPromptingRename(false)
  }

  // Field manipulation
  const addField = () => {
    const newIdx = fields.length + 1
    const newField: FormFieldRow = {
      id: `field_${newIdx}`,
      label: `Field ${newIdx}`,
      type: 'text',
      options: '',
      required: false,
    }
    setFields((prev) => [...prev, newField])
  }

  const updateField = (index: number, patch: Partial<FormFieldRow>) => {
    setFields((prev) => {
      const next = [...prev]
      const current = next[index]
      if (!current) return prev
      const updated = { ...current, ...patch }
      // If type changed to rating and options empty, suggest default 1-5 rating options
      if (patch.type === 'rating' && !updated.options) {
        updated.options = '1, 2, 3, 4, 5'
      } else if (patch.type === 'radio' && !updated.options) {
        updated.options = 'Option A, Option B'
      } else if (patch.type === 'multi' && !updated.options) {
        updated.options = 'Option 1, Option 2'
      }
      next[index] = updated
      return next
    })
  }

  const removeField = (index: number) => {
    if (fields.length <= 1) return
    setFields((prev) => prev.filter((_, i) => i !== index))
  }

  const moveField = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= fields.length) return
    setFields((prev) => {
      const next = [...prev]
      const temp = next[index]
      next[index] = next[target]
      next[target] = temp
      return next
    })
  }

  // Save / Rename / Delete
  const handleStartSave = () => {
    const defaultName = activeSavedId
      ? `${savedForms.find((f) => f.id === activeSavedId)?.name ?? 'Form'} (copy)`
      : `${title || 'My Form'}`
    setSaveName(defaultName)
    setIsPromptingSave(true)
    setIsPromptingRename(false)
    setTimeout(() => saveInputRef.current?.focus(), 50)
  }

  const handleConfirmSave = () => {
    const name = saveName.trim()
    if (!name) return
    const id = `form_${Date.now()}`
    const newForm: SavedForm = {
      id,
      name,
      title: title.trim() || name,
      description: description.trim(),
      fields: cloneFields(fields),
    }
    const updated = addOrUpdateSavedForm(newForm)
    setSavedForms(updated)
    setActiveSavedId(id)
    setActiveStarterId('')
    setIsPromptingSave(false)
  }

  const handleUpdateCurrentSaved = () => {
    if (!activeSavedId) return
    const current = savedForms.find((f) => f.id === activeSavedId)
    if (!current) return
    const updatedForm: SavedForm = {
      ...current,
      title: title.trim() || current.name,
      description: description.trim(),
      fields: cloneFields(fields),
    }
    const updated = addOrUpdateSavedForm(updatedForm)
    setSavedForms(updated)
  }

  const handleStartRename = () => {
    if (!activeSavedId) return
    const current = savedForms.find((f) => f.id === activeSavedId)
    if (!current) return
    setRenameValue(current.name)
    setIsPromptingRename(true)
    setIsPromptingSave(false)
  }

  const handleConfirmRename = () => {
    if (!activeSavedId) return
    const val = renameValue.trim()
    if (!val) return
    const updated = renameSavedForm(activeSavedId, val)
    setSavedForms(updated)
    setIsPromptingRename(false)
  }

  const handleDeleteSaved = () => {
    if (!activeSavedId) return
    const updated = deleteSavedForm(activeSavedId)
    setSavedForms(updated)
    setActiveSavedId(null)
    selectStarter('feedback')
  }

  // Form insertion
  const currentFormName = useMemo(() => {
    if (activeSavedId) {
      const s = savedForms.find((f) => f.id === activeSavedId)
      if (s) return s.name
    }
    return activeStarterId || 'form'
  }, [activeSavedId, savedForms, activeStarterId])

  const currentMarkdown = useMemo(() => {
    const name = slugifyName(title, currentFormName, existingText)
    return formatFormMarkdown({
      title,
      description,
      name,
      fields,
    })
  }, [title, description, currentFormName, existingText, fields])

  const handleInsert = () => {
    onInsert(currentMarkdown)
  }

  useEffect(() => {
    bind((e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isPromptingSave) {
          setIsPromptingSave(false)
          return true
        }
        if (isPromptingRename) {
          setIsPromptingRename(false)
          return true
        }
        onClose()
        return true
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleInsert()
        return true
      }
      return false
    })
  }, [bind, currentMarkdown, isPromptingSave, isPromptingRename])

  useEffect(() => {
    titleInputRef.current?.focus()
  }, [])

  return (
    <div className="fc-form-dialog" role="dialog" aria-label="Forms settings" data-template={activeSavedId ? 'saved' : activeStarterId}>
      <div className="fc-form-head">
        <div className="fc-form-title-row">
          <span className="fc-form-icon" aria-hidden="true">📋</span>
          <span className="fc-form-heading">Forms</span>
        </div>

        <div className="fc-form-types" role="tablist" aria-label="Starting form template">
          {STARTER_FORMS.map((s) => (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={activeStarterId === s.id && !activeSavedId}
              className={'fc-form-type-btn' + (activeStarterId === s.id && !activeSavedId ? ' on' : '')}
              data-type={s.id}
              onClick={() => selectStarter(s.id)}
            >
              {s.name}
            </button>
          ))}
        </div>

        {savedForms.length > 0 && (
          <div className="fc-form-saved-row">
            <label className="fc-form-saved-label" htmlFor={`${uid}-saved-select`}>Saved forms:</label>
            <select
              id={`${uid}-saved-select`}
              className="fc-form-input fc-form-saved-select"
              value={activeSavedId ?? ''}
              onChange={(e) => selectSaved(e.target.value)}
              aria-label="Select saved form"
            >
              <option value="">— Select a saved form —</option>
              {savedForms.map((sf) => (
                <option key={sf.id} value={sf.id}>
                  {sf.name}
                </option>
              ))}
            </select>
            {activeSavedId && (
              <div className="fc-form-saved-actions">
                <button
                  type="button"
                  className="fc-form-quiet-btn"
                  onClick={handleStartRename}
                  title="Rename saved form"
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="fc-form-quiet-btn fc-form-del-link"
                  onClick={handleDeleteSaved}
                  title="Delete saved form"
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="fc-form-context">
        <span className="fc-form-context-badge">Context</span>
        <span className="fc-form-context-text" title={contextDisplay}>
          {contextDisplay}
        </span>
      </div>

      <form className="fc-form-body" onSubmit={(e) => { e.preventDefault(); handleInsert(); }}>
        <div className="fc-form-field">
          <label htmlFor={`${uid}-title-input`}>Title</label>
          <input
            id={`${uid}-title-input`}
            ref={titleInputRef}
            type="text"
            className="fc-form-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Form title"
            aria-label="Form title"
          />
        </div>

        <div className="fc-form-field">
          <label htmlFor={`${uid}-desc-input`}>Description (optional)</label>
          <input
            id={`${uid}-desc-input`}
            type="text"
            className="fc-form-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief instructions or context"
            aria-label="Form description"
          />
        </div>

        <div className="fc-form-builder">
          <div className="fc-form-builder-head">
            <span className="fc-form-builder-title">Fields</span>
            <button
              type="button"
              className="fc-form-add-btn"
              onClick={addField}
              title="Add field to form"
            >
              ＋ Add field
            </button>
          </div>

          <div className="fc-form-fields-list">
            {fields.map((f, i) => (
              <div className="fc-form-row" key={f.id || i}>
                <div className="fc-form-row-main">
                  <div className="fc-form-row-reorder">
                    <button
                      type="button"
                      disabled={i === 0}
                      className="fc-form-icon-btn"
                      onClick={() => moveField(i, -1)}
                      title="Move up"
                      aria-label="Move up"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      disabled={i === fields.length - 1}
                      className="fc-form-icon-btn"
                      onClick={() => moveField(i, 1)}
                      title="Move down"
                      aria-label="Move down"
                    >
                      ↓
                    </button>
                  </div>

                  <input
                    type="text"
                    className="fc-form-input fc-form-field-label"
                    value={f.label}
                    onChange={(e) => updateField(i, { label: e.target.value })}
                    placeholder="Field label"
                    aria-label={`Label for field ${i + 1}`}
                  />

                  <select
                    className="fc-form-input fc-form-field-type"
                    value={f.type}
                    onChange={(e) => updateField(i, { type: e.target.value as BuilderFieldType })}
                    aria-label={`Type for field ${i + 1}`}
                  >
                    <option value="text">Short text</option>
                    <option value="textarea">Long text</option>
                    <option value="radio">Single choice</option>
                    <option value="select">Dropdown</option>
                    <option value="multi">Multiple choice</option>
                    <option value="rating">Rating</option>
                    <option value="number">Number</option>
                    <option value="date">Date</option>
                    <option value="checkbox">Checkbox</option>
                  </select>

                  <label className="fc-form-field-req" title="Required field">
                    <input
                      type="checkbox"
                      checked={f.required}
                      onChange={(e) => updateField(i, { required: e.target.checked })}
                    />
                    <span>Req</span>
                  </label>

                  <button
                    type="button"
                    disabled={fields.length <= 1}
                    className="fc-form-icon-btn fc-form-del-btn"
                    onClick={() => removeField(i)}
                    title="Remove field"
                    aria-label={`Remove field ${i + 1}`}
                  >
                    ✕
                  </button>
                </div>

                {isChoiceType(f.type) && (
                  <div className="fc-form-row-options">
                    <span className="fc-form-options-label">Options:</span>
                    <input
                      type="text"
                      className="fc-form-input fc-form-field-options"
                      value={f.options}
                      onChange={(e) => updateField(i, { options: e.target.value })}
                      placeholder={f.type === 'rating' ? '1, 2, 3, 4, 5' : 'Option A, Option B, Option C'}
                      aria-label={`Options for field ${i + 1}`}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Live Preview */}
        <div className="fc-form-preview">
          <span className="fc-form-preview-label">Live Preview</span>
          <div className="fc-form-preview-content turn-body">
            <Prose src={currentMarkdown} scope={`fc-form-preview-${uid}`} />
          </div>
        </div>

        {/* Inline prompts for Save or Rename */}
        {isPromptingSave && (
          <div className="fc-form-save-box">
            <span className="fc-form-save-label">Form name:</span>
            <input
              ref={saveInputRef}
              type="text"
              className="fc-form-input fc-form-save-input"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="e.g. Session poll v2"
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleConfirmSave()
                }
              }}
            />
            <button type="button" className="fc-form-submit fc-form-sm-btn" onClick={handleConfirmSave}>
              Save
            </button>
            <button type="button" className="fc-form-cancel fc-form-sm-btn" onClick={() => setIsPromptingSave(false)}>
              Cancel
            </button>
          </div>
        )}

        {isPromptingRename && (
          <div className="fc-form-save-box">
            <span className="fc-form-save-label">Rename form:</span>
            <input
              type="text"
              className="fc-form-input fc-form-save-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleConfirmRename()
                }
              }}
            />
            <button type="button" className="fc-form-submit fc-form-sm-btn" onClick={handleConfirmRename}>
              Save
            </button>
            <button type="button" className="fc-form-cancel fc-form-sm-btn" onClick={() => setIsPromptingRename(false)}>
              Cancel
            </button>
          </div>
        )}

        <div className="fc-form-actions">
          <div className="fc-form-save-actions">
            {activeSavedId ? (
              <>
                <button
                  type="button"
                  className="fc-form-save-btn"
                  onClick={handleUpdateCurrentSaved}
                  title="Save current changes to this form"
                >
                  Save changes
                </button>
                <button
                  type="button"
                  className="fc-form-save-btn"
                  onClick={handleStartSave}
                  title="Save as a new form"
                >
                  Save as new…
                </button>
              </>
            ) : (
              <button
                type="button"
                className="fc-form-save-btn"
                onClick={handleStartSave}
                title="Save this configuration as your own form"
              >
                Save as a form…
              </button>
            )}
          </div>

          <div className="fc-form-main-actions">
            <button type="button" className="fc-form-cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="fc-form-submit">
              Insert Form
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
