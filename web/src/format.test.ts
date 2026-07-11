import { describe, expect, it } from 'vitest'
import { formatRelative, formatSchedule, outcomeColor, statusLabel } from './format'

describe('formatSchedule', () => {
  it('formatea interval', () => {
    expect(formatSchedule({ kind: 'interval', expr: '120s' })).toBe('interval 120s')
  })

  it('formatea cron', () => {
    expect(formatSchedule({ kind: 'cron', expr: '0 8 * * *' })).toBe('cron 0 8 * * *')
  })
})

describe('outcomeColor', () => {
  it('mapea outcomes conocidos y vacíos', () => {
    expect(outcomeColor('executed')).toBe('text-riesgo-a')
    expect(outcomeColor('pending')).toBe('text-humo')
    expect(outcomeColor('failed')).toBe('text-riesgo-d')
    expect(outcomeColor(null)).toBe('text-humo')
  })
})

describe('formatRelative', () => {
  it('null significa nunca', () => {
    expect(formatRelative(null)).toBe('nunca')
  })
})

describe('statusLabel', () => {
  it('mapea estados principales', () => {
    expect(statusLabel('active')).toEqual({ label: 'activa', className: 'text-celeste' })
    expect(statusLabel('paused')).toEqual({ label: 'pausada', className: 'text-humo' })
  })
})
