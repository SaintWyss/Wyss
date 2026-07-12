package ar.wyss.app

import android.net.http.SslCertificate
import android.net.http.SslError
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import com.getcapacitor.Bridge
import com.getcapacitor.BridgeWebViewClient

class PinnedWebViewClient(
    bridge: Bridge,
    private val pinnedFp: String,
    private val onTrustFailure: (String) -> Unit,
) : BridgeWebViewClient(bridge) {
    override fun onReceivedSslError(
        view: WebView,
        handler: SslErrorHandler,
        error: SslError,
    ) {
        try {
            val bundle = SslCertificate.saveState(error.certificate)
            val der = bundle.getByteArray("x509-certificate")
                ?: throw IllegalStateException("SslCertificate missing x509-certificate")

            if (FingerprintMatcher.matches(der, pinnedFp)) {
                handler.proceed()
                return
            }

            handler.cancel()
            notifyTrustFailure("cert_mismatch")
        } catch (_: Exception) {
            handler.cancel()
            notifyTrustFailure("cert_mismatch")
        }
    }

    override fun onReceivedError(
        view: WebView,
        request: WebResourceRequest,
        error: WebResourceError,
    ) {
        if (request.isForMainFrame) {
            notifyTrustFailure("net_error")
        }
        super.onReceivedError(view, request, error)
    }

    private fun notifyTrustFailure(code: String) {
        try {
            onTrustFailure(code)
        } catch (_: Exception) {
            // Trust decisions must remain fail-closed even if error reporting fails.
        }
    }
}
