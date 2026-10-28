/* Unit tests for Forms:
 * 1. Rows -> Markdown writer (each field type, options, required, escaping, parseForm roundtrip)
 * 2. Saved-forms store in localStorage (read old/empty/corrupt data safely, CRUD operations, error handling)
 * 3. Verbiage rename to "Forms"
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  FORMS_STORAGE_KEY,
  FORMS_STORAGE_VERSION,
  STARTER_FORMS,
  formatChoices,
  formatFieldLine,
  formatFormMarkdown,
  parseChoices,
  slugifyFieldId,
  slugifyName,
  loadSavedForms,
  saveSavedForms,
  addOrUpdateSavedForm,
  deleteSavedForm,
  renameSavedForm,
  type FormFieldRow,
  type SavedForm,
} from '../src/fluid/composer/formsStorage'
import { parseForm } from '../src/experimental/spec/form'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => {
  assert.deepEqual(a, b, what)
  checks++
}
const ok = (a: unknown, what: string) => {
  assert.ok(a, what)
  checks++
}

const mockCtx = () => {
  const errors: string[] = []
  const warnings: string[] = []
  return {
    ctx: {
      err: (_at: string, msg: string) => errors.push(msg),
      warn: (_at: string, msg: string) => warnings.push(msg),
    },
    errors,
    warnings,
  }
}

/* -------------------------------------------------------------------------- *
 * 1. ROWS -> MARKDOWN WRITER                                                 *
 * -------------------------------------------------------------------------- */

// Field ID slugification
{
  const used = new Set<string>()
  eq(slugifyFieldId('Your Name', 1, used), 'your_name', 'slugifies simple label')
  eq(slugifyFieldId('Your Name', 2, used), 'your_name_2', 'deduplicates duplicate label')
  eq(slugifyFieldId('123 Invalid Start', 3, used), 'field_3', 'falls back when starting with number')
  eq(slugifyFieldId('', 4, used), 'field_4', 'falls back when empty')
  eq(slugifyFieldId('Comments & Feedback', 5, used), 'comments_feedback', 'removes special chars')
}

// Choice parsing & formatting
{
  eq(parseChoices(''), [], 'empty choices string gives empty array')
  eq(parseChoices('  '), [], 'whitespace choices string gives empty array')
  eq(parseChoices('Red, Green, Blue'), ['Red', 'Green', 'Blue'], 'parses comma list')
  eq(parseChoices('Option A, "Option B, with comma", Option C'), ['Option A', 'Option B, with comma', 'Option C'], 'parses quoted choice with comma')

  eq(formatChoices('Apple, Banana, Orange'), 'Apple,Banana,Orange', 'formats simple choices bare')
  eq(formatChoices('Option A, Option B'), '"Option A","Option B"', 'quotes choices with spaces')
  eq(formatChoices(''), 'Option', 'falls back when choices are empty')
}

