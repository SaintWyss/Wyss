package ar.wyss.app

import java.security.MessageDigest

object FingerprintMatcher {
    private val hexDigits = "0123456789ABCDEF".toCharArray()

    fun sha256Fingerprint(der: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(der)
        val chars = CharArray(digest.size * 3 - 1)

        digest.forEachIndexed { index, byte ->
            val value = byte.toInt() and 0xff
            val offset = index * 3
            chars[offset] = hexDigits[value ushr 4]
            chars[offset + 1] = hexDigits[value and 0x0f]
            if (index < digest.lastIndex) {
                chars[offset + 2] = ':'
            }
        }

        return String(chars)
    }

    fun matches(presentedDer: ByteArray, pinnedFp: String?): Boolean {
        if (pinnedFp.isNullOrBlank()) {
            return false
        }

        return sha256Fingerprint(presentedDer).equals(pinnedFp, ignoreCase = true)
    }
}
