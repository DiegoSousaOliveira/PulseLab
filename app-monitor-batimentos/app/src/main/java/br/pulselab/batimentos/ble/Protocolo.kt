package br.pulselab.batimentos.ble

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

/**
 * Formato dos dados que a placa envia por Bluetooth Low Energy.
 *
 * É o MESMO protocolo de `monitor-batimentos/lib/painel_ble.py` (placa) e de
 * `monitor-batimentos/web/index.html` (página). Se mudar lá, mude aqui também.
 *
 * Dois canais ("características") dentro de um serviço:
 *
 *  ESTADO (16 bytes, little-endian):
 *   0 versão | 1 situação | 2 flags | 3 BPM | 4 SpO2 | 5 progresso (0-255)
 *   6 contador de batidas (0-255, dá a volta) | 7 fase do desafio
 *   8 repouso | 9 pico | 10 alvo | 11-12 tempo (décimos de s)
 *   13-14 recuperação (décimos de s; 0xFFFF = não voltou) | 15 sequência
 *
 *  ONDA (até 18 bytes): 0 sequência | 1 n | n pontos int16 (little-endian)
 *
 * Este arquivo é Kotlin puro (não usa nada do Android): por isso dá para
 * testá-lo no computador (veja app/src/test).
 */
object Protocolo {
    val SERVICO: UUID = UUID.fromString("448e804d-b3e1-4c80-89f5-91c53751f51a")
    val ESTADO: UUID = UUID.fromString("114b64c2-3004-4c6f-8311-1dbaa117286e")
    val ONDA: UUID = UUID.fromString("ab2cad3c-87af-494c-9f9f-62b21297da07")

    /** Descritor padrão do BLE que liga/desliga as notificações. */
    val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    const val PREFIXO_NOME = "Batimentos"
    const val TAMANHO_ESTADO = 16
    const val VERSAO = 1
    private const val SEM_VALOR = 0xFFFF

    /** Converte o pacote ESTADO em [Leitura]. Devolve null se o pacote for inválido. */
    fun lerEstado(dados: ByteArray): Leitura? {
        if (dados.size < TAMANHO_ESTADO) return null
        val b = ByteBuffer.wrap(dados).order(ByteOrder.LITTLE_ENDIAN)
        fun u8(i: Int) = dados[i].toInt() and 0xFF
        fun u16(i: Int) = b.getShort(i).toInt() and 0xFFFF

        val flags = u8(2)
        val fase = FaseDesafio.doCodigo(u8(7))
        val recuperacao = u16(13)
        return Leitura(
            versao = u8(0),
            situacao = SituacaoLeitura.entries.getOrElse(u8(1)) { SituacaoLeitura.SEM_DEDO },
            estavel = flags and 1 != 0,
            spo2Presumido = flags and 2 != 0,
            somLigado = flags and 4 != 0,
            bpm = u8(3),
            spo2 = u8(4),
            progresso = u8(5) / 255f,
            batidas = u8(6),
            desafio = fase?.let {
                Desafio(
                    fase = it,
                    repouso = u8(8),
                    pico = u8(9),
                    alvo = u8(10),
                    tempoS = u16(11) / 10f,
                    recuperacaoS = if (recuperacao == SEM_VALOR) null else recuperacao / 10f,
                )
            },
            sequencia = u8(15),
        )
    }

    /** Converte o pacote ONDA na lista de pontos (vazia se inválido). */
    fun lerOnda(dados: ByteArray): List<Int> {
        if (dados.size < 2) return emptyList()
        val n = dados[1].toInt() and 0xFF
        if (dados.size < 2 + 2 * n) return emptyList()
        val b = ByteBuffer.wrap(dados).order(ByteOrder.LITTLE_ENDIAN)
        return List(n) { i -> b.getShort(2 + 2 * i).toInt() }
    }
}

/** A ordem segue os códigos enviados pela placa (0, 1, 2, 3). */
enum class SituacaoLeitura { SEM_SENSOR, SEM_DEDO, ESTABILIZANDO, PRONTO }

enum class FaseDesafio(val codigo: Int) {
    REPOUSO_ESPERA(1),   // esperando dedo + primeiro BPM
    REPOUSO(2),          // contando os 15 s de repouso
    EXERCICIO(3),        // contagem do exercício
    VOLTA(4),            // esperando o dedo voltar
    RECUPERACAO(5),      // acompanhando a volta ao repouso
    RESULTADO(6);

    companion object {
        fun doCodigo(codigo: Int) = entries.firstOrNull { it.codigo == codigo }
    }
}

data class Desafio(
    val fase: FaseDesafio,
    val repouso: Int,
    val pico: Int,
    val alvo: Int,
    /** Fases REPOUSO/EXERCICIO: tempo que FALTA. Fases VOLTA/RECUPERACAO: tempo desde o exercício. */
    val tempoS: Float,
    /** null = não voltou perto do repouso em 3 minutos. */
    val recuperacaoS: Float?,
)

data class Leitura(
    val versao: Int,
    val situacao: SituacaoLeitura,
    val estavel: Boolean,
    val spo2Presumido: Boolean,
    val somLigado: Boolean,
    val bpm: Int,
    val spo2: Int,
    val progresso: Float,
    /** Contador de 0 a 255 que dá a volta: qualquer mudança = batida nova. */
    val batidas: Int,
    val desafio: Desafio?,
    val sequencia: Int,
)
