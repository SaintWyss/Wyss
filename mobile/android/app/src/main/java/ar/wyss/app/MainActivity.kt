package ar.wyss.app

import android.net.http.SslCertificate
import android.net.http.SslError
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.SslErrorHandler
import android.webkit.WebView
import com.getcapacitor.Bridge
import com.getcapacitor.BridgeActivity
import com.getcapacitor.BridgeWebViewClient
import java.io.ByteArrayInputStream
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.Locale

private const val TAG = "WyssSpike"
private const val SPIKE_URL = "https://192.168.100.5:7777"
private const val SPIKE_FP =
    "24:32:68:D9:C0:58:52:C1:85:61:D8:A1:03:3F:9D:ED:E9:51:29:EF:35:2C:00:70:2B:4D:79:47:1E:2C:54:DA"

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val currentBridge = bridge ?: return
        currentBridge.setWebViewClient(PinnedSpikeWebViewClient(currentBridge))
        Handler(Looper.getMainLooper()).postDelayed(
            {
                Log.i(TAG, "navegando spike a $SPIKE_URL")
                currentBridge.getWebView().loadUrl(SPIKE_URL)
            },
            3000L,
        )
    }
}

private class PinnedSpikeWebViewClient(bridge: Bridge) : BridgeWebViewClient(bridge) {
    override fun onReceivedSslError(
        view: WebView,
        handler: SslErrorHandler,
        error: SslError,
    ) {
        try {
            val bundle = SslCertificate.saveState(error.certificate)
            val x509Bytes = bundle.getByteArray("x509-certificate")
                ?: throw IllegalStateException("SslCertificate sin x509-certificate")
            val certificate = CertificateFactory
                .getInstance("X.509")
                .generateCertificate(ByteArrayInputStream(x509Bytes)) as X509Certificate
            val presentedFp = sha256Fingerprint(certificate.encoded)
            val match = presentedFp == SPIKE_FP

            Log.i(
                TAG,
                "huella presentada=$presentedFp huella esperada=$SPIKE_FP match=$match",
            )
            if (match) {
                handler.proceed()
                return
            }

            handler.cancel()
            Log.w(TAG, "certificado TLS rechazado por fingerprint mismatch")
        } catch (exc: Exception) {
            handler.cancel()
            Log.e(TAG, "certificado TLS rechazado: no pude extraer/verificar fingerprint", exc)
        }
    }

    private fun sha256Fingerprint(encodedCertificate: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(encodedCertificate)
        return digest.joinToString(":") { byte ->
            "%02X".format(Locale.US, byte.toInt() and 0xff)
        }
    }
}
