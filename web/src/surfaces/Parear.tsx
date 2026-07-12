import { useCallback, useEffect, useState } from 'react'
import qrcode from 'qrcode-generator'
import { api, WyssApiError, type PairPayload } from '../api'
import { ErrorNote } from '../ui'

/** El string exacto que encodea el QR: el JSON crudo que la app nativa valida. */
export function pairingQrData(payload: PairPayload): string {
  return JSON.stringify(payload)
}

/** SVG del QR generado enteramente client-side (qrcode-generator, cero red). */
export function renderPairingQr(payload: PairPayload): string {
  const qr = qrcode(0, 'M')
  qr.addData(pairingQrData(payload))
  qr.make()
  return qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true })
}

export function Parear() {
  const [payload, setPayload] = useState<PairPayload | null>(null)
  const [error, setError] = useState<WyssApiError | null>(null)
  const [cargando, setCargando] = useState(false)

  const load = useCallback(() => {
    setCargando(true)
    api
      .pair()
      .then((p) => {
        setPayload(p)
        setError(null)
      })
      .catch((e) =>
        setError(
          e instanceof WyssApiError
            ? e
            : new WyssApiError(0, { error: 'error de red', accion: 'reintentá' }),
        ),
      )
      .finally(() => setCargando(false))
  }, [])

  useEffect(load, [load])

  return (
    <section className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="display text-xl font-semibold">Parear teléfono</h2>
        <button
          onClick={load}
          disabled={cargando}
          className="rounded-sm border border-borde px-4 py-1.5 font-mono text-xs text-humo transition-colors hover:border-celeste hover:text-celeste disabled:opacity-40"
        >
          {cargando ? '…' : 'regenerar'}
        </button>
      </div>
      <p className="mt-1 text-sm text-humo">
        Escaneá este QR desde la app Wyss del teléfono. Lleva la dirección del
        servidor, la huella del certificado y tu credencial — mostralo solo a tus
        dispositivos.
      </p>

      <div className="mt-6">
        {error && <ErrorNote error={error.message} accion={error.accion} />}
        {payload && !error && (
          <article className="rounded-md border border-borde bg-papel p-5">
            <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start">
              <div
                aria-label="QR de pairing"
                role="img"
                className="w-56 shrink-0 rounded-md bg-white p-3 [&_svg]:h-auto [&_svg]:w-full"
                dangerouslySetInnerHTML={{ __html: renderPairingQr(payload) }}
              />
              <div className="min-w-0 text-sm">
                <ol className="flex flex-col gap-2 text-humo">
                  <li className="flex gap-2">
                    <span className="font-mono text-xs leading-5 text-celeste">01</span>
                    Abrí la app Wyss en el teléfono.
                  </li>
                  <li className="flex gap-2">
                    <span className="font-mono text-xs leading-5 text-celeste">02</span>
                    Tocá «Escanear QR» y apuntá a esta pantalla.
                  </li>
                  <li className="flex gap-2">
                    <span className="font-mono text-xs leading-5 text-celeste">03</span>
                    Listo: el teléfono queda pareado y entra solo.
                  </li>
                </ol>
                <dl className="mt-5 border-t border-borde pt-4 font-mono text-[11px] text-humo">
                  <dt className="uppercase tracking-widest text-humo/60">servidor</dt>
                  <dd className="mt-0.5 break-all text-hueso/90">{payload.url}</dd>
                  <dt className="mt-3 uppercase tracking-widest text-humo/60">
                    huella del certificado
                  </dt>
                  <dd className="mt-0.5 break-all text-hueso/90">{payload.fp}</dd>
                </dl>
              </div>
            </div>
          </article>
        )}
      </div>
    </section>
  )
}
