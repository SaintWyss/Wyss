import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, type DigestToday } from '../api'
import { EmptyState, ErrorNote } from '../ui'

export function Digest() {
  const [data, setData] = useState<DigestToday | null>(null)
  const [error, setError] = useState<WyssApiError | null>(null)
  const [cargando, setCargando] = useState(false)

  const load = useCallback(() => {
    setCargando(true)
    api
      .digestToday()
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e instanceof WyssApiError ? e : null))
      .finally(() => setCargando(false))
  }, [])

  useEffect(load, [load])

  const fecha = data ? data.generated_at.slice(0, 10) : null

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="display text-xl font-semibold">Digest</h2>
        <button
          onClick={load}
          disabled={cargando}
          className="rounded-sm bg-celeste px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {cargando ? 'Generando…' : 'Generar ahora'}
        </button>
      </div>
      <p className="mt-1 text-sm text-humo">
        {fecha ? `Digest — ${fecha}` : 'El parte del día: bandeja, finanzas y rutinas.'}
      </p>

      <div className="mt-6">
        {error && <ErrorNote error={error.message} accion={error.accion} />}
        {!error && data === null && !cargando && (
          <EmptyState
            mensaje="Sin digest todavía."
            siguiente="Generalo con el botón o esperá la hora configurada."
          />
        )}
        {data && (
          <article className="rounded-md border border-borde bg-papel p-5">
            <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-hueso">
              {data.markdown}
            </pre>
          </article>
        )}
      </div>
    </section>
  )
}