// Each field type & required
{
  const used = new Set<string>()

  // 1. Short text
  const fText: FormFieldRow = { id: 'full_name', label: 'Full Name', type: 'text', options: '', required: true }
  eq(formatFieldLine(fText, 0, used), 'full_name: text "Full Name" required', 'short text field required')

  // 2. Long text
  const fArea: FormFieldRow = { id: 'bio', label: 'Biography', type: 'textarea', options: '', required: false }
  eq(formatFieldLine(fArea, 1, used), 'bio: textarea "Biography"', 'long text field optional')

  // 3. Single choice (radio)
  const fRadio: FormFieldRow = { id: 'plan', label: 'Subscription Plan', type: 'radio', options: 'Free, Pro, Enterprise', required: true }
  eq(formatFieldLine(fRadio, 2, used), 'plan: radio "Subscription Plan" choices=Free,Pro,Enterprise required', 'single choice radio field')

  // 4. Dropdown (select)
  const fSelect: FormFieldRow = { id: 'country', label: 'Country', type: 'select', options: 'Canada, United States, Mexico', required: false }
  eq(formatFieldLine(fSelect, 3, used), 'country: select "Country" choices=Canada,"United States",Mexico', 'select field with quoted spaced items')

  // 5. Multiple choice (multi)
  const fMulti: FormFieldRow = { id: 'skills', label: 'Skills', type: 'multi', options: 'React, TypeScript, Rust', required: true }
  eq(formatFieldLine(fMulti, 4, used), 'skills: multi "Skills" choices=React,TypeScript,Rust required', 'multi-choice field')

  // 6. Rating (select with rating choices)
  const fRating: FormFieldRow = { id: 'satisfaction', label: 'Satisfaction', type: 'rating', options: '1, 2, 3, 4, 5', required: false }
  eq(formatFieldLine(fRating, 5, used), 'satisfaction: select "Satisfaction" choices=1,2,3,4,5', 'rating field uses select with choices')

  // 7. Number
  const fNum: FormFieldRow = { id: 'quantity', label: 'Quantity', type: 'number', options: '', required: true }
  eq(formatFieldLine(fNum, 6, used), 'quantity: number "Quantity" required', 'number field')

  // 8. Date
  const fDate: FormFieldRow = { id: 'start_date', label: 'Start Date', type: 'date', options: '', required: false }
  eq(formatFieldLine(fDate, 7, used), 'start_date: date "Start Date"', 'date field')

  // 9. Checkbox
  const fCheck: FormFieldRow = { id: 'agree', label: 'I agree to the terms', type: 'checkbox', options: '', required: true }
  eq(formatFieldLine(fCheck, 8, used), 'agree: checkbox "I agree to the terms" required', 'checkbox field')
}

// Escaping in labels, options and title
{
  const used = new Set<string>()
  const tricky: FormFieldRow = {
    id: 'tricky',
    label: 'What is your "favorite" feature\\tool?',
    type: 'radio',
    options: 'Speed & "efficiency", Fast, Other',
    required: true,
  }
  const line = formatFieldLine(tricky, 0, used)
  eq(
    line,
    'tricky: radio "What is your \\"favorite\\" feature\\\\tool?" choices="Speed & \\"efficiency\\"",Fast,Other required',
    'escapes quotes and backslashes in label and options',
  )

  const { ctx, errors } = mockCtx()
  const parsed = parseForm(line, ctx)
  eq(errors.length, 0, 'escaped line parses with zero errors')
  eq(parsed[0].label, 'What is your "favorite" feature\\tool?', 'parsed label preserves unescaped string')
  eq(parsed[0].choices, ['Speed & "efficiency"', 'Fast', 'Other'], 'parsed choices preserve quoted string')
}

// Form markdown block structure (with and without description)
{
  const fields: FormFieldRow[] = [
    { id: 'feedback', label: 'Comments', type: 'textarea', options: '', required: true },
    { id: 'score', label: 'Score', type: 'rating', options: '1, 2, 3, 4, 5', required: false },
  ]

  const withoutDesc = formatFormMarkdown({
    title: 'Customer Feedback',
    name: 'cust-fb',
    fields,
  })
  ok(withoutDesc.startsWith('```form version=1 name=cust-fb title="Customer Feedback"\n'), 'opening fence without description')
  ok(withoutDesc.endsWith('\n```'), 'closing fence')
  ok(withoutDesc.includes('feedback: textarea "Comments" required'), 'contains textarea line')
  ok(withoutDesc.includes('score: select "Score" choices=1,2,3,4,5'), 'contains score line')

  const withDesc = formatFormMarkdown({
    title: 'Customer Feedback',
    description: 'Please help us improve by answering these questions.',
    name: 'cust-fb',
    fields,
  })
  ok(
    withDesc.startsWith('Please help us improve by answering these questions.\n\n```form version=1 name=cust-fb title="Customer Feedback"'),
    'description is placed above the form block',
  )
}

// Name slugification against existing text
{
  eq(slugifyName('Customer Survey', 'survey', ''), 'customer-survey', 'slugifies title')
  eq(slugifyName('Customer Survey', 'survey', 'name=customer-survey'), 'customer-survey-2', 'deduplicates existing name in draft')
  eq(slugifyName('', 'poll', ''), 'poll', 'falls back to form type when title empty')
}

