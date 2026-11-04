/* NEW MAGNET IN A WORKSPACE OF ITS OWN (owner Turn ent-e64111a2228c §3): the one
 * editor (Editor.tsx) over a seed with no source yet, in a sheet. Nothing is made
 * until a source is chosen and Make magnet pressed, through the one create; the
 * Magnet is then drawn here and curated here, as one put in is. */

import { useEffect, useState } from 'react'
import { closeSheet, Sheet, useOpenSheet } from '../../frame/Sheet'
import * as nav from '../../nav'
import { store } from '../../store'
import { workspace } from '../../workspace/place'
import { curateMade, refusalWords } from '../../workspaces/doors'
import { conversationSeed } from './choices'
import { NEW_MAGNET_SHEET, setDraft, useNewMagnetAsked } from './client'
import { Editor } from './Editor'
import { conversationOf } from './model'
import { createChosen } from './provider'
import type { MagnetConfig, MagnetSeed } from './types'
import './magnet.css'

/** Its draft's key in the editor's drafts; never sent, the server names a Magnet. */
const DRAFT = 'mag-new' as const
const blank = (): MagnetConfig => ({ ...conversationSeed(''), id: DRAFT })

const nameOf = (seed: MagnetSeed): string => {
  const c = conversationOf({ ...seed, id: DRAFT })
  if (!c) return 'Magnet'
  return store.list?.find((x) => x.id === c)?.name ?? store.conversations.get(c)?.name ?? 'Conversation'
}

async function make(seed: MagnetSeed) {
  const key = workspace.key!
  const made = await createChosen(seed, nameOf(seed))
  /* made and drawn: failing to list it takes nothing back */
  await curateMade(key, made.id).catch((e) => nav.toast({ text: `It is here, but not listed in this workspace: ${refusalWords(e)}` }))
}

export function NewMagnet() {
  const asked = useNewMagnetAsked()
  const open = useOpenSheet()?.id === NEW_MAGNET_SHEET
  const [config] = useState(blank)
  /* each opening starts blank */
  useEffect(() => { if (asked) setDraft(DRAFT, null) }, [asked])
  if (!open) return null
  return <Sheet id={NEW_MAGNET_SHEET} label="New magnet" className="mg-new-sheet">
    <div className="mg-zone"><Editor key={asked} id={DRAFT} config={config} at="all" making={{ save: make, close: closeSheet }} /></div>
  </Sheet>
}
