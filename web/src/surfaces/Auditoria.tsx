import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, WyssApiError, type AuditEvent } from '../api'
import { EmptyState, ErrorNote } from '../ui'

export function Auditoria() {
  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [since, setSince] = useState('')
  const [tipo, setTipo] = useState('')
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)

  const load = useCallback(() => {
    api
      .audit(since ? `${since}T00:00:00` : undefined, 200)
      .then((r) => {
        setEvents(r.events)
        setError(null)
      })
      .catch((e) =>
        setError(
          e instanceof WyssApiError
            ? { error: e.message, accion: e.accion }
            : { error: 'error de red', accion: 'reintentá' },
        ),
      )
  }, [since])

  useEffect(load, [load])

  const tipos = useMemo(
    () => [...new Set((events ?? []).map((e) => e.event_type))].sort(),
    [events],
  )
  const visibles = (events ?? []).filter((e) => !tipo || e.event_type === tipo)

  return (
    <section className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="display text-xl font-semibold">Auditoría</h2>
        <div className="flex items-center gap-2">
          <select
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            className="rounded-sm border border-borde bg-papel px-2 py-1.5 font-mono text-xs text-hueso"
            aria-label="Filtrar por tipo de evento"
          >
            <option value="">todos los tipos</option>
            {tipos.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="rounded-sm border border-borde bg-papel px-2 py-1.5 font-mono text-xs text-hueso"
            aria-label="Desde fecha"
          />
        </div>
      </div>
      <p className="mt-1 text-sm text-humo">
        Todo lo relevante queda registrado. Esta vista lo prueba.
      </p>

      <div className="mt-6">
        {error && <ErrorNote error={error.error} accion={error.accion} />}
        {events !== null && events.length === 0 && !error && (
          <EmptyState
            mensaje="Sin auditoría todavía."
            siguiente="wyss index <ruta> o wyss start generan los primeros eventos."
          />
        )}
        {visibles.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-borde">
            <table className="w-full text-left font-mono text-xs">
              <tbody>
                {visibles.map((event, i) => (
                  <tr
                    key={i}
                    className="border-b border-borde/50 last:border-0 hover:bg-papel/60"
                  >
                    <td className="whitespace-nowrap px-3 py-2 text-humo">
                      {event.created_at.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-celeste">
                      {event.event_type}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-humo">
                      {event.actor_id}
                    </td>
                    <td className="px-3 py-2 text-hueso/90">{event.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {events !== null && events.length > 0 && visibles.length === 0 && (
          <EmptyState mensaje={`Sin eventos del tipo «${tipo}» en el rango.`} />
        )}
      </div>
    </section>
  )
}
