import { useEffect, useRef, useState } from 'react'
import { api, WyssApiError, type AskResult, type RiskLevel } from '../api'
import { useDictado } from '../dictado'
import { ErrorNote, ResultadoEjecucion, RiskChip, Salidas } from '../ui'
import { Sello, type Resolucion } from '../documento'

interface Mensaje {
  id: number
  role: 'owner' | 'wyss'
  text?: string
  ask?: AskResult
  error?: { error: string; accion: string }
}

let nextId = 1

export function Chat({ daemonAlive }: { daemonAlive: boolean }) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [input, setInput] = useState('')
  const [enviando, setEnviando] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  // El dictado solo llena el input editable: el owner revisa y envía a mano.
  const dictado = useDictado((texto) =>
    setInput((prev) => (prev ? `${prev} ${texto}` : texto)),
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes])

  const send = async () => {
    const instruction = input.trim()
    if (!instruction || enviando) return
    setInput('')
    setEnviando(true)
    setMensajes((m) => [...m, { id: nextId++, role: 'owner', text: instruction }])
    try {
      const result = await api.ask(instruction)
      setMensajes((m) => [...m, { id: nextId++, role: 'wyss', ask: result }])
    } catch (e) {
      const err =
        e instanceof WyssApiError
          ? { error: e.message, accion: e.accion }
          : { error: 'error de red', accion: 'reintentá' }
      setMensajes((m) => [...m, { id: nextId++, role: 'wyss', error: err }])
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col">
      <div className="flex-1">
        {mensajes.length === 0 && (
          <div className="mt-16 text-center">
            <h2 className="display text-2xl font-semibold">
              ¿Qué despachamos hoy?
            </h2>
            <p className="mx-auto mt-3 max-w-md text-sm text-humo">
              Pedilo en lenguaje natural. Wyss propone un plan con su nivel de
              riesgo; nada se ejecuta sin tu sello.
            </p>
          </div>
        )}
        <div className="flex flex-col gap-4 pb-6">
          {mensajes.map((m) =>
            m.role === 'owner' ? (
              <p
                key={m.id}
                className="ml-auto max-w-[80%] rounded-md bg-papel px-4 py-2.5 text-sm"
              >
                {m.text}
              </p>
            ) : (
              <div key={m.id} className="max-w-[90%]">
                {m.error ? (
                  <ErrorNote error={m.error.error} accion={m.error.accion} />
                ) : m.ask ? (
                  <Respuesta ask={m.ask} daemonAlive={daemonAlive} />
                ) : null}
              </div>
            ),
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <form
        className="sticky bottom-0 flex gap-2 border-t border-borde bg-tinta pb-1 pt-4"
        onSubmit={(e) => {
          e.preventDefault()
          void send()
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={!daemonAlive}
          placeholder={
            daemonAlive
              ? 'Pedile algo a wyss…'
              : 'el daemon no está corriendo — levantalo con: wyss start'
          }
          className="flex-1 rounded-sm border border-borde bg-papel px-4 py-2.5 text-sm placeholder:text-humo/60 disabled:opacity-50"
        />
        {dictado.soportado && (
          <button
            type="button"
            onClick={dictado.toggle}
            disabled={!daemonAlive}
            aria-pressed={dictado.activo}
            title="Dictar (el texto queda editable antes de enviar)"
            className={`rounded-sm border px-3 py-2.5 font-mono text-xs transition-colors disabled:opacity-40 ${
              dictado.activo
                ? 'animate-pulse border-celeste text-celeste'
                : 'border-borde text-humo hover:border-celeste hover:text-celeste'
            }`}
          >
            {dictado.activo ? '● grabando' : '⌾ dictar'}
          </button>
        )}
        <button
          type="submit"
          disabled={!daemonAlive || enviando || input.trim() === ''}
          className="rounded-sm bg-celeste px-5 py-2.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {enviando ? '…' : 'Enviar'}
        </button>
      </form>
    </section>
  )
}

function Respuesta({ ask, daemonAlive }: { ask: AskResult; daemonAlive: boolean }) {
  if (ask.outcome === 'pending' && ask.pending_id) {
    return (
      <PropuestaInline
        pendingId={ask.pending_id}
        plan={ask.plan ?? ''}
        risk={(ask.risk_level ?? 'B') as RiskLevel}
        daemonAlive={daemonAlive}
      />
    )
  }
  if (ask.outcome === 'rejected') {
    return (
      <div className="rounded-md border border-riesgo-d/50 bg-riesgo-d/10 px-4 py-3">
        <p className="text-sm font-medium text-riesgo-d">Rechazado por política</p>
        <ul className="mt-1 flex flex-col gap-0.5">
          {(ask.reasons ?? []).map((r, i) => (
            <li key={i} className="font-mono text-xs text-humo">
              {r}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (ask.outcome === 'queued') {
    return (
      <p className="text-sm text-humo">
        Encolado directo (nivel A):{' '}
        <span className="font-mono text-hueso">{ask.execution_id}</span>
      </p>
    )
  }
  if (ask.outcome === 'executed') {
    return (
      <div className="text-sm">
        {ask.success ? (
          <span className="text-riesgo-a">Ejecutado (nivel A)</span>
        ) : (
          <span className="text-riesgo-d">Falló la ejecución</span>
        )}{' '}
        <span className="font-mono text-xs text-humo">{ask.detail}</span>
        <Salidas outputs={ask.outputs} />
      </div>
    )
  }
  if (ask.outcome === 'degraded') {
    return (
      <p className="text-sm italic text-humo">
        {ask.message ?? 'Orquestador no disponible: modo degradado.'}
      </p>
    )
  }
  return <p className="text-sm">{ask.message ?? JSON.stringify(ask)}</p>
}

/** Plan propuesto embebido en el chat: texto renderizado por el daemon + sello inline. */
function PropuestaInline({
  pendingId,
  plan,
  risk,
  daemonAlive,
}: {
  pendingId: string
  plan: string
  risk: RiskLevel
  daemonAlive: boolean
}) {
  const [resolucion, setResolucion] = useState<Resolucion | null>(null)
  const [gate, setGate] = useState<string | null>(null) // null = sin gate abierto
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)
  const [ejecucion, setEjecucion] = useState<{
    executionId?: string
    success?: boolean
    detail?: string
    outputs?: string[]
  }>({})

  const send = async (approve: boolean) => {
    setError(null)
    try {
      const result = await api.confirm(pendingId, approve)
      if (result.accepted) {
        setResolucion('aprobado')
        setEjecucion({
          executionId: result.execution_id,
          success: result.success,
          detail: result.detail,
          outputs: result.outputs,
        })
      } else {
        setResolucion('rechazado')
      }
    } catch (e) {
      if (e instanceof WyssApiError && e.status === 404) setResolucion('expirada')
      else if (e instanceof WyssApiError)
        setError({ error: e.message, accion: e.accion })
      else setError({ error: 'error de red', accion: 'reintentá' })
    }
  }

  return (
    <article className="rounded-md border border-borde bg-papel p-4">
      <header className="flex items-center gap-3">
        <RiskChip level={risk} />
        <span className="font-mono text-xs text-humo">{pendingId}</span>
      </header>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-hueso/90">
        {plan}
      </pre>
      {error && (
        <div className="mt-3">
          <ErrorNote error={error.error} accion={error.accion} />
        </div>
      )}
      {resolucion === null ? (
        gate !== null ? (
          <footer className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm text-humo">
              Nivel C: escribí{' '}
              <span className="font-mono font-semibold text-riesgo-c">CONFIRMAR</span>
            </span>
            <input
              value={gate}
              onChange={(e) => setGate(e.target.value)}
              autoFocus
              className="rounded-sm border border-borde bg-tinta px-3 py-1.5 font-mono text-sm"
              placeholder="CONFIRMAR"
            />
            <button
              onClick={() => void send(true)}
              disabled={gate !== 'CONFIRMAR'}
              className="rounded-sm bg-riesgo-c px-4 py-1.5 text-sm font-semibold text-tinta disabled:opacity-40"
            >
              Sellar
            </button>
          </footer>
        ) : (
          <footer className="mt-4 flex items-center gap-3">
            <button
              onClick={() => (risk === 'C' ? setGate('') : void send(true))}
              disabled={!daemonAlive}
              className="rounded-sm bg-celeste px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Aprobar
            </button>
            <button
              onClick={() => void send(false)}
              disabled={!daemonAlive}
              className="rounded-sm border border-borde px-4 py-1.5 text-sm text-humo transition-colors hover:border-riesgo-d hover:text-riesgo-d disabled:opacity-40"
            >
              Rechazar
            </button>
            <span className="ml-auto font-mono text-[10px] text-humo">
              también en la bandeja
            </span>
          </footer>
        )
      ) : (
        <footer className="mt-4 flex flex-wrap items-center gap-4">
          <Sello tipo={resolucion} />
          <ResultadoEjecucion {...ejecucion} />
        </footer>
      )}
    </article>
  )
}