// Verify starter forms produce valid Markdown that parseForm parses with zero errors
{
  for (const starter of STARTER_FORMS) {
    const md = formatFormMarkdown({
      title: starter.title,
      name: starter.id,
      fields: starter.fields,
    })
    const body = md.slice(md.indexOf('\n') + 1, md.lastIndexOf('\n'))
    const { ctx, errors, warnings } = mockCtx()
    const parsed = parseForm(body, ctx)
    eq(errors, [], `starter ${starter.name} parses with no errors`)
    eq(warnings, [], `starter ${starter.name} parses with no warnings`)
    eq(parsed.length, starter.fields.length, `starter ${starter.name} has ${starter.fields.length} fields`)
  }
}

/* -------------------------------------------------------------------------- *
 * 2. SAVED-FORMS STORE (LOCALSTORAGE RESILIENCE)                             *
 * -------------------------------------------------------------------------- */

function makeMockStorage(initialData: Record<string, string> = {}) {
  const map = new Map<string, string>(Object.entries(initialData))
  return {
    getItem(key: string) {
      return map.get(key) ?? null
    },
    setItem(key: string, value: string) {
      map.set(key, value)
    },
    removeItem(key: string) {
      map.delete(key)
    },
    clear() {
      map.clear()
    },
    get length() {
      return map.size
    },
    key(index: number) {
      return [...map.keys()][index] ?? null
    },
  } as Storage
}

// Reading empty storage
{
  const store = makeMockStorage()
  eq(loadSavedForms(store), [], 'empty storage returns empty array')
}

// Reading null/empty string
{
  const store = makeMockStorage({ [FORMS_STORAGE_KEY]: '' })
  eq(loadSavedForms(store), [], 'empty string returns empty array')
}

// Reading corrupt JSON
{
  const store = makeMockStorage({ [FORMS_STORAGE_KEY]: '{bad json: true,,,' })
  eq(loadSavedForms(store), [], 'corrupt JSON returns empty array without throwing')
}

// Reading primitives or invalid root objects
{
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: '12345' })), [], 'number primitive returns empty array')
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: '"just a string"' })), [], 'string primitive returns empty array')
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: 'true' })), [], 'boolean primitive returns empty array')
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: '{}' })), [], 'empty object returns empty array')
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: '{"version": 1}' })), [], 'object without forms returns empty array')
  eq(loadSavedForms(makeMockStorage({ [FORMS_STORAGE_KEY]: '{"version": 1, "forms": "not an array"}' })), [], 'non-array forms returns empty array')
}

// Reading corrupted items in forms array
{
  const corruptPayload = {
    version: 1,
    forms: [
      null,
      undefined,
      42,
      {},
      { id: '', name: 'No ID' },
      { id: 'good_1', name: 'Valid Form', fields: [{ id: 'f1', label: 'Q1', type: 'text', required: true }] },
      { id: 'good_2', name: 'Missing Fields', fields: 'invalid' },
    ],
  }
  const store = makeMockStorage({ [FORMS_STORAGE_KEY]: JSON.stringify(corruptPayload) })
  const loaded = loadSavedForms(store)
  eq(loaded.length, 2, 'filters out null/invalid items and keeps valid ones')
  eq(loaded[0].id, 'good_1', 'keeps first valid form')
  eq(loaded[1].id, 'good_2', 'sanitizes second form with fallback field')
  ok(loaded[1].fields.length >= 1, 'provides fallback field for missing fields array')
}

// Backward compatibility: reading legacy unversioned array format
{
  const legacyForms = [
    {
      id: 'legacy_1',
      name: 'Legacy Poll',
      title: 'Legacy Poll',
      fields: [{ id: 'opt', label: 'Option', type: 'radio', options: 'A, B', required: true }],
    },
  ]
  const store = makeMockStorage({ [FORMS_STORAGE_KEY]: JSON.stringify(legacyForms) })
  const loaded = loadSavedForms(store)
  eq(loaded.length, 1, 'loads legacy plain array')
  eq(loaded[0].name, 'Legacy Poll', 'correct form name from legacy array')
}

