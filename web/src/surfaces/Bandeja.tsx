import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, type Pending } from '../api'
import { EmptyState, ErrorNote, ResultadoEjecucion, RiskChip } from '../ui'
import { Sello, useCountdown, type Resolucion } from '../documento'

export function Bandeja({ daemonAlive }: { daemonAlive: boolean }) {
  const [pending, setPending] = useState<Pending[] | null>(null)
  const [error, setError] = useState<WyssApiError | null>(null)

  const load = useCallback(() => {
    api
      .pending()
      .then((r) => {
        setPending(r.pending)
        setError(null)
      })
      .catch((e) => setError(e instanceof WyssApiError ? e : null))
  }, [])

  useEffect(load, [load])

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex items-baseline justify-between">
        <h2 className="display text-xl font-semibold">Bandeja</h2>
        <button
          onClick={load}
          className="font-mono text-xs text-humo transition-colors hover:text-celeste"
        >
          actualizar
        </button>
      </div>
      <p className="mt-1 text-sm text-humo">
        Propuestas que esperan tu decisión. Nada se ejecuta sin tu sello.
      </p>

      <div className="mt-6 flex flex-col gap-4">
        {error && <ErrorNote error={error.message} accion={error.accion} />}
        {pending !== null && pending.length === 0 && !error && (
          <EmptyState
            mensaje="Sin propuestas pendientes."
            siguiente={
              <>
                Pedile algo a wyss en el{' '}
                <a href="#/chat" className="text-celeste underline underline-offset-2">
                  chat
                </a>
                .
              </>
            }
          />
        )}
        {pending?.map((p) => (
          <Documento key={p.id} pending={p} daemonAlive={daemonAlive} />
        ))}
      </div>
    </section>
  )
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'gate' } // nivel C: exige tipear CONFIRMAR
  | { kind: 'enviando' }
  | {
      kind: 'resuelto'
      resolucion: Resolucion
      executionId?: string
      success?: boolean
      detail?: string
    }
  | { kind: 'error'; error: string; accion: string }

function Documento({ pending, daemonAlive }: { pending: Pending; daemonAlive: boolean }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [gateText, setGateText] = useState('')
  const countdown = useCountdown(pending.expires_at)
  const expirada = countdown === null && phase.kind === 'idle'

  const send = async (approve: boolean) => {
    setPhase({ kind: 'enviando' })
    try {
      const result = await api.confirm(pending.id, approve)
      if (result.accepted) {
        setPhase({
          kind: 'resuelto',
          resolucion: 'aprobado',
          executionId: result.execution_id,
          success: result.success,
          detail: result.detail,
        })
      } else {
        setPhase({ kind: 'resuelto', resolucion: 'rechazado' })
      }
    } catch (e) {
      if (e instanceof WyssApiError && e.status === 404) {
        setPhase({ kind: 'resuelto', resolucion: 'expirada' })
      } else if (e instanceof WyssApiError) {
        setPhase({ kind: 'error', error: e.message, accion: e.accion })
      } else {
        setPhase({ kind: 'error', error: 'error de red', accion: 'reintentá' })
      }
    }
  }

  const aprobar = () => {
    if (pending.risk_level === 'C') {
      setPhase({ kind: 'gate' })
      return
    }
    void send(true)
  }

  const resuelto = phase.kind === 'resuelto'

  return (
    <article
      className={`relative rounded-md border border-borde bg-papel p-5 transition-opacity ${
        resuelto || expirada ? 'opacity-70' : ''
      }`}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <RiskChip level={pending.risk_level} />
        <span className="font-mono text-xs text-humo">{pending.id}</span>
        <span className="ml-auto font-mono text-xs text-humo">
          {resuelto ? '' : countdown === null ? 'expirada' : `expira en ${countdown}`}
        </span>
      </header>

      <h3 className="mt-3 font-medium">{pending.plan.summary}</h3>
      {pending.plan.rationale && (
        <p className="mt-1 text-sm text-humo">{pending.plan.rationale}</p>
      )}

      <ol className="mt-4 flex flex-col gap-1.5">
        {pending.plan.steps.map((step, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="font-mono text-xs leading-5 text-humo">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span>
              <span className="font-mono text-celeste">{step.type}</span>{' '}
              <span className="font-mono text-hueso/90">{step.target}</span>
            </span>
          </li>
        ))}
      </ol>

      {phase.kind === 'error' && (
        <div className="mt-4">
          <ErrorNote error={phase.error} accion={phase.accion} />
        </div>
      )}

      {(phase.kind === 'idle' || phase.kind === 'enviando') && !expirada && (
        <footer className="mt-5 flex items-center gap-3">
          <button
            onClick={aprobar}
            disabled={!daemonAlive || phase.kind === 'enviando'}
            className="rounded-sm bg-celeste px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Aprobar
          </button>
          <button
            onClick={() => void send(false)}
            disabled={!daemonAlive || phase.kind === 'enviando'}
            className="rounded-sm border border-borde px-4 py-1.5 text-sm text-humo transition-colors hover:border-riesgo-d hover:text-riesgo-d disabled:cursor-not-allowed disabled:opacity-40"
          >
            Rechazar
          </button>
          {!daemonAlive && (
            <span className="font-mono text-xs text-humo">
              requiere daemon: wyss start
            </span>
          )}
        </footer>
      )}

      {phase.kind === 'gate' && (
        <footer className="mt-5 flex flex-wrap items-center gap-3">
          <label className="text-sm text-humo" htmlFor={`gate-${pending.id}`}>
            Nivel C: escribí{' '}
            <span className="font-mono font-semibold text-riesgo-c">CONFIRMAR</span>
          </label>
          <input
            id={`gate-${pending.id}`}
            value={gateText}
            onChange={(e) => setGateText(e.target.value)}
            autoFocus
            className="rounded-sm border border-borde bg-tinta px-3 py-1.5 font-mono text-sm text-hueso placeholder:text-humo/50"
            placeholder="CONFIRMAR"
          />
          <button
            onClick={() => void send(true)}
            disabled={gateText !== 'CONFIRMAR'}
            className="rounded-sm bg-riesgo-c px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Sellar
          </button>
          <button
            onClick={() => {
              setPhase({ kind: 'idle' })
              setGateText('')
            }}
            className="text-sm text-humo hover:text-hueso"
          >
            Cancelar
          </button>
        </footer>
      )}

      {resuelto && (
        <footer className="mt-5 flex flex-wrap items-center gap-4">
          <Sello tipo={phase.resolucion} />
          <ResultadoEjecucion
            executionId={phase.executionId}
            success={phase.success}
            detail={phase.detail}
          />
        </footer>
      )}

      {expirada && phase.kind === 'idle' && (
        <footer className="mt-5">
          <Sello tipo="expirada" />
        </footer>
      )}
    </article>
  )
}
