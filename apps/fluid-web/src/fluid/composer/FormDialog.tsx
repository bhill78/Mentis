import { useEffect, useRef, useState } from 'react'
import type { Id, Post } from '../store'
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

function defaultTitle(type: FormType): string {
  switch (type) {
    case 'feedback': return 'Feedback'
    case 'poll': return 'Quick Poll'
    case 'survey': return 'Survey'
    case 'custom': return 'Custom Form'
  }
}

function slugifyName(title: string, type: FormType, existingText: string): string {
  let base = (title.trim() || type)
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 30)
  if (!base || !/^[a-z]/.test(base)) {
    base = type.toLowerCase()
  }
  let candidate = base
  let counter = 1
  while (
    existingText.includes(`name=${candidate}`) ||
    existingText.includes(`name="${candidate}"`)
  ) {
    counter++
    candidate = `${base}-${counter}`
  }
  return candidate
}

export function formatFormMarkdown({
  type,
  name,
  title,
}: {
  type: FormType
  name: string
  title: string
}): string {
  const cleanTitle = title.trim().replace(/"/g, '') || defaultTitle(type)
  const header = `form version=1 name=${name} title="${cleanTitle}"`

  let body = ''
  if (type === 'feedback') {
    body = 'comments: textarea "Your comments" required\nrating: select "Rating" choices="Excellent,Good,Satisfactory,Needs Improvement" default="Good"'
  } else if (type === 'poll') {
    body = 'vote: radio "Option" choices="Option A,Option B,Option C" required\nreason: text "Reason (optional)"'
  } else if (type === 'survey') {
    body = 'name: text "Name" required\nrole: text "Role"\ntopics: multi "Topics of interest" choices="Design,Engineering,Product,Governance"\nnotify: checkbox "Notify me of updates" default=true'
  } else {
    body = 'title: text "Title" required\ndescription: textarea "Description"'
  }

  return `\`\`\`${header}\n${body}\n\`\`\``
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
  const [type, setType] = useState<FormType>('feedback')
  const [title, setTitle] = useState(defaultTitle('feedback'))
  const [titleEdited, setTitleEdited] = useState(false)
  const titleInputRef = useRef<HTMLInputElement>(null)

  // Context determination
  const postRef = parent?.number != null ? `Post #${parent.number}` : (replyTo ? `Post #${replyTo.slice(4, 10)}` : null)
  const convRef = parent?.home_name ?? convName ?? 'this conversation'
  const contextDisplay = replyTo
    ? `Replying to ${postRef} in ${convRef}`
    : `Conversation: ${convRef}`

  const switchType = (t: FormType) => {
    setType(t)
    if (!titleEdited) {
      setTitle(defaultTitle(t))
    }
  }

  const handleInsert = () => {
    const name = slugifyName(title, type, existingText)
    const block = formatFormMarkdown({
      type,
      name,
      title,
    })
    onInsert(block)
  }

  useEffect(() => {
    bind((e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return true
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
        handleInsert()
        return true
      }
      return false
    })
  }, [bind, type, title, existingText, titleEdited])

  useEffect(() => {
    titleInputRef.current?.focus()
  }, [])

  return (
    <div className="fc-form-dialog" role="dialog" aria-label="Form settings" data-type={type}>
      <div className="fc-form-head">
        <div className="fc-form-title-row">
          <span className="fc-form-icon" aria-hidden="true">📋</span>
          <span className="fc-form-heading">/form</span>
        </div>
        <div className="fc-form-types" role="tablist" aria-label="Form type">
          <button
            type="button"
            role="tab"
            aria-selected={type === 'feedback'}
            className={'fc-form-type-btn' + (type === 'feedback' ? ' on' : '')}
            data-type="feedback"
            onClick={() => switchType('feedback')}
          >
            Feedback
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={type === 'poll'}
            className={'fc-form-type-btn' + (type === 'poll' ? ' on' : '')}
            data-type="poll"
            onClick={() => switchType('poll')}
          >
            Poll
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={type === 'survey'}
            className={'fc-form-type-btn' + (type === 'survey' ? ' on' : '')}
            data-type="survey"
            onClick={() => switchType('survey')}
          >
            Survey
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={type === 'custom'}
            className={'fc-form-type-btn' + (type === 'custom' ? ' on' : '')}
            data-type="custom"
            onClick={() => switchType('custom')}
          >
            Custom
          </button>
        </div>
      </div>

      <div className="fc-form-context">
        <span className="fc-form-context-badge">Context</span>
        <span className="fc-form-context-text" title={contextDisplay}>
          {contextDisplay}
        </span>
      </div>

      <form className="fc-form-body" onSubmit={(e) => { e.preventDefault(); handleInsert(); }}>
        <div className="fc-form-field">
          <label htmlFor="form-title-input">Title</label>
          <input
            id="form-title-input"
            ref={titleInputRef}
            type="text"
            className="fc-form-input"
            value={title}
            onChange={(e) => { setTitle(e.target.value); setTitleEdited(true); }}
            placeholder={defaultTitle(type)}
            aria-label="Form title"
          />
        </div>

        <div className="fc-form-preview">
          <span className="fc-form-preview-label">Fields included</span>
          <div className="fc-form-preview-list">
            {type === 'feedback' && (
              <>
                <span>• Textarea: comments (required)</span>
                <span>• Select: rating (Excellent, Good, Satisfactory, Needs Improvement)</span>
              </>
            )}
            {type === 'poll' && (
              <>
                <span>• Radio choices: vote (required)</span>
                <span>• Text: reason (optional)</span>
              </>
            )}
            {type === 'survey' && (
              <>
                <span>• Text: name (required) & role</span>
                <span>• Multi-choice: topics</span>
                <span>• Checkbox: notify</span>
              </>
            )}
            {type === 'custom' && (
              <>
                <span>• Text: title (required)</span>
                <span>• Textarea: description</span>
              </>
            )}
          </div>
        </div>

        <div className="fc-form-actions">
          <button type="button" className="fc-form-cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="fc-form-submit">
            Insert Form
          </button>
        </div>
      </form>
    </div>
  )
}
