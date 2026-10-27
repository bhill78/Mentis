/* EXPERIMENTAL: the reading half of compare and review (drawn in ../types/decide.tsx). */
import type { TypeSpec } from './api'
import { listOf } from '../util'

export interface Section { name: string; text: string; line: number }

export const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/

/** Split a body at heading lines, ignoring anything inside fences (a nested
    block's body is never mistaken for a heading). Text before the first
    heading comes back as `intro`. */
export function splitSections(body: string, heading: (line: string) => string | null) {
  const heads: { name: string; line: number }[] = []
  const bufs: string[][] = [[]]
  let fence: { ch: string; n: number } | null = null
  body.split('\n').forEach((line, n) => {
    const m = FENCE.exec(line)
    if (fence) {
      if (m && m[1][0] === fence.ch && m[1].length >= fence.n && !m[2].trim()) fence = null
    } else if (m) {
      fence = { ch: m[1][0], n: m[1].length }
    } else {
      const h = heading(line)
      if (h !== null) {
        heads.push({ name: h, line: n + 1 })
        bufs.push([])
        return
      }
    }
    bufs[bufs.length - 1].push(line)
  })
  const secs: Section[] = heads.map((h, i) => ({ ...h, text: bufs[i + 1].join('\n').replace(/^\s*\n|\s+$/g, '') }))
  return { intro: bufs[0].join('\n').trim(), secs, unclosed: fence !== null }
}

export interface CmpData { intro: string; options: Section[]; criteria: string[] }

export interface RevData { intro: string; material: string; checks: { text: string; checked: boolean }[]; decisions: string[]; needReason: string[] }

export const DEFAULT_DECISIONS = 'approve,request-changes,reject'

export const compareSpec: TypeSpec<CmpData> = {
  type: 'compare',
  summary: 'Two or more options side by side. The person marks, notes and picks; the renderer ranks and recommends nothing.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    choose: { req: 'optional', choices: ['none', 'one', 'many'], says: 'whether the person picks: none (default), one or many' },
    criteria: { req: 'optional', says: 'comma list of things to weigh; the person marks each option + − or ? against each' },
  },
  nests: true,
  body: 'optional intro, then one `## Option name` line per option, each followed by ordinary Markdown (marked blocks allowed)',
  parse(body, a, c) {
    const { intro, secs, unclosed } = splitSections(body, (l) => /^## +(.*?)(?:\s+#+)?\s*$/.exec(l)?.[1] ?? null)
    if (unclosed) c.err('body', 'A fence inside the compare is never closed, so everything after it is swallowed into that block.')
    if (secs.length < 2)
      c.err('body', `A compare needs at least two options, each starting with a “## Name” line. I found ${secs.length}.`)
    const names = secs.map((s) => s.name)
    secs.forEach((s) => {
      if (!s.name) c.err(`line ${s.line}`, 'This “##” line has no option name after it.')
      else if (names.indexOf(s.name) !== names.lastIndexOf(s.name)) c.err(`line ${s.line}`, `The option name “${s.name}” is used twice; names must differ.`)
      if (!s.text) c.warn(`line ${s.line}`, `Option “${s.name}” has nothing under it.`)
    })
    const criteria = listOf(a.criteria).filter(Boolean)
    const dup = criteria.filter((x, i) => criteria.indexOf(x) !== i)
    if (dup.length) c.err('criteria', `Criteria repeat: ${[...new Set(dup)].join(', ')}.`)
    if (a.criteria !== undefined && !criteria.length) c.err('criteria', 'criteria is empty. Give a comma list, e.g. criteria="cost,risk,effort", or leave it out.')
    return { intro, options: secs, criteria }
  },
}

export const reviewSpec: TypeSpec<RevData> = {
  type: 'review',
  summary: 'Material to review, checks to tick, comments and a decision. All of it is state for Send back; nothing is decided in Mentis.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    decisions: { req: 'optional', says: `comma list of the decisions offered (default ${DEFAULT_DECISIONS})` },
    reason_required: { req: 'optional', says: 'comma list of the decisions that need a written reason' },
  },
  nests: true,
  body: 'a `## Material` line then ordinary Markdown (marked blocks allowed), then a `## Checks` line then `- [ ] check` lines',
  parse(body, a, c) {
    const { intro, secs, unclosed } = splitSections(body, (l) => {
      const m = /^## +(material|checks)(?:\s+#+)?\s*:?\s*$/i.exec(l)
      return m ? m[1].toLowerCase() : null
    })
    if (unclosed) c.err('body', 'A fence inside the review is never closed, so everything after it is swallowed into that block.')
    const mat = secs.filter((s) => s.name === 'material'), chk = secs.filter((s) => s.name === 'checks')
    if (!mat.length) c.err('body', 'A review needs a “## Material” line with the thing being reviewed under it.')
    if (mat.length > 1) c.err(`line ${mat[1].line}`, '“## Material” appears twice; put all the material under one.')
    if (chk.length > 1) c.err(`line ${chk[1].line}`, '“## Checks” appears twice; put all the checks under one.')
    if (mat[0] && !mat[0].text) c.err(`line ${mat[0].line}`, 'The “## Material” section is empty.')
    if (intro) c.warn('body', 'There is text before “## Material”. It is shown above the material as an introduction.')
    const checks: RevData['checks'] = []
    if (!chk.length) c.warn('body', 'There is no “## Checks” section, so this review is only a decision.')
    else
      chk[0].text.split('\n').forEach((line, n) => {
        if (!line.trim()) return
        const m = /^\s*[-*] \[( |x|X)\] (.*\S)\s*$/.exec(line)
        if (!m) c.err(`line ${chk[0].line + n + 1}`, `“${line}” is not a check. Checks look like “- [ ] text”.`)
        else checks.push({ text: m[2], checked: m[1] !== ' ' })
      })
    const decisions = listOf(a.decisions ?? DEFAULT_DECISIONS).filter(Boolean)
    if (!decisions.length) c.err('decisions', 'decisions is empty. Give a comma list, or leave it out for approve,request-changes,reject.')
    const dd = decisions.filter((x, i) => decisions.indexOf(x) !== i)
    if (dd.length) c.err('decisions', `Decisions repeat: ${[...new Set(dd)].join(', ')}.`)
    const needReason = listOf(a.reason_required).filter(Boolean)
    for (const r of needReason)
      if (!decisions.includes(r)) c.err('reason_required', `reason_required names “${r}”, but the decisions are: ${decisions.join(', ')}.`)
    return { intro, material: mat[0]?.text ?? '', checks, decisions, needReason }
  },
}
