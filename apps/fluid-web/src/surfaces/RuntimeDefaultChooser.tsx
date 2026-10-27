import { useState } from 'react'
import { post, useApi, type Id, type WhoRead } from '../api'
import { useMe } from '../identity'

/* ------------------------------------------------------------------------ *
 * WHICH RUNTIME RUNS THIS NAME'S WORK WHEN THE WORK NAMES NONE.
 *
 * A person's declaration about the Participant, kept beside it and never
 * read from its name: `@Quill` runs wherever Mentis decides unless somebody
 * declares Codex here or chooses it for the work. Declaring writes one
 * `runtime-default` entry and supersedes the last, so History keeps what it
 * was. It changes what NEW work is bound to; work already recorded keeps its
 * runtime, and bound work whose runtime cannot run is refused, not moved.
 *
 * "Auto" is a real answer -- Mentis's ordinary selection, said as such.
 * ------------------------------------------------------------------------ */

/** What the declaration means, in words, for anywhere a name is shown. */
export function runtimeSays(
  declared: string | null | undefined,
  mode: 'default' | 'auto' | 'undeclared' | undefined,
): string {
  if (mode === 'default' && declared) return `${declared} (declared default)`
  if (mode === 'auto') return 'auto: Mentis decides (declared)'
  return 'auto: Mentis decides (nobody declared a default)'
}

export default function RuntimeDefaultChooser({
  participant,
  who,
  onChanged,
}: {
  participant: Id
  /** the `/api/who` read, when the caller already has it */
  who?: WhoRead | null
  onChanged?: () => void
}) {
  const own = useApi<WhoRead>(who === undefined ? `/api/who/${participant}` : null)
  const d = who === undefined ? own.data : who
  const { me } = useMe()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const choose = async (runtime: string | null) => {
    setBusy(true)
    setError(null)
    try {
      await post(`/api/participants/${encodeURIComponent(participant)}/runtime-default`, {
        runtime,
        attributed_to: me,
      })
      if (who === undefined) own.reload()
      onChanged?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!d) return null
  const declared = d.default_runtime ?? null
  return (
    <p className="wp-runtime">
      <label>
        Default runtime{' '}
        <select
          value={declared ?? ''}
          disabled={busy || !me}
          onChange={(e) => void choose(e.target.value || null)}
        >
          <option value="">auto (Mentis decides)</option>
          {(d.runtimes_known ?? []).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <span className="wp-runtime-why">
        {d.runtime_mode === 'default'
          ? `New work for this name runs on ${declared} unless a runtime is chosen for it, and is refused rather than moved if ${declared} cannot run.`
          : d.runtime_mode === 'auto'
            ? 'Declared auto: Mentis picks a runtime for each piece of work and records which one ran.'
            : 'Nobody has declared one, so Mentis picks a runtime for each piece of work and records which one ran. The name is never read as a runtime.'}
      </span>
      {error && <span className="wp-error"> {error}</span>}
    </p>
  )
}