// Storage operation failures (e.g. QuotaExceeded or security blocks)
{
  const throwingStorage = {
    getItem() {
      throw new Error('SecurityError: access denied')
    },
    setItem() {
      throw new Error('QuotaExceededError')
    },
    removeItem() {},
    clear() {},
    length: 0,
    key() {
      return null
    },
  } as unknown as Storage

  eq(loadSavedForms(throwingStorage), [], 'loadSavedForms catches storage errors safely')
  eq(saveSavedForms([], throwingStorage), false, 'saveSavedForms catches storage errors safely and returns false')
}

// Full CRUD cycle: Add, Update, Rename, Delete
{
  const store = makeMockStorage()
  const form1: SavedForm = {
    id: 'f_poll_v2',
    name: 'Session poll v2',
    title: 'Session Poll v2',
    description: 'Weekly sync poll',
    fields: [
      { id: 'q1', label: 'Topics', type: 'multi', options: 'Roadmap, Tech Debt, Design', required: true },
      { id: 'q2', label: 'Confidence', type: 'rating', options: '1, 2, 3, 4, 5', required: false },
    ],
  }

  // 1. Add
  const added = addOrUpdateSavedForm(form1, store)
  eq(added.length, 1, 'adds new form')
  eq(added[0].name, 'Session poll v2', 'form name matches')

  // Verify stored JSON has version 1
  const rawStored = JSON.parse(store.getItem(FORMS_STORAGE_KEY)!)
  eq(rawStored.version, FORMS_STORAGE_VERSION, 'saved JSON has version 1')
  eq(rawStored.forms.length, 1, 'saved JSON contains 1 form')

  // 2. Add second form
  const form2: SavedForm = {
    id: 'f_retro',
    name: 'Sprint Retro',
    title: 'Sprint Retro',
    fields: [{ id: 'went_well', label: 'What went well?', type: 'textarea', options: '', required: true }],
  }
  const twoForms = addOrUpdateSavedForm(form2, store)
  eq(twoForms.length, 2, 'now has 2 forms')

  // 3. Rename
  const renamed = renameSavedForm('f_poll_v2', 'Team Poll Final', store)
  eq(renamed.find((f) => f.id === 'f_poll_v2')?.name, 'Team Poll Final', 'renames form')

  // 4. Update
  const updatedForm = {
    ...form2,
    description: 'Updated retro description',
  }
  const afterUpdate = addOrUpdateSavedForm(updatedForm, store)
  eq(afterUpdate.find((f) => f.id === 'f_retro')?.description, 'Updated retro description', 'updates existing form')

  // 5. Delete
  const afterDelete = deleteSavedForm('f_poll_v2', store)
  eq(afterDelete.length, 1, 'deletes 1 form')
  eq(afterDelete[0].id, 'f_retro', 'remaining form is f_retro')

  // Reload from storage
  const reloaded = loadSavedForms(store)
  eq(reloaded.length, 1, 'reloads persisted state from storage')
  eq(reloaded[0].name, 'Sprint Retro', 'persisted form matches')
}

/* -------------------------------------------------------------------------- *
 * 3. VERBIAGE RENAME CHECK                                                   *
 * -------------------------------------------------------------------------- */

{
  const src = fileURLToPath(new URL('../src/', import.meta.url))
  const slashPaletteText = readFileSync(src + 'fluid/composer/SlashPalette.tsx', 'utf8')
  ok(!slashPaletteText.includes('Reusable Form'), 'SlashPalette does not contain "Reusable Form"')
  ok(slashPaletteText.includes("title: 'Forms'"), "SlashPalette titles the /form entry 'Forms'")

  const formDialogText = readFileSync(src + 'fluid/composer/FormDialog.tsx', 'utf8')
  ok(!formDialogText.includes('Reusable Form'), 'FormDialog does not contain "Reusable Form"')
  ok(formDialogText.includes('Forms</span>'), 'FormDialog header displays "Forms"')
}

console.log(`fluid forms: ${checks} checks passed`)
