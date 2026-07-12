package ar.wyss.app

import android.content.Context
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONObject

@CapacitorPlugin(name = "Pairing")
class PairingPlugin : Plugin() {
    @PluginMethod
    fun completePairing(call: PluginCall) {
        val payload = call.getString("payload")?.let { PairingPayload.parse(it) }
        if (payload == null) {
            call.reject("QR inválido: esperaba {v:1, url https LAN, fp, token}")
            return
        }

        pairingPrefs()
            .edit()
            .putString(KEY_URL, payload.url)
            .putString(KEY_FP, payload.fp)
            .putString(KEY_TOKEN, payload.token)
            .remove(KEY_LAST_ERROR)
            .apply()

        installPinnedClient(payload.fp)
        activity.runOnUiThread {
            bridge.webView.loadUrl(remoteUrl(payload.url, payload.token))
        }
        call.resolve()
    }

    @PluginMethod
    fun pairingState(call: PluginCall) {
        call.resolve(JSObject().put("paired", hasPairing()))
    }

    @PluginMethod
    fun clearPairing(call: PluginCall) {
        pairingPrefs().edit().clear().apply()
        call.resolve()
    }

    @PluginMethod
    fun lastError(call: PluginCall) {
        val prefs = pairingPrefs()
        val error = prefs.getString(KEY_LAST_ERROR, null)
        prefs.edit().remove(KEY_LAST_ERROR).apply()
        call.resolve(JSObject().put("error", error ?: JSONObject.NULL))
    }

    private fun installPinnedClient(fp: String) {
        bridge.setWebViewClient(
            PinnedWebViewClient(bridge, fp) { code ->
                handleTrustFailure(code)
            },
        )
    }

    private fun handleTrustFailure(code: String) {
        pairingPrefs().edit().putString(KEY_LAST_ERROR, code).apply()
        activity.runOnUiThread {
            bridge.webView.loadUrl("${bridge.appUrl}#error=$code")
        }
    }

    private fun hasPairing(): Boolean {
        val prefs = pairingPrefs()
        return !prefs.getString(KEY_URL, null).isNullOrBlank() &&
            !prefs.getString(KEY_FP, null).isNullOrBlank() &&
            !prefs.getString(KEY_TOKEN, null).isNullOrBlank()
    }

    private fun pairingPrefs() =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    companion object {
        const val PREFS_NAME = "wyss_pairing"
        const val KEY_URL = "url"
        const val KEY_FP = "fp"
        const val KEY_TOKEN = "token"
        const val KEY_LAST_ERROR = "last_error"

        fun remoteUrl(url: String, token: String): String = "$url/?token=$token"
    }
}
