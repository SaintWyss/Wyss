import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, type Routine } from '../api'
import { formatRelative, formatSchedule, outcomeColor, statusLabel } from '../format'
import { EmptyState, ErrorNote } from '../ui'

export function Rutinas() {
  const [routines, setRoutines] = useState<Routine[] | null>(null)
  const [error, setError] = useState<WyssApiError | null>(null)

  const load = useCallback(() => {
    api
      .routines()
      .then((r) => {
        setRoutines(r.routines)
        setError(null)
      })
      .catch((e) => setError(e instanceof WyssApiError ? e : null))
  }, [])

  useEffect(load, [load])

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex items-baseline justify-between">
        <h2 className="display text-xl font-semibold">Rutinas</h2>
        <button
          onClick={load}
          className="font-mono text-xs text-humo transition-colors hover:text-celeste"
        >
          actualizar
        </button>
      </div>
      <p className="mt-1 text-sm text-humo">
        Tareas programadas que disparan propuestas a la bandeja.
      </p>

      <div className="mt-6 flex flex-col gap-4">
        {error && <ErrorNote error={error.message} accion={error.accion} />}
        {routines !== null && routines.length === 0 && !error && (
          <EmptyState
            mensaje="Sin rutinas programadas."
            siguiente={
              <span className="font-mono">Creá una con: wyss routine add …</span>
            }
          />
        )}
        {routines?.map((r) => (
          <RutinaCard key={r.id} routine={r} onChanged={load} />
        ))}
      </div>
    </section>
  )
}

function RutinaCard({ routine, onChanged }: { routine: Routine; onChanged: () => void }) {
  const [enVuelo, setEnVuelo] = useState(false)
  const [confirmandoBorrar, setConfirmandoBorrar] = useState(false)
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)
  const estado = statusLabel(routine.status)

  const run = async (fn: () => Promise<unknown>) => {
    setEnVuelo(true)
    setError(null)
    try {
      await fn()
      onChanged()
    } catch (e) {
      if (e instanceof WyssApiError) setError({ error: e.message, accion: e.accion })
      else setError({ error: 'error de red', accion: 'reintentá' })
    } finally {
      setEnVuelo(false)
      setConfirmandoBorrar(false)
    }
  }

  return (
    <article className="rounded-md border border-borde bg-papel p-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h3 className="display font-medium">{routine.name}</h3>
        <span
          className={`inline-flex items-center rounded-sm border border-current/60 px-2 py-0.5 font-mono text-xs uppercase tracking-wide ${estado.className}`}
        >
          {estado.label}
        </span>
        <span className="ml-auto font-mono text-xs text-humo">
          {formatSchedule(routine.schedule)}
        </span>
      </header>

      <p className="mt-3 text-sm text-humo">
        última corrida:{' '}
        <span className="font-mono text-hueso">
          {formatRelative(routine.last_fired_at)}
        </span>
        {routine.last_outcome && (
          <>
            {' · '}
            <span className={`font-mono ${outcomeColor(routine.last_outcome)}`}>
              {routine.last_outcome}
            </span>
          </>
        )}
      </p>

      {error && (
        <div className="mt-3">
          <ErrorNote error={error.error} accion={error.accion} />
        </div>
      )}

      <footer className="mt-4 flex flex-wrap items-center gap-3">
        {confirmandoBorrar ? (
          <>
            <span className="text-sm text-humo">¿Borrar esta rutina?</span>
            <button
              onClick={() => void run(() => api.deleteRoutine(routine.id))}
              disabled={enVuelo}
              className="rounded-sm bg-riesgo-d px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:opacity-40"
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
          <>
            {routine.status === 'active' ? (
              <button
                onClick={() => void run(() => api.pauseRoutine(routine.id))}
                disabled={enVuelo}
                className="rounded-sm border border-borde px-4 py-1.5 text-sm text-humo transition-colors hover:text-hueso disabled:opacity-40"
              >
                Pausar
              </button>
            ) : (
              <button
                onClick={() => void run(() => api.resumeRoutine(routine.id))}
                disabled={enVuelo}
                className="rounded-sm border border-borde px-4 py-1.5 text-sm text-humo transition-colors hover:text-hueso disabled:opacity-40"
              >
                Reanudar
              </button>
            )}
            <button
              onClick={() => setConfirmandoBorrar(true)}
              disabled={enVuelo}
              className="rounded-sm border border-borde px-4 py-1.5 text-sm text-humo transition-colors hover:border-riesgo-d hover:text-riesgo-d disabled:opacity-40"
            >
              Borrar
            </button>
          </>
        )}
      </footer>
    </article>
  )
}
