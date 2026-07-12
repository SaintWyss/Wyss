/*
 * Pantalla de pairing bundled del APK.
 * REGLA DURA: cero fetch/XHR/WebSocket — la única comunicación es con los
 * plugins nativos (Capacitor.Plugins). La SPA real llega por loadUrl nativo
 * después del pairing (Pitfall 1: una sola llamada de red desde este bundle
 * reintroduce la colisión de Origin).
 */
'use strict'

const $ = (id) => document.getElementById(id)

const ERRORES = {
  cert_mismatch: {
    titulo: 'El certificado del servidor cambió',
    causa:
      'La identidad del servidor no coincide con la que este teléfono conoce. ' +
      'Pasa si regeneraste el certificado en la PC — o si alguien se hace pasar por tu servidor.',
    accion:
      'Si fuiste vos (certificado nuevo), re-pareá escaneando el QR actual. Si no, no te conectes.',
  },
  net_error: {
    titulo: 'No encuentro el servidor',
    causa: 'El servidor no respondió. Puede estar apagado o haber cambiado de IP.',
    accion:
      'Verificá que la PC tenga «wyss web --lan --tls» corriendo. Si cambió la IP, re-pareá con el QR nuevo.',
  },
}

function mostrar(estado) {
  for (const id of ['estado-scan', 'estado-error', 'estado-pareado']) {
    $(id).hidden = id !== estado
  }
}

function mostrarError(code) {
  const err = ERRORES[code] ?? ERRORES.net_error
  $('error-titulo').textContent = err.titulo
  $('error-causa').textContent = err.causa
  $('error-accion').textContent = err.accion
  mostrar('estado-error')
}

function nota(texto) {
  const el = $('scan-detalle')
  el.textContent = texto
  el.hidden = !texto
}

function plugins() {
  return window.Capacitor && window.Capacitor.Plugins
}

async function escanear() {
  const { Pairing, BarcodeScanner } = plugins()
  const btn = $('btn-escanear')
  btn.disabled = true
  nota('')
  try {
    const { barcodes } = await BarcodeScanner.scan({ formats: ['QR_CODE'] })
    if (!barcodes || barcodes.length === 0) {
      nota('No leí ningún QR. Probá de nuevo.')
      return
    }
    nota('QR leído, conectando…')
    // El string CRUDO va al nativo: la validación autoritativa es PairingPayload.parse.
    await Pairing.completePairing({ payload: barcodes[0].rawValue })
    // Si resolvió, el nativo ya hizo el loadUrl al servidor.
  } catch (e) {
    const msg = (e && e.message) || String(e)
    if (/cancel/i.test(msg)) {
      nota('')
    } else if (/module/i.test(msg)) {
      // Falta el módulo de escaneo de Google Play Services: instalarlo y reintentar.
      nota('Instalando el módulo de escaneo (una sola vez)… reintentá en unos segundos.')
      try {
        await BarcodeScanner.installGoogleBarcodeScannerModule()
      } catch (_) {
        /* el progreso lo maneja Play Services; el reintento manual alcanza */
      }
    } else {
      nota(msg)
    }
  } finally {
    btn.disabled = false
  }
}

async function repararear() {
  const { Pairing } = plugins()
  await Pairing.clearPairing()
  nota('')
  mostrar('estado-scan')
}

async function init() {
  const p = plugins()
  if (!p || !p.Pairing) {
    // Sin runtime Capacitor (abierto en un browser suelto): no hay nada que hacer.
    mostrar('estado-scan')
    nota('Esta pantalla solo funciona dentro de la app Wyss.')
    $('btn-escanear').disabled = true
    return
  }

  $('btn-escanear').addEventListener('click', escanear)
  $('btn-reparear').addEventListener('click', repararear)
  $('btn-olvidar').addEventListener('click', repararear)

  // Fuente de verdad del error: lastError() nativo (lee y limpia). El fragment
  // #error=… es best-effort y puede perderse en el load.
  const hashError = (window.location.hash.match(/error=([a-z_]+)/) || [])[1]
  const { error } = await p.Pairing.lastError()
  const code = error || hashError
  if (code) {
    mostrarError(code)
    return
  }

  const { paired } = await p.Pairing.pairingState()
  mostrar(paired ? 'estado-pareado' : 'estado-scan')
}

init()
