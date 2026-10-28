/* Storage and Markdown formatting for Forms in Fluid.
 * Persists user-saved forms in localStorage under 'mentis.fluid.forms' (versioned, try/catch).
 */

export const FORMS_STORAGE_KEY = 'mentis.fluid.forms'
export const FORMS_STORAGE_VERSION = 1

export type BuilderFieldType =
  | 'text'
  | 'textarea'
  | 'radio'
  | 'select'
  | 'multi'
  | 'rating'
  | 'number'
  | 'date'
  | 'checkbox'

export interface FormFieldRow {
  id: string
  label: string
  type: BuilderFieldType
  options: string
  required: boolean
}

export interface SavedForm {
  id: string
  name: string
  title: string
  description?: string
  fields: FormFieldRow[]
  isStarter?: boolean
  createdAt?: number
  updatedAt?: number
}

export interface SavedFormsPayload {
  version: number
  forms: SavedForm[]
}

export const STARTER_FORMS: SavedForm[] = [
  {
    id: 'feedback',
    name: 'Feedback',
    title: 'Feedback',
    description: '',
    isStarter: true,
    fields: [
      { id: 'comments', label: 'Your comments', type: 'textarea', options: '', required: true },
      { id: 'rating', label: 'Rating', type: 'rating', options: 'Excellent, Good, Satisfactory, Needs Improvement', required: false },
    ],
  },
  {
    id: 'poll',
    name: 'Poll',
    title: 'Quick Poll',
    description: '',
    isStarter: true,
    fields: [
      { id: 'vote', label: 'Option', type: 'radio', options: 'Option A, Option B, Option C', required: true },
      { id: 'reason', label: 'Reason (optional)', type: 'text', options: '', required: false },
    ],
  },
  {
    id: 'survey',
    name: 'Survey',
    title: 'Survey',
    description: '',
    isStarter: true,
    fields: [
      { id: 'name', label: 'Name', type: 'text', options: '', required: true },
      { id: 'role', label: 'Role', type: 'text', options: '', required: false },
      { id: 'topics', label: 'Topics of interest', type: 'multi', options: 'Design, Engineering, Product, Governance', required: false },
      { id: 'notify', label: 'Notify me of updates', type: 'checkbox', options: '', required: false },
    ],
  },
  {
    id: 'custom',
    name: 'Custom',
    title: 'Custom Form',
    description: '',
    isStarter: true,
    fields: [
      { id: 'title', label: 'Title', type: 'text', options: '', required: true },
      { id: 'description', label: 'Description', type: 'textarea', options: '', required: false },
    ],
  },
]

function unwrapQuotes(s: string): string {
  const t = s.trim()
  if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) {
    return t.slice(1, -1)
  }
  return t
}

/** Parse a comma-separated options string into an array of trimmed choices. */
export function parseChoices(raw: string): string[] {
  if (!raw.trim()) return []
  const items: string[] = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i]
    if (c === '"') {
      inQuotes = !inQuotes
      current += c
    } else if (c === ',' && !inQuotes) {
      const trimmed = unwrapQuotes(current)
      if (trimmed) items.push(trimmed)
      current = ''
    } else {
      current += c
    }
  }
  const last = unwrapQuotes(current)
  if (last) items.push(last)
  return items
}

/** Serialize choices into the format expected by form block syntax:
 *  bare if alphanumeric without spaces or symbols, quoted otherwise.
 */
