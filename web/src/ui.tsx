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
