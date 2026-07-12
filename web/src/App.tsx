import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, SESSION_EXPIRED_EVENT, type KbFreshness } from './api'
import { Bandeja } from './surfaces/Bandeja'
import { Chat } from './surfaces/Chat'
import { Buscar } from './surfaces/Buscar'
import { Finanzas } from './surfaces/Finanzas'
import { Auditoria } from './surfaces/Auditoria'
import { Rutinas } from './surfaces/Rutinas'
import { Digest } from './surfaces/Digest'
import { Memoria } from './surfaces/Memoria'
import { Parear } from './surfaces/Parear'

type Surface =
  | 'chat'
  | 'bandeja'
  | 'rutinas'
  | 'digest'
  | 'buscar'
  | 'memoria'
  | 'pellegrini'
  | 'auditoria'
  | 'parear'

// Los agentes van con su nombre propio (Pellegrini = finanzas; Belgrano vendrá después).
const SURFACES: { id: Surface; label: string; rol?: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'bandeja', label: 'Bandeja' },
  { id: 'rutinas', label: 'Rutinas' },
  { id: 'digest', label: 'Digest' },
  { id: 'buscar', label: 'Buscar' },
  { id: 'memoria', label: 'Memoria' },
  { id: 'pellegrini', label: 'Pellegrini', rol: 'finanzas' },
  { id: 'auditoria', label: 'Auditoría' },
  { id: 'parear', label: 'Parear' },
]

// Sidebar desktop: los 8 destinos agrupados por intención (UI-SPEC fase 14).
const GRUPOS: { titulo: string; items: Surface[] }[] = [
  { titulo: 'Operar', items: ['chat', 'bandeja'] },
  { titulo: 'Automatizar', items: ['rutinas', 'digest'] },
  { titulo: 'Saber', items: ['buscar', 'memoria'] },
  { titulo: 'Cuentas', items: ['pellegrini', 'auditoria'] },
  { titulo: 'Dispositivos', items: ['parear'] },
]

/** Lanza la app de escritorio Borjes vía el bridge (ruta fija, sin argumentos). */
function BorjesLauncher() {
  const [estado, setEstado] = useState<'idle' | 'ok' | 'error'>('idle')
  const [detalle, setDetalle] = useState('')

  const lanzar = async () => {
    try {
      await api.lanzarBorjes()
      setEstado('ok')
    } catch (e) {
      setEstado('error')
      setDetalle(e instanceof WyssApiError ? `${e.message} — ${e.accion}` : 'error de red')
    }
    window.setTimeout(() => setEstado('idle'), 2500)
  }

  return (
    <button
      onClick={() => void lanzar()}
      title={estado === 'error' ? detalle : 'Abrir Borjes (navegador de carpetas)'}
      className="flex w-full items-center justify-between rounded-sm px-2.5 py-1.5 text-left text-sm text-humo transition-colors hover:bg-papel/60 hover:text-hueso"
    >
      <span>
        Borjes
        <span className="ml-1.5 font-mono text-[10px] text-humo/70">escritorio</span>
      </span>
      <span className="font-mono text-[10px]">
        {estado === 'idle' && '↗'}
        {estado === 'ok' && <span className="text-riesgo-a">✓</span>}
        {estado === 'error' && <span className="text-riesgo-d">✗</span>}
      </span>
    </button>
  )
}

function surfaceFromHash(): Surface {
  const raw = window.location.hash.replace('#/', '')
  return (SURFACES.find((s) => s.id === raw)?.id ?? 'chat') as Surface
}

