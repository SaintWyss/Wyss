import { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'

export type Resolucion = 'aprobado' | 'rechazado' | 'expirada'

const SELLO_STYLES: Record<Resolucion, string> = {
  aprobado: 'border-celeste text-celeste',
  rechazado: 'border-riesgo-d text-riesgo-d',
  expirada: 'border-humo text-humo',
}

const SELLO_TEXTO: Record<Resolucion, string> = {
  aprobado: 'Aprobado',
  rechazado: 'Rechazado',
  expirada: 'Expirada',
}

/** El sello: golpe de goma sobre el documento. Firma visual de la app. */
export function Sello({ tipo }: { tipo: Resolucion }) {
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      gsap.set(el, { scale: 1, opacity: 1, rotation: -8 })
      return
    }
    const tween = gsap.fromTo(
      el,
      { scale: 2.4, opacity: 0, rotation: -8 },
      { scale: 1, opacity: 1, rotation: -8, duration: 0.28, ease: 'back.out(2.5)' },
    )
    return () => {
      tween.kill()
    }
  }, [])

  return (
    <span
      ref={ref}
      className={`display pointer-events-none inline-block select-none rounded-sm border-4 px-3 py-1 text-xl font-black uppercase tracking-widest opacity-0 ${SELLO_STYLES[tipo]}`}
    >
      {SELLO_TEXTO[tipo]}
    </span>
  )
}

/** Formatea milisegundos restantes. null = ya expiró. Pura, testeada en documento.test.ts. */
export function formatRemaining(remainingMs: number): string | null {
  if (Number.isNaN(remainingMs)) return '—'
  if (remainingMs <= 0) return null
  const mins = Math.floor(remainingMs / 60_000)
  if (mins < 1) return '<1m'
  if (mins < 60) return `${mins}m`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

/** Cuenta regresiva sobre expires_at (ISO). null = ya expiró. */
export function useCountdown(expiresAt: string): string | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(interval)
  }, [])
  return formatRemaining(Date.parse(expiresAt) - now)
}
