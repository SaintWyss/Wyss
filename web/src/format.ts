export interface ScheduleLike {
  kind: string
  expr: string
}

export interface StatusLabel {
  label: string
  className: string
}

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

export function formatRelative(iso: string | null): string {
  if (!iso) return 'nunca'
  const timestamp = Date.parse(iso)
  if (Number.isNaN(timestamp)) return 'nunca'

  const diff = Date.now() - timestamp
  if (diff < MINUTE_MS) return 'ahora'
  if (diff < HOUR_MS) return `hace ${Math.floor(diff / MINUTE_MS)} min`
  if (diff < DAY_MS) return `hace ${Math.floor(diff / HOUR_MS)} h`
  return `hace ${Math.floor(diff / DAY_MS)} d`
}

export function formatSchedule(schedule: ScheduleLike): string {
  return `${schedule.kind} ${schedule.expr}`
}

export function outcomeColor(outcome: string | null): string {
  if (outcome === 'executed') return 'text-riesgo-a'
  if (outcome === 'failed') return 'text-riesgo-d'
  return 'text-humo'
}

export function statusLabel(status: string): StatusLabel {
  if (status === 'active') return { label: 'activa', className: 'text-celeste' }
  if (status === 'paused') return { label: 'pausada', className: 'text-humo' }
  return { label: status, className: 'text-humo' }
}
