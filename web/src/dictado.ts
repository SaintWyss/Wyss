// Dictado por voz vía Web Speech API (feature-detect, sin dependencias).
//
// Reglas de seguridad del bridge móvil:
// - el resultado SIEMPRE cae al input de texto editable — jamás se auto-envía
// - el owner ve el comando interpretado antes de mandarlo
// - la confirmación B/C aplica igual que con texto tipeado
//
// Nota: los browsers exigen contexto seguro (HTTPS o localhost) para el
// micrófono. Sobre http://<ip-lan> el API no está disponible → el botón no se
// muestra y queda el input de texto (fallback obligatorio).

import { useCallback, useEffect, useRef, useState } from 'react'

interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: SpeechResultEvent) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start(): void
  stop(): void
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function detectarCtor(): SpeechRecognitionCtor | null {
  // Sin secure context (http://<ip-lan>) el mic está vedado aunque el ctor
  // exista: ocultar el botón y dejar el input de texto (fallback obligatorio).
  // Con `wyss web --tls` (PR-10) esto pasa a true y la voz se destraba.
  if (!window.isSecureContext) return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function useDictado(onTexto: (texto: string) => void) {
  const ctor = useRef<SpeechRecognitionCtor | null>(null)
  const rec = useRef<SpeechRecognitionLike | null>(null)
  const [soportado, setSoportado] = useState(false)
  const [activo, setActivo] = useState(false)

  useEffect(() => {
    ctor.current = detectarCtor()
    setSoportado(ctor.current !== null)
    return () => rec.current?.stop()
  }, [])

  const toggle = useCallback(() => {
    if (activo) {
      rec.current?.stop()
      return
    }
    if (ctor.current === null) return
    const r = new ctor.current()
    r.lang = 'es-AR'
    r.interimResults = false
    r.continuous = false
    r.onresult = (event) => {
      const partes: string[] = []
      for (let i = 0; i < event.results.length; i++) {
        partes.push(event.results[i][0].transcript)
      }
      const texto = partes.join(' ').trim()
      if (texto) onTexto(texto)
    }
    r.onend = () => setActivo(false)
    r.onerror = () => setActivo(false)
    rec.current = r
    setActivo(true)
    r.start()
  }, [activo, onTexto])

  return { soportado, activo, toggle }
}
