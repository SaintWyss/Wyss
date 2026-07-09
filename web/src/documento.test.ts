import { describe, expect, it } from 'vitest'
import { formatRemaining } from './documento'

describe('formatRemaining', () => {
  it('expirada: cero o negativo → null', () => {
    expect(formatRemaining(0)).toBeNull()
    expect(formatRemaining(-5_000)).toBeNull()
  })

  it('fecha imparseable → em dash', () => {
    expect(formatRemaining(Number.NaN)).toBe('—')
  })

  it('menos de un minuto', () => {
    expect(formatRemaining(30_000)).toBe('<1m')
  })

  it('minutos', () => {
    expect(formatRemaining(59 * 60_000)).toBe('59m')
  })

  it('horas y minutos', () => {
    expect(formatRemaining(90 * 60_000)).toBe('1h 30m')
    expect(formatRemaining(120 * 60_000)).toBe('2h 0m')
  })
})
