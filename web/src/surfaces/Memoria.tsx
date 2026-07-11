import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, type MemoryFact } from '../api'
import { formatRelative } from '../format'
import { EmptyState, ErrorNote } from '../ui'

export function Memoria() {
  const [facts, setFacts] = useState<MemoryFact[] | null>(null)
  const [error, setError] = useState<WyssApiError | null>(null)

  const load = useCallback(() => {
    api
      .memoryList()
      .then((r) => {
        setFacts(r.facts)
        setError(null)
      })
      .catch((e) => setError(e instanceof WyssApiError ? e : null))
  }, [])

  useEffect(load, [load])

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex items-baseline justify-between">
        <h2 className="display text-xl font-semibold">Memoria</h2>
        <button
          onClick={load}
          className="font-mono text-xs text-humo transition-colors hover:text-celeste"
        >
          actualizar
        </button>
      </div>
      <p className="mt-1 text-sm text-humo">
        Lo que wyss recuerda de vos. Cada plan nuevo lo recibe como dato.
      </p>

      <div className="mt-6 flex flex-col gap-3">
        {error && <ErrorNote error={error.message} accion={error.accion} />}
        {facts !== null && facts.length === 0 && !error && (
          <EmptyState
            mensaje="Memoria vacía."
            siguiente={<>Decile en el chat: «guardá en tu memoria que…»</>}
          />
        )}
        {facts?.map((f) => (
          <FactRow key={f.id} fact={f} onChanged={load} />
        ))}
      </div>
    </section>
  )
}

function FactRow({ fact, onChanged }: { fact: MemoryFact; onChanged: () => void }) {
  const [editando, setEditando] = useState(false)
  const [valor, setValor] = useState(fact.value)
  const [confirmandoBorrar, setConfirmandoBorrar] = useState(false)
  const [enVuelo, setEnVuelo] = useState(false)
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)

  const run = async (fn: () => Promise<unknown>) => {
    setEnVuelo(true)
    setError(null)
    try {
      await fn()
      setEditando(false)
      setConfirmandoBorrar(false)
      onChanged()
    } catch (e) {
      if (e instanceof WyssApiError) setError({ error: e.message, accion: e.accion })
      else setError({ error: 'error de red', accion: 'reintentá' })
    } finally {
      setEnVuelo(false)
    }
  }

  return (
    <article className="rounded-md border border-borde bg-papel p-4">
      {editando ? (
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            autoFocus
            className="min-w-0 flex-1 rounded-sm border border-borde bg-tinta px-3 py-1.5 font-mono text-sm text-hueso"
          />
          <button
            onClick={() => void run(() => api.editMemory(fact.id, valor))}
            disabled={enVuelo || valor.trim() === ''}
            className="rounded-sm bg-celeste px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Guardar
          </button>
          <button
            onClick={() => {
              setEditando(false)
              setValor(fact.value)
            }}
            className="text-sm text-humo transition-colors hover:text-hueso"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <p className="text-sm text-hueso">{fact.value}</p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono text-xs text-humo">{fact.category}</span>
        <span className="inline-flex items-center rounded-sm border border-celeste/60 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-celeste">
          {fact.tier}
        </span>
        <span className="font-mono text-xs text-humo">
          {formatRelative(fact.updated_at)}
        </span>

        <span className="ml-auto flex items-center gap-3">
          {confirmandoBorrar ? (
            <>
              <span className="text-sm text-humo">¿Borrar este recuerdo?</span>
              <button
                onClick={() => void run(() => api.forgetMemory(fact.id))}
                disabled={enVuelo}
                className="rounded-sm bg-riesgo-d px-3 py-1 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Borrar
              </button>
              <button
                onClick={() => setConfirmandoBorrar(false)}
                className="text-sm text-humo transition-colors hover:text-hueso"
              >
                Cancelar
              </button>
            </>
          ) : (
            !editando && (
              <>
                <button
                  onClick={() => setEditando(true)}
                  className="font-mono text-xs text-humo transition-colors hover:text-celeste"
                >
                  editar
                </button>
                <button
                  onClick={() => setConfirmandoBorrar(true)}
                  className="font-mono text-xs text-humo transition-colors hover:text-riesgo-d"
                >
                  borrar
                </button>
              </>
            )
          )}
        </span>
      </div>

      {error && (
        <div className="mt-3">
          <ErrorNote error={error.error} accion={error.accion} />
        </div>
      )}
    </article>
  )
}
