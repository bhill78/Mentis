/* ONE VOICE AT A TIME, for every package. `useApi` keeps the last failure's
   words until a read succeeds, so a read in flight stood beside them: Try
   again said the record was being read and could not be read at once, in a
   status region and an alert region together. A read in flight is the newer
   fact and speaks alone; the failure returns, unchanged, if this read fails
   too.

   P0 owns this: it renders .qc-muted and .qc-error, which are type.css's, and
   every package that reads anything mounts it. */
export function ReadState({ loading, error, reload }: {
  loading: boolean; error: string | null; reload: () => void
}) {
  if (loading) return <p className="qc-muted" role="status">Reading…</p>
  if (error) return <p role="alert" className="qc-error">{error} <button onClick={reload}>Try again</button></p>
  return null
}
