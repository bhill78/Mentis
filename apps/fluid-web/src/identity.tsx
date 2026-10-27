import { createContext, useContext, useMemo } from 'react'
import { useApi, type Id, type ParticipantsList } from './api'

/** "me" is the owner, resolved once from the record: the Participant whose
 *  `about` is "the owner". It is not a choice this interface offers, and
 *  nothing is persisted — authoring is always the owner. */

export interface Person {
  participant: Id
  alias: string
  about: string
  conversations: Id[]
  /** the held image chosen to picture this name, or null for the default */
  avatar?: Id | null
  /** where this name last ran, observed; null if it never has */
  runtime?: string | null
}

interface MeValue {
  me: Id | null
  people: Person[]
  person: (id: Id | null | undefined) => Person | undefined
}

const Ctx = createContext<MeValue>({ me: null, people: [], person: () => undefined })

export const useMe = () => useContext(Ctx)

export function MeProvider({ children }: { children: React.ReactNode }) {
  const list = useApi<ParticipantsList>('/api/participants')
  const value = useMemo<MeValue>(() => {
    const people = list.data?.participants ?? []
    const owner = people.find((p) => p.about === 'the owner') ?? people[0]
    return {
      me: owner?.participant ?? null,
      people,
      person: (id) => people.find((p) => p.participant === id),
    }
  }, [list.data])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
