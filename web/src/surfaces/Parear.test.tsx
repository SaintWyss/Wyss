import { describe, expect, it } from 'vitest'
import type { PairPayload } from '../api'
import { pairingQrData, renderPairingQr } from './Parear'

const payload: PairPayload = {
  v: 1,
  url: 'https://192.168.100.5:7777',
  fp: 'AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99',
  token: 'un-token-de-prueba-largo-1234567890',
}

describe('pairingQrData', () => {
  it('encodea exactamente el JSON del payload (lo que la app nativa parsea)', () => {
    const data = pairingQrData(payload)
    expect(JSON.parse(data)).toEqual(payload)
    expect(data).toBe(JSON.stringify(payload))
  })
})

describe('renderPairingQr', () => {
  it('produce un SVG no vacío', () => {
    const svg = renderPairingQr(payload)
    expect(svg).toContain('<svg')
    expect(svg).toContain('</svg>')
  })

  it('es determinista para el mismo payload y cambia si cambia el payload', () => {
    expect(renderPairingQr(payload)).toBe(renderPairingQr(payload))
    const otro = { ...payload, token: 'otro-token' }
    expect(renderPairingQr(otro)).not.toBe(renderPairingQr(payload))
  })
})
