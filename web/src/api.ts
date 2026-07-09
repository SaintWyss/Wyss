// Espejo a mano del contrato del bridge (src/bootstrap/web.py).
// Fuente de verdad del shape: tests/bootstrap/test_web.py.

export type RiskLevel = 'A' | 'B' | 'C' | 'D'

export interface ApiError {
  error: string
  accion: string
}

export interface RetryParams {
  max_attempts: number
  backoff_base_s: number
  backoff_max_s: number
}

export interface PlanStep {
  type: string
  target: string
  parameters: Record<string, unknown>
  on_error: string
  retry_params: RetryParams | null
}

export interface Plan {
  task_id: string
  summary: string
  steps: PlanStep[]
  rationale: string
  estimated_risk: string | null
}

export interface Pending {
  id: string
  task_id: string
  plan: Plan
  risk_level: RiskLevel
  outcome: string
  created_at: string
  expires_at: string
}

export interface AskResult {
  outcome: 'pending' | 'rejected' | 'queued' | 'executed' | 'degraded' | string
  pending_id?: string
  plan?: string
  risk_level?: RiskLevel
  reasons?: string[]
  execution_id?: string
  message?: string
  // outcome 'executed' (nivel A con executor real, RC): resultado honesto
  success?: boolean
  detail?: string
}

export interface ConfirmResult {
  accepted: boolean
  execution_id?: string
  reason?: string
  // presentes cuando el daemon ejecutó de verdad (RC: PlanExecutor cableado)
  success?: boolean
  detail?: string
}

export interface KbFreshness {
  kb_id: string
  files: number
  last_indexed: string | null
  embedded: number
  pending: number
  failed: number
}

export interface Hit {
  entry_id: string
  score: number
  snippet: string
  source_path: string
  date: string | null
}

export interface SearchResult {
  hits: Hit[]
  degraded: boolean
  reason: string | null
  freshness: KbFreshness[]
}

export interface FinResumen {
  ingresos: number
  gastos: number
  superavit: number
  por_categoria: Record<string, number>
  dias_cobertura: number
}

export interface Transaccion {
  tipo: 'ingreso' | 'gasto'
  monto: number
  fecha: string
  fuente: string | null
  categoria: string | null
  created_at: string
}

export interface AuditEvent {
  created_at: string
  actor_id: string
  event_type: string
  message: string
}

export interface DaemonStatus {
  alive: boolean
}

/** Error con causa + acción, shape estable del bridge. */
export class WyssApiError extends Error {
  accion: string
  status: number

  constructor(status: number, body: ApiError) {
    super(body.error)
    this.accion = body.accion
    this.status = status
  }
}

/** 401 = el server se reinició y el token cambió: sesión vencida. */
export const SESSION_EXPIRED_EVENT = 'wyss:session-expired'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (response.status === 401) {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    throw new WyssApiError(401, {
      error: 'sesión vencida',
      accion: 'volvé a abrir la URL que imprime wyss web',
    })
  }
  if (!response.ok) {
    let body: ApiError
    try {
      body = (await response.json()) as ApiError
    } catch {
      body = { error: `error ${response.status}`, accion: 'reintentá' }
    }
    throw new WyssApiError(response.status, body)
  }
  return (await response.json()) as T
}

export const api = {
  status: () => apiFetch<{ kbs: KbFreshness[] }>('/api/status'),
  daemon: () => apiFetch<DaemonStatus>('/api/daemon'),
  pending: () => apiFetch<{ pending: Pending[] }>('/api/pending'),
  search: (q: string, kb?: string, limit = 10) => {
    const params = new URLSearchParams({ q, limit: String(limit) })
    if (kb) params.set('kb', kb)
    return apiFetch<SearchResult>(`/api/search?${params}`)
  },
  finResumen: (desde?: string, hasta?: string) => {
    const params = new URLSearchParams()
    if (desde) params.set('desde', desde)
    if (hasta) params.set('hasta', hasta)
    const qs = params.size > 0 ? `?${params}` : ''
    return apiFetch<FinResumen>(`/api/fin/resumen${qs}`)
  },
  finTransaccion: (body: {
    tipo: 'ingreso' | 'gasto'
    monto: number
    fuente?: string
    categoria?: string
    fecha?: string
  }) =>
    apiFetch<{ transaccion: Transaccion }>('/api/fin/transaccion', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  audit: (since?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (since) params.set('since', since)
    return apiFetch<{ events: AuditEvent[] }>(`/api/audit?${params}`)
  },
  lanzarBorjes: () =>
    apiFetch<{ lanzado: boolean }>('/api/apps/borjes', { method: 'POST' }),
  ask: (instruction: string) =>
    apiFetch<AskResult>('/api/ask', {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    }),
  confirm: (pendingId: string, approve: boolean) =>
    apiFetch<ConfirmResult>(`/api/confirm/${encodeURIComponent(pendingId)}`, {
      method: 'POST',
      body: JSON.stringify({ approve }),
    }),
}
