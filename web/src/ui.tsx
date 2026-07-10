import type { ReactNode } from 'react'
import type { RiskLevel } from './api'

const RISK_STYLES: Record<RiskLevel, string> = {
  A: 'text-riesgo-a border-riesgo-a/60',
  B: 'text-riesgo-b border-riesgo-b/60',
  C: 'text-riesgo-c border-riesgo-c/60',
  D: 'text-riesgo-d border-riesgo-d/60',
}

const RISK_LABELS: Record<RiskLevel, string> = {
  A: 'A · automático',
  B: 'B · confirmación simple',
  C: 'C · confirmación fuerte',
  D: 'D · prohibido',
}

export function RiskChip({ level }: { level: RiskLevel }) {
  const style = RISK_STYLES[level] ?? RISK_STYLES.D
  const label = RISK_LABELS[level] ?? level
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-xs font-medium uppercase tracking-wide ${style}`}
    >
      {label}
    </span>
  )
}

export function EmptyState({
  mensaje,
  siguiente,
}: {
  mensaje: string
  siguiente?: ReactNode
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-borde px-6 py-10">
      <p className="text-humo">{mensaje}</p>
      {siguiente && <p className="text-sm text-hueso">{siguiente}</p>}
    </div>
  )
}

export function ErrorNote({ error, accion }: { error: string; accion: string }) {
  return (
    <div className="rounded-md border border-riesgo-d/50 bg-riesgo-d/10 px-4 py-3">
      <p className="text-sm text-hueso">{error}</p>
      <p className="mt-1 font-mono text-xs text-humo">{accion}</p>
    </div>
  )
}

/** Salidas visibles de pasos de lectura (file.read/list/stat, git): monospace, scroll. */
export function Salidas({ outputs }: { outputs?: string[] }) {
  if (!outputs || outputs.length === 0) return null
  return (
    <div className="mt-2 flex w-full flex-col gap-2">
      {outputs.map((salida, i) => (
        <pre
          key={i}
          className="max-h-64 overflow-auto whitespace-pre-wrap rounded-sm border border-borde bg-papel/60 px-3 py-2 font-mono text-xs text-hueso"
        >
          {salida}
        </pre>
      ))}
    </div>
  )
}

/** Resultado real de la ejecución post-confirmación (RC: el daemon ejecuta). */
export function ResultadoEjecucion({
  executionId,
  success,
  detail,
  outputs,
}: {
  executionId?: string
  success?: boolean
  detail?: string
  outputs?: string[]
}) {
  if (executionId === undefined) return null
  if (success === undefined) {
    // daemon viejo sin runner: solo encoló
    return (
      <span className="font-mono text-xs text-humo">Encolado: {executionId}</span>
    )
  }
  return (
    // div (no span): Salidas renderiza bloques <pre> y anidar block en inline es DOM inválido
    <div className="min-w-0 flex-1 text-sm">
      {success ? (
        <span className="text-riesgo-a">Ejecutado</span>
      ) : (
        <span className="text-riesgo-d">Falló</span>
      )}{' '}
      <span className="font-mono text-xs text-humo">{detail}</span>
      <Salidas outputs={outputs} />
    </div>
  )
}
