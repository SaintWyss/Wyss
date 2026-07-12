package ar.wyss.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class PairingPayloadTest {
    @Test
    fun validPayloadParsesFields() {
        val payload = PairingPayload.parse(
            """{"v":1,"url":"https://192.168.1.10:7777","fp":"AA:BB","token":"secret"}""",
        )

        assertNotNull(payload)
        assertEquals("https://192.168.1.10:7777", payload?.url)
        assertEquals("AA:BB", payload?.fp)
        assertEquals("secret", payload?.token)
    }

    @Test
    fun rejectsInvalidVersion() {
        assertNull(PairingPayload.parse(validPayload().replace(""""v":1""", """"v":2""")))
    }

    @Test
    fun rejectsMissingVersion() {
        assertNull(PairingPayload.parse("""{"url":"https://192.168.1.10:7777","fp":"AA:BB","token":"secret"}"""))
    }

    @Test
    fun rejectsHttpUrl() {
        assertNull(PairingPayload.parse(validPayload(url = "http://192.168.1.10:7777")))
    }

    @Test
    fun rejectsPublicDomainHost() {
        assertNull(PairingPayload.parse(validPayload(url = "https://example.com:7777")))
    }

    @Test
    fun rejectsPublicIpHost() {
        assertNull(PairingPayload.parse(validPayload(url = "https://8.8.8.8:7777")))
    }

    @Test
    fun rejects172OutsidePrivateRange() {
        assertNull(PairingPayload.parse(validPayload(url = "https://172.32.0.1:7777")))
    }

    @Test
    fun rejectsBlankFingerprint() {
        assertNull(PairingPayload.parse(validPayload(fp = "")))
    }

    @Test
    fun rejectsMissingToken() {
        assertNull(PairingPayload.parse("""{"v":1,"url":"https://192.168.1.10:7777","fp":"AA:BB"}"""))
    }

    @Test
    fun rejectsBrokenJson() {
        assertNull(PairingPayload.parse("""{"v":1,"url":"""))
    }

    @Test
    fun acceptsPrivateRanges() {
        assertNotNull(PairingPayload.parse(validPayload(url = "https://172.16.0.1:7777")))
        assertNotNull(PairingPayload.parse(validPayload(url = "https://10.0.0.1:7777")))
        assertNotNull(PairingPayload.parse(validPayload(url = "https://192.168.1.1:7777")))
    }

    private fun validPayload(
        url: String = "https://192.168.1.10:7777",
        fp: String = "AA:BB",
        token: String = "secret",
    ): String = """{"v":1,"url":"$url","fp":"$fp","token":"$token"}"""
}
