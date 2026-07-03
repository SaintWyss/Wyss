import { useCallback, useEffect, useState } from 'react'
import { api, WyssApiError, type FinResumen } from '../api'
import { ErrorNote } from '../ui'

function mesActual(): string {
  return new Date().toISOString().slice(0, 7) // YYYY-MM
}

function rangoDelMes(mes: string): { desde: string; hasta: string } {
  const [year, month] = mes.split('-').map(Number)
  const desde = `${mes}-01`
  const ultimo = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return { desde, hasta: `${mes}-${String(ultimo).padStart(2, '0')}` }
}

const pesos = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  maximumFractionDigits: 0,
})

export function Finanzas() {
  const [mes, setMes] = useState(mesActual)
  const [resumen, setResumen] = useState<FinResumen | null>(null)
  const [error, setError] = useState<{ error: string; accion: string } | null>(null)

  const load = useCallback(() => {
    const { desde, hasta } = rangoDelMes(mes)
    api
      .finResumen(desde, hasta)
      .then((r) => {
        setResumen(r)
        setError(null)
      })
      .catch((e) =>
        setError(
          e instanceof WyssApiError
            ? { error: e.message, accion: e.accion }
            : { error: 'error de red', accion: 'reintentá' },
        ),
      )
  }, [mes])

  useEffect(load, [load])

  const maxCategoria = resumen
    ? Math.max(1, ...Object.values(resumen.por_categoria))
    : 1

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="display text-xl font-semibold">Finanzas</h2>
        <input
          type="month"
          value={mes}
          onChange={(e) => setMes(e.target.value || mesActual())}
          className="rounded-sm border border-borde bg-papel px-3 py-1.5 font-mono text-xs text-hueso"
          aria-label="Período"
        />
      </div>
      <p className="mt-1 text-sm text-humo">
        Ledger determinístico — los números salen de SQL, nunca de un modelo.
      </p>

      {error && (
        <div className="mt-5">
          <ErrorNote error={error.error} accion={error.accion} />
        </div>
      )}

      {resumen && (
        <>
          <div className="mt-6 grid grid-cols-3 gap-3">
            <Kpi label="Ingresos" valor={resumen.ingresos} />
            <Kpi label="Gastos" valor={resumen.gastos} />
            <Kpi
              label="Superávit"
              valor={resumen.superavit}
              tono={resumen.superavit >= 0 ? 'text-riesgo-a' : 'text-riesgo-d'}
            />
          </div>
          {resumen.dias_cobertura > 0 && (
            <p className="mt-2 font-mono text-[10px] text-humo">
              {resumen.dias_cobertura}{' '}
              {resumen.dias_cobertura === 1 ? 'día' : 'días'} con registros en el
              período
            </p>
          )}

          <h3 className="mt-8 text-sm font-medium text-humo">Gasto por categoría</h3>
          {Object.keys(resumen.por_categoria).length === 0 ? (
            <p className="mt-2 text-sm text-humo">
              Sin gastos registrados en el período. Cargá el primero acá abajo.
            </p>
          ) : (
            <div className="mt-3 flex flex-col gap-2">
              {Object.entries(resumen.por_categoria)
                .sort(([, a], [, b]) => b - a)
                .map(([categoria, monto]) => (
                  <div key={categoria} className="flex items-center gap-3">
                    <span className="w-32 truncate font-mono text-xs text-hueso/90">
                      {categoria}
                    </span>
                    <div className="h-4 flex-1 rounded-sm bg-papel">
                      <div
                        className="h-full rounded-sm bg-celeste/70"
                        style={{ width: `${(monto / maxCategoria) * 100}%` }}
                      />
                    </div>
                    <span className="w-24 text-right font-mono text-xs text-humo">
                      {pesos.format(monto)}
                    </span>
                  </div>
                ))}
            </div>
          )}
        </>
      )}

      <AltaRapida onRegistrada={load} />
    </section>
  )
}

function Kpi({
  label,
  valor,
  tono = 'text-hueso',
}: {
  label: string
  valor: number
  tono?: string
}) {
  return (
    <div className="rounded-md border border-borde bg-papel px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-humo">{label}</p>
      <p className={`mt-1 font-mono text-xl font-medium ${tono}`}>
        {pesos.format(valor)}
      </p>
    </div>
  )
}

function AltaRapida({ onRegistrada }: { onRegistrada: () => void }) {
  const [tipo, setTipo] = useState<'ingreso' | 'gasto'>('gasto')
  const [monto, setMonto] = useState('')
  const [detalle, setDetalle] = useState('') // fuente (ingreso) o categoría (gasto)
  const [fecha, setFecha] = useState('')
  const [estado, setEstado] = useState<
    { kind: 'idle' } | { kind: 'ok' } | { kind: 'error'; error: string; accion: string }
  >({ kind: 'idle' })

  const registrar = async () => {
    const montoNum = Number(monto)
    if (!montoNum || montoNum <= 0) {
      setEstado({
        kind: 'error',
        error: 'el monto debe ser positivo',
        accion: 'reintentá con un monto mayor a 0',
      })
      return
    }
    try {
      await api.finTransaccion({
        tipo,
        monto: montoNum,
        fuente: tipo === 'ingreso' ? detalle || undefined : undefined,
        categoria: tipo === 'gasto' ? detalle || undefined : undefined,
        fecha: fecha || undefined,
      })
      setMonto('')
      setDetalle('')
      setEstado({ kind: 'ok' })
      onRegistrada()
      window.setTimeout(() => setEstado({ kind: 'idle' }), 2500)
    } catch (e) {
      setEstado(
        e instanceof WyssApiError
          ? { kind: 'error', error: e.message, accion: e.accion }
          : { kind: 'error', error: 'error de red', accion: 'reintentá' },
      )
    }
  }

  return (
    <form
      className="mt-8 rounded-md border border-borde bg-papel p-4"
      onSubmit={(e) => {
        e.preventDefault()
        void registrar()
      }}
    >
      <h3 className="text-sm font-medium">Registrar movimiento</h3>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="flex rounded-sm border border-borde">
          {(['gasto', 'ingreso'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTipo(t)}
              className={`px-3 py-1.5 text-sm capitalize transition-colors ${
                tipo === t ? 'bg-celeste font-semibold text-tinta' : 'text-humo'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <input
          value={monto}
          onChange={(e) => setMonto(e.target.value)}
          inputMode="decimal"
          placeholder="monto"
          className="w-28 rounded-sm border border-borde bg-tinta px-3 py-1.5 font-mono text-sm placeholder:text-humo/50"
        />
        <input
          value={detalle}
          onChange={(e) => setDetalle(e.target.value)}
          placeholder={tipo === 'ingreso' ? 'fuente' : 'categoría'}
          className="w-36 rounded-sm border border-borde bg-tinta px-3 py-1.5 text-sm placeholder:text-humo/50"
        />
        <input
          type="date"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
          className="rounded-sm border border-borde bg-tinta px-3 py-1.5 font-mono text-xs text-hueso"
          aria-label="Fecha (opcional, default hoy)"
        />
        <button
          type="submit"
          className="rounded-sm bg-celeste px-4 py-1.5 text-sm font-semibold text-tinta transition-opacity hover:opacity-90"
        >
          Registrar
        </button>
        {estado.kind === 'ok' && (
          <span className="font-mono text-xs text-riesgo-a">registrado ✓</span>
        )}
      </div>
      {estado.kind === 'error' && (
        <div className="mt-3">
          <ErrorNote error={estado.error} accion={estado.accion} />
        </div>
      )}
    </form>
  )
}