function useHashSurface(): [Surface, (s: Surface) => void] {
  const [surface, setSurface] = useState<Surface>(surfaceFromHash)
  useEffect(() => {
    const onHash = () => setSurface(surfaceFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const navigate = useCallback((s: Surface) => {
    window.location.hash = `#/${s}`
  }, [])
  return [surface, navigate]
}

export default function App() {
  const [surface, navigate] = useHashSurface()
  const [sessionExpired, setSessionExpired] = useState(false)
  const [daemonAlive, setDaemonAlive] = useState<boolean | null>(null)
  const [bridgeError, setBridgeError] = useState<string | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [kbs, setKbs] = useState<KbFreshness[]>([])

  useEffect(() => {
    const onExpired = () => setSessionExpired(true)
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [])

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const [daemon, pending] = await Promise.all([api.daemon(), api.pending()])
        if (!active) return
        setDaemonAlive(daemon.alive)
        setPendingCount(pending.pending.length)
        setBridgeError(null)
      } catch (e) {
        // El polling no interrumpe la UI, pero el motivo tiene que verse:
        // "bridge inaccesible (403 origen)" ≠ "daemon apagado" — el smoke
        // físico del teléfono fue indiagnosticable por tragar este error.
        if (!active) return
        setBridgeError(
          e instanceof WyssApiError ? `${e.message} — ${e.accion}` : 'error de red',
        )
      }
    }
    void tick()
    const interval = window.setInterval(() => void tick(), 5000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    api
      .status()
      .then((s) => setKbs(s.kbs))
      .catch(() => setKbs([]))
  }, [])

  if (sessionExpired) {
    return (
      <main className="flex min-h-screen items-center justify-center px-6">
        <div className="max-w-md">
          <h1 className="display text-2xl font-semibold">Sesión vencida</h1>
          <p className="mt-3 text-humo">
            El servidor se reinició y el token cambió. Volvé a abrir la URL que
            imprime <span className="font-mono text-hueso">wyss web</span>.
          </p>
        </div>
      </main>
    )
  }

  const totalFiles = kbs.reduce((sum, kb) => sum + kb.files, 0)

  return (
    <div className="flex h-dvh">
      <aside className="hidden w-56 shrink-0 flex-col border-r border-borde px-4 py-5 lg:flex">
        <h1 className="display text-lg font-bold tracking-tight">WYSS</h1>
        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-humo">
          mesa de despacho
        </p>
        <nav className="mt-7 flex flex-col gap-4" aria-label="Secciones">
          {GRUPOS.map(({ titulo, items }) => (
            <div key={titulo}>
              <p className="mb-1 px-2.5 font-mono text-[10px] uppercase tracking-widest text-humo/60">
                {titulo}
              </p>
              <div className="flex flex-col gap-0.5">
                {items.map((id) => {
                  const { label, rol } = SURFACES.find((s) => s.id === id)!
                  const active = surface === id
                  return (
                    <button
                      key={id}
                      onClick={() => navigate(id)}
                      aria-current={active ? 'page' : undefined}
                      className={`flex items-center justify-between rounded-sm px-2.5 py-1.5 text-left text-sm transition-colors ${
                        active
                          ? 'bg-papel text-hueso shadow-[inset_2px_0_0_0_var(--color-celeste)]'
                          : 'text-humo hover:bg-papel/60 hover:text-hueso'
                      }`}
                    >
                      <span>
                        {label}
                        {rol && (
                          <span className="ml-1.5 font-mono text-[10px] text-humo/70">
                            {rol}
                          </span>
                        )}
                      </span>
                      {id === 'bandeja' && pendingCount > 0 && (
                        <span className="rounded-full bg-celeste px-1.5 font-mono text-[10px] font-bold text-tinta">
                          {pendingCount}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>
        <div className="mt-auto">
          <p className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-humo/60">
            apps
          </p>
          <BorjesLauncher />
          <a
            href="http://localhost:3000"
            target="_blank"
            rel="noreferrer"
            title="Abrir RAG Corp (requiere el stack corriendo: pnpm dev o compose)"
            className="flex w-full items-center justify-between rounded-sm px-2.5 py-1.5 text-left text-sm text-humo transition-colors hover:bg-papel/60 hover:text-hueso"
          >
            <span>
              RAG Corp
              <span className="ml-1.5 font-mono text-[10px] text-humo/70">web</span>
            </span>
            <span className="font-mono text-[10px]">↗</span>
          </a>
          <p className="mt-5 font-mono text-[10px] text-humo/60">
            {window.location.hostname === '127.0.0.1' ||
            window.location.hostname === 'localhost'
              ? '127.0.0.1 · solo esta máquina'
              : `${window.location.hostname} · red local`}
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-borde px-4 py-2.5 md:px-6">
          <div className="flex items-center gap-2 text-sm">
            <span className="display mr-1 text-sm font-bold tracking-tight lg:hidden">
              WYSS
            </span>
            {bridgeError !== null ? (
              <>
                <span aria-hidden className="text-riesgo-d">
                  ●
                </span>
                <span className="text-hueso">bridge: {bridgeError}</span>
              </>
            ) : daemonAlive === null ? (
              <span className="text-humo">conectando…</span>
            ) : daemonAlive ? (
              <>
                <span aria-hidden className="text-riesgo-a">
                  ●
                </span>
                <span className="text-humo">daemon activo</span>
              </>
            ) : (
              <>
                <span aria-hidden className="text-riesgo-d">
                  ●
                </span>
                <span className="text-hueso">el daemon no está corriendo</span>
                <span className="font-mono text-xs text-humo">
                  levantalo con: wyss start
                </span>
              </>
            )}
          </div>
          <p className="hidden font-mono text-xs text-humo sm:block">
            {kbs.length > 0
              ? `${kbs.length} BC · ${totalFiles.toLocaleString('es-AR')} archivos`
              : 'índice vacío'}
          </p>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-6">
          {surface === 'chat' && <Chat daemonAlive={daemonAlive === true} />}
          {surface === 'bandeja' && <Bandeja daemonAlive={daemonAlive === true} />}
          {surface === 'rutinas' && <Rutinas />}
          {surface === 'digest' && <Digest />}
          {surface === 'buscar' && <Buscar kbs={kbs} />}
          {surface === 'memoria' && <Memoria />}
          {surface === 'pellegrini' && <Finanzas />}
          {surface === 'auditoria' && <Auditoria />}
          {surface === 'parear' && <Parear />}
        </main>

        <nav
          aria-label="Secciones"
          className="flex shrink-0 overflow-x-auto border-t border-borde bg-tinta pb-[env(safe-area-inset-bottom)] lg:hidden"
        >
          {SURFACES.map(({ id, label }) => {
            const active = surface === id
            return (
              <button
                key={id}
                onClick={() => navigate(id)}
                aria-current={active ? 'page' : undefined}
                className={`relative min-w-[72px] flex-1 whitespace-nowrap px-2 py-2.5 text-center text-[11px] transition-colors ${
                  active
                    ? 'text-hueso shadow-[inset_0_2px_0_0_var(--color-celeste)]'
                    : 'text-humo'
                }`}
              >
                {label}
                {id === 'bandeja' && pendingCount > 0 && (
                  <span className="absolute right-1/2 top-1 mr-[-22px] rounded-full bg-celeste px-1.5 font-mono text-[9px] font-bold leading-4 text-tinta">
                    {pendingCount}
                  </span>
                )}
              </button>
            )
          })}
        </nav>
      </div>
    </div>
  )
}
