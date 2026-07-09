import { useState } from 'react'
import { api, WyssApiError, type KbFreshness, type SearchResult } from '../api'
import { EmptyState, ErrorNote } from '../ui'

export function Buscar({ kbs }: { kbs: KbFreshness[] }) {
  const [q, setQ] = useState('')
  const [kb, setKb] = useState<string | null>(null)
  const [result, setResult] = useState<SearchResult | null>(null)
  const [buscando, setBuscando] = useState(false)
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)
  const [ultimaQ, setUltimaQ] = useState('')

  const buscar = async () => {
    const query = q.trim()
    if (!query || buscando) return
    setBuscando(true)
    setError(null)
    try {
      setResult(await api.search(query, kb ?? undefined, 20))
      setUltimaQ(query)
    } catch (e) {
      setResult(null)
      setError(
        e instanceof WyssApiError
          ? { error: e.message, accion: e.accion }
          : { error: 'error de red', accion: 'reintentá' },
      )
    } finally {
      setBuscando(false)
    }
  }

  return (
    <section className="mx-auto max-w-3xl">
      <h2 className="display text-xl font-semibold">Buscar</h2>
      <p className="mt-1 text-sm text-humo">
        Retrieval híbrido (texto + vectores) sobre tus bases de conocimiento.
      </p>

      <form
        className="mt-5 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void buscar()
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="¿Qué estás buscando?"
          className="flex-1 rounded-sm border border-borde bg-papel px-4 py-2.5 text-sm placeholder:text-humo/60"
        />
        <button
          type="submit"
          disabled={buscando || q.trim() === ''}
          className="rounded-sm bg-celeste px-5 py-2.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {buscando ? '…' : 'Buscar'}
        </button>
      </form>

      {kbs.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {kbs.map((item) => {
            const active = kb === item.kb_id
            return (
              <button
                key={item.kb_id}
                onClick={() => setKb(active ? null : item.kb_id)}
                className={`rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
                  active
                    ? 'border-celeste bg-celeste/15 text-celeste'
                    : 'border-borde text-humo hover:border-humo'
                }`}
              >
                {item.kb_id} · {item.files}
              </button>
            )
          })}
        </div>
      )}

      <div className="mt-6 flex flex-col gap-3">
        {error && <ErrorNote error={error.error} accion={error.accion} />}

        {result?.degraded && (
          <p className="rounded-sm border border-riesgo-b/50 bg-riesgo-b/10 px-3 py-2 font-mono text-xs text-riesgo-b">
            búsqueda solo texto (FTS5) — {result.reason ?? 'vectores no disponibles'}
          </p>
        )}

        {result !== null && result.hits.length === 0 && !error && (
          <EmptyState
            mensaje={`Sin resultados para «${ultimaQ}».`}
            siguiente="Probá con otros términos, o indexá más contenido: wyss index <ruta> --bc <nombre>"
          />
        )}

        {result?.hits.map((hit) => (
          <article
            key={hit.entry_id}
            className="rounded-md border border-borde bg-papel px-4 py-3"
          >
            <header className="flex items-baseline gap-3">
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-celeste">
                {hit.source_path}
              </span>
              <span className="font-mono text-[10px] text-humo">
                {hit.score.toFixed(3)}
              </span>
            </header>
            <p className="mt-2 text-sm leading-relaxed text-hueso/90">{hit.snippet}</p>
            {hit.date && (
              <p className="mt-1.5 font-mono text-[10px] text-humo">{hit.date}</p>
            )}
          </article>
        ))}

        {result !== null && result.freshness.length > 0 && (
          <p className="mt-2 font-mono text-[10px] text-humo">
            índice:{' '}
            {result.freshness
              .map((f) => `${f.kb_id} ${f.files} archivos`)
              .join(' · ')}
          </p>
        )}
      </div>
    </section>
  )
}