export function formatChoices(raw: string): string {
  const items = parseChoices(raw)
  if (!items.length) {
    return 'Option'
  }
  return items
    .map((s) => (/^[^\s",=]+$/.test(s) ? s : JSON.stringify(s)))
    .join(',')
}

/** Slugify a field identifier from an existing id or label, guaranteeing uniqueness. */
export function slugifyFieldId(labelOrId: string, fallbackIndex: number, usedIds: Set<string>): string {
  let base = labelOrId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
  if (!base || !/^[a-z]/.test(base)) {
    base = `field_${fallbackIndex}`
  }
  let candidate = base
  let counter = 1
  while (usedIds.has(candidate)) {
    counter++
    candidate = `${base}_${counter}`
  }
  usedIds.add(candidate)
  return candidate
}

/** Format a single field line for the form body. */
export function formatFieldLine(f: FormFieldRow, index: number, usedIds: Set<string>): string {
  const id = slugifyFieldId(f.id || f.label, index + 1, usedIds)
  const escapedLabel = f.label.trim().replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, ' ') || `Field ${index + 1}`
  const req = f.required ? ' required' : ''

  switch (f.type) {
    case 'text':
      return `${id}: text "${escapedLabel}"${req}`
    case 'textarea':
      return `${id}: textarea "${escapedLabel}"${req}`
    case 'radio': {
      const opts = formatChoices(f.options || 'Option A, Option B')
      return `${id}: radio "${escapedLabel}" choices=${opts}${req}`
    }
    case 'select': {
      const opts = formatChoices(f.options || 'Choice 1, Choice 2')
      return `${id}: select "${escapedLabel}" choices=${opts}${req}`
    }
    case 'multi': {
      const opts = formatChoices(f.options || 'Option 1, Option 2')
      return `${id}: multi "${escapedLabel}" choices=${opts}${req}`
    }
    case 'rating': {
      // rating is rendered via select with rating choices
      const opts = formatChoices(f.options || '1, 2, 3, 4, 5')
      return `${id}: select "${escapedLabel}" choices=${opts}${req}`
    }
    case 'number':
      return `${id}: number "${escapedLabel}"${req}`
    case 'date':
      return `${id}: date "${escapedLabel}"${req}`
    case 'checkbox':
      return `${id}: checkbox "${escapedLabel}"${req}`
    default:
      return `${id}: text "${escapedLabel}"${req}`
  }
}

/** Slugify form name against existing composer text to avoid collisions. */
export function slugifyName(title: string, formName: string, existingText: string): string {
  let base = (title.trim() || formName)
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 30)
  if (!base || !/^[a-z]/.test(base)) {
    base = 'form'
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

/** Format rows into a full Markdown form block with optional description. */
export function formatFormMarkdown({
  title,
  description,
  name,
  fields,
  type,
}: {
  title: string
  description?: string
  name: string
  fields?: FormFieldRow[]
  type?: string
}): string {
  const cleanTitle = title.trim().replace(/"/g, '\\"') || 'Form'
  const header = `form version=1 name=${name} title="${cleanTitle}"`

  let resolvedFields = fields
  if (!resolvedFields || !resolvedFields.length) {
    const starter = STARTER_FORMS.find((s) => s.id === type) ?? STARTER_FORMS[0]
    resolvedFields = starter.fields
  }

  const usedIds = new Set<string>()
  const fieldLines = resolvedFields.map((f, i) => formatFieldLine(f, i, usedIds)).join('\n')
  const block = `\`\`\`${header}\n${fieldLines}\n\`\`\``
  const desc = description?.trim()
  if (desc) {
    return `${desc}\n\n${block}`
  }
  return block
}

function sanitizeFormRow(row: unknown, index: number): FormFieldRow | null {
  if (!row || typeof row !== 'object') return null
  const r = row as Partial<FormFieldRow>
  const type: BuilderFieldType =
    r.type && ['text', 'textarea', 'radio', 'select', 'multi', 'rating', 'number', 'date', 'checkbox'].includes(r.type)
      ? r.type
      : 'text'
  return {
    id: typeof r.id === 'string' && r.id.trim() ? r.id.trim() : `field_${index + 1}`,
    label: typeof r.label === 'string' ? r.label : `Field ${index + 1}`,
    type,
    options: typeof r.options === 'string' ? r.options : '',
    required: Boolean(r.required),
  }
}

function sanitizeSavedForm(item: unknown): SavedForm | null {
  if (!item || typeof item !== 'object') return null
  const f = item as Partial<SavedForm>
  if (typeof f.id !== 'string' || !f.id.trim()) return null
  if (typeof f.name !== 'string' || !f.name.trim()) return null
  const title = typeof f.title === 'string' && f.title.trim() ? f.title.trim() : f.name.trim()
  const description = typeof f.description === 'string' ? f.description : ''
  const rawFields = Array.isArray(f.fields) ? f.fields : []
  const fields: FormFieldRow[] = []
  rawFields.forEach((rf, i) => {
    const clean = sanitizeFormRow(rf, i)
    if (clean) fields.push(clean)
  })
  if (!fields.length) {
    fields.push({ id: 'field_1', label: 'Field 1', type: 'text', options: '', required: false })
  }
  return {
    id: f.id.trim(),
    name: f.name.trim(),
    title,
    description,
    fields,
    isStarter: Boolean(f.isStarter),
    createdAt: typeof f.createdAt === 'number' ? f.createdAt : undefined,
    updatedAt: typeof f.updatedAt === 'number' ? f.updatedAt : undefined,
  }
}

/** Load user-saved forms from localStorage safely. */
export function loadSavedForms(storage?: Storage): SavedForm[] {
  try {
    const s = storage ?? (typeof window !== 'undefined' ? window.localStorage : undefined)
    if (!s) return []
    const raw = s.getItem(FORMS_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return []

    // Format { version: 1, forms: [...] }
    if (Array.isArray(parsed.forms)) {
      return parsed.forms.map(sanitizeSavedForm).filter((x: SavedForm | null): x is SavedForm => x !== null)
    }
    // Backward compatibility for legacy plain array format
    if (Array.isArray(parsed)) {
      return parsed.map(sanitizeSavedForm).filter((x: SavedForm | null): x is SavedForm => x !== null)
    }
    return []
  } catch {
    return []
  }
}

/** Save forms array to localStorage under key 'mentis.fluid.forms'. */
export function saveSavedForms(forms: SavedForm[], storage?: Storage): boolean {
  try {
    const s = storage ?? (typeof window !== 'undefined' ? window.localStorage : undefined)
    if (!s) return false
    const payload: SavedFormsPayload = {
      version: FORMS_STORAGE_VERSION,
      forms: forms.filter((f) => !f.isStarter),
    }
    s.setItem(FORMS_STORAGE_KEY, JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

/** Add or update a form in localStorage. */
export function addOrUpdateSavedForm(form: SavedForm, storage?: Storage): SavedForm[] {
  const current = loadSavedForms(storage)
  const now = Date.now()
  const clean = sanitizeSavedForm({
    ...form,
    isStarter: false,
    updatedAt: now,
    createdAt: form.createdAt ?? now,
  })
  if (!clean) return current

  const idx = current.findIndex((f) => f.id === clean.id)
  let updated: SavedForm[]
  if (idx >= 0) {
    updated = [...current]
    updated[idx] = clean
  } else {
    updated = [...current, clean]
  }
  saveSavedForms(updated, storage)
  return updated
}

/** Delete a saved form from localStorage. */
export function deleteSavedForm(id: string, storage?: Storage): SavedForm[] {
  const current = loadSavedForms(storage)
  const updated = current.filter((f) => f.id !== id)
  saveSavedForms(updated, storage)
  return updated
}

/** Rename a saved form in localStorage. */
export function renameSavedForm(id: string, newName: string, storage?: Storage): SavedForm[] {
  const current = loadSavedForms(storage)
  const name = newName.trim()
  if (!name) return current
  const updated = current.map((f) => (f.id === id ? { ...f, name, updatedAt: Date.now() } : f))
  saveSavedForms(updated, storage)
  return updated
}
