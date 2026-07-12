package ar.wyss.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FingerprintMatcherTest {
    private val cert = byteArrayOf(1, 2, 3, 4, 5)
    private val otherCert = byteArrayOf(1, 2, 3, 4, 6)

    @Test
    fun sameCertMatchesPinnedFingerprint() {
        val fp = FingerprintMatcher.sha256Fingerprint(cert)

        assertTrue(FingerprintMatcher.matches(cert, fp))
    }

    @Test
    fun differentCertDoesNotMatch() {
        val fp = FingerprintMatcher.sha256Fingerprint(cert)

        assertFalse(FingerprintMatcher.matches(otherCert, fp))
    }

    @Test
    fun nullOrBlankPinnedFingerprintDoesNotMatch() {
        assertFalse(FingerprintMatcher.matches(cert, null))
        assertFalse(FingerprintMatcher.matches(cert, ""))
        assertFalse(FingerprintMatcher.matches(cert, "   "))
    }

    @Test
    fun pinnedPrefixDoesNotMatch() {
        val fp = FingerprintMatcher.sha256Fingerprint(cert)

        assertFalse(FingerprintMatcher.matches(cert, fp.substring(0, 20)))
    }

    @Test
    fun fingerprintComparisonIsCaseInsensitive() {
        val fp = FingerprintMatcher.sha256Fingerprint(cert).lowercase()

        assertTrue(FingerprintMatcher.matches(cert, fp))
    }
}
