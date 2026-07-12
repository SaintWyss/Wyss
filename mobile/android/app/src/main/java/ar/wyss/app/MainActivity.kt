package ar.wyss.app

import android.content.Context
import android.os.Bundle
import com.getcapacitor.BridgeActivity

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(PairingPlugin::class.java)
        super.onCreate(savedInstanceState)

        val currentBridge = bridge ?: return
        val prefs = getSharedPreferences(PairingPlugin.PREFS_NAME, Context.MODE_PRIVATE)
        val url = prefs.getString(PairingPlugin.KEY_URL, null)
        val fp = prefs.getString(PairingPlugin.KEY_FP, null)
        val token = prefs.getString(PairingPlugin.KEY_TOKEN, null)

        if (url.isNullOrBlank() || fp.isNullOrBlank() || token.isNullOrBlank()) {
            return
        }

        currentBridge.setWebViewClient(
            PinnedWebViewClient(currentBridge, fp) { code ->
                prefs.edit().putString(PairingPlugin.KEY_LAST_ERROR, code).apply()
                runOnUiThread {
                    currentBridge.webView.loadUrl("${currentBridge.appUrl}#error=$code")
                }
            },
        )
        currentBridge.webView.post {
            currentBridge.webView.loadUrl(PairingPlugin.remoteUrl(url, token))
        }
    }
}
