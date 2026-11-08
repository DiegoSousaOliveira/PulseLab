package br.pulselab.batimentos.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Testes do decodificador com pacotes montados pelo MESMO struct.pack da
 * placa (lib/painel_ble.py). Os mesmos bytes foram usados para validar a
 * página web/index.html.
 */
class ProtocoloTest {

    private fun hex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    // struct.pack('<BBBBBBBBBBBHHB', 1, 3, 1|2|4, 112, 97, 200, 17, 5, 68, 112, 75, 473, 0xFFFF, 9)
    private val estadoRecuperacao = hex("0103077061c8110544704bd901ffff09")

    // struct.pack('<BB8h', 3, 8, -700, -350, 0, 350, 700, 32767, -32767, 5)
    private val onda = hex("030844fda2fe00005e01bc02ff7f01800500")

    @Test
    fun estadoCompleto() {
        val l = Protocolo.lerEstado(estadoRecuperacao)!!
        assertEquals(1, l.versao)
        assertEquals(SituacaoLeitura.PRONTO, l.situacao)
        assertTrue(l.estavel && l.spo2Presumido && l.somLigado)
        assertEquals(112, l.bpm)
        assertEquals(97, l.spo2)
        assertEquals(200 / 255f, l.progresso, 1e-6f)
        assertEquals(17, l.batidas)
        assertEquals(9, l.sequencia)
        val d = l.desafio!!
        assertEquals(FaseDesafio.RECUPERACAO, d.fase)
        assertEquals(68, d.repouso)
        assertEquals(112, d.pico)
        assertEquals(75, d.alvo)
        assertEquals(47.3f, d.tempoS, 1e-4f)
        assertNull(d.recuperacaoS)            // 0xFFFF = não voltou
    }

    @Test
    fun semDesafioESemDedo() {
        // struct.pack('<BBBBBBBBBBBHHB', 1, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xFFFF, 200)
        val l = Protocolo.lerEstado(hex("01010200000000000000000000ffffc8"))!!
        assertEquals(SituacaoLeitura.SEM_DEDO, l.situacao)
        assertNull(l.desafio)
        assertEquals(200, l.sequencia)
    }

    @Test
    fun resultadoComRecuperacao() {
        // fase 6 (resultado), recuperação 85,0 s = 850 décimos
        val d = Protocolo.lerEstado(hex("01030770610000064470000000520300"))!!.desafio!!
        assertEquals(FaseDesafio.RESULTADO, d.fase)
        assertEquals(85.0f, d.recuperacaoS!!, 1e-4f)
    }

    @Test
    fun pacoteCurtoEInvalido() {
        assertNull(Protocolo.lerEstado(ByteArray(10)))
        assertEquals(emptyList<Int>(), Protocolo.lerOnda(byteArrayOf(1)))
        assertEquals(emptyList<Int>(), Protocolo.lerOnda(byteArrayOf(1, 8, 0, 0)))   // diz 8 pontos, só tem 1
    }

    @Test
    fun ondaComLimites() {
        assertEquals(listOf(-700, -350, 0, 350, 700, 32767, -32767, 5), Protocolo.lerOnda(onda))
    }
}
