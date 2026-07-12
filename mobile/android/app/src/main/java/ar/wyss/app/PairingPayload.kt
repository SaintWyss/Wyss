package ar.wyss.app

import java.net.URI
import org.json.JSONObject

data class PairingPayload(
    val url: String,
    val fp: String,
    val token: String,
) {
    companion object {
        fun parse(json: String): PairingPayload? {
            return try {
                val obj = JSONObject(json)
                val version = obj.opt("v")
                if (version !is Int || version != 1) {
                    return null
                }

                val url = obj.requiredNonBlankString("url") ?: return null
                val fp = obj.requiredNonBlankString("fp") ?: return null
                val token = obj.requiredNonBlankString("token") ?: return null

                if (!isAllowedLanHttpsUrl(url)) {
                    return null
                }

                PairingPayload(url = url, fp = fp, token = token)
            } catch (_: Exception) {
                null
            }
        }

        private fun JSONObject.requiredNonBlankString(name: String): String? {
            if (!has(name)) {
                return null
            }

            val value = opt(name)
            if (value !is String || value.isBlank()) {
                return null
            }

            return value
        }

        private fun isAllowedLanHttpsUrl(url: String): Boolean {
            val uri = URI(url)
            if (!uri.scheme.equals("https", ignoreCase = true)) {
                return false
            }

            val host = uri.host ?: return false
            return isRfc1918Ip(host)
        }

        private fun isRfc1918Ip(host: String): Boolean {
            val octets = host.split('.')
            if (octets.size != 4) {
                return false
            }

            val values = octets.map { octet ->
                if (octet.isEmpty() || octet.length > 3 || octet.any { !it.isDigit() }) {
                    return false
                }
                octet.toIntOrNull()?.takeIf { it in 0..255 } ?: return false
            }

            return values[0] == 10 ||
                (values[0] == 172 && values[1] in 16..31) ||
                (values[0] == 192 && values[1] == 168)
        }
    }
}
