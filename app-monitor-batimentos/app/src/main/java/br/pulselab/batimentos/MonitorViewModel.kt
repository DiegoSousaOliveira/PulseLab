package br.pulselab.batimentos

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.pulselab.batimentos.ble.ConexaoBle
import br.pulselab.batimentos.ble.Desafio
import br.pulselab.batimentos.ble.EstadoConexao
import br.pulselab.batimentos.ble.FaseDesafio
import br.pulselab.batimentos.ble.Leitura
import br.pulselab.batimentos.ble.PlacaEncontrada
import br.pulselab.batimentos.ble.SituacaoLeitura
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.exp
import kotlin.math.roundToInt
import kotlin.math.sin

/**
 * Guarda tudo o que a tela mostra e sobrevive à rotação do celular.
 *
 * PRIVACIDADE: as leituras ficam só na memória do app e somem ao fechá-lo.
 * Nada é gravado nem enviado para a internet (o app nem pede essa permissão).
 */
class MonitorViewModel(app: Application) : AndroidViewModel(app) {

    private val _leitura = MutableStateFlow<Leitura?>(null)
    val leitura: StateFlow<Leitura?> = _leitura.asStateFlow()

    /** Últimos pontos da onda (~5 s), do mais velho ao mais novo. */
    private val _onda = MutableStateFlow<List<Int>>(emptyList())
    val onda: StateFlow<List<Int>> = _onda.asStateFlow()

    private val _demonstracao = MutableStateFlow(false)
    val demonstracao: StateFlow<Boolean> = _demonstracao.asStateFlow()

    /** Hora (ms) do último pacote: sem pacote há 3 s com a conexão aberta = aviso. */
    private val _ultimoPacoteMs = MutableStateFlow(0L)
    val ultimoPacoteMs: StateFlow<Long> = _ultimoPacoteMs.asStateFlow()

    private val conexao = ConexaoBle(
        context = app,
        escopo = viewModelScope,
        aoReceberEstado = { receberEstado(it) },
        aoReceberOnda = { pontos -> adicionarOnda(pontos) },
    )
    val estadoConexao: StateFlow<EstadoConexao> = conexao.estado
    val placas: StateFlow<List<PlacaEncontrada>> = conexao.placas
    val bluetoothLigado: Boolean get() = conexao.bluetoothLigado

    private var demoJob: Job? = null

    fun procurar() {
        pararDemonstracao()
        conexao.procurar()
    }

    fun pararBusca() = conexao.pararBusca()

    fun conectar(placa: PlacaEncontrada) {
        limpar()
        conexao.conectar(placa)
    }

    fun desconectar() = conexao.desconectar()

    private fun receberEstado(l: Leitura) {
        _leitura.value = l
        _ultimoPacoteMs.value = System.currentTimeMillis()
        // Sem dedo, a placa para de mandar a onda: limpamos a tela.
        if (l.situacao != SituacaoLeitura.PRONTO && l.situacao != SituacaoLeitura.ESTABILIZANDO) {
            _onda.value = emptyList()
        }
    }

    private fun adicionarOnda(pontos: List<Int>) {
        _onda.update { (it + pontos).takeLast(PONTOS_ONDA) }
    }

    private fun limpar() {
        _leitura.value = null
        _onda.value = emptyList()
    }

    // ------------------------------------------------------- modo demonstração
    fun alternarDemonstracao() {
        if (_demonstracao.value) pararDemonstracao() else iniciarDemonstracao()
    }

    private fun pararDemonstracao() {
        demoJob?.cancel()
        if (_demonstracao.value) limpar()
        _demonstracao.value = false
    }

    /**
     * Simula a placa (sem Bluetooth), num ciclo de 60 s:
     * 0-25 s monitor; 25-45 s Desafio na recuperação; 45-60 s resultado.
     */
    private fun iniciarDemonstracao() {
        conexao.desconectar()
        limpar()
        _demonstracao.value = true
        demoJob = viewModelScope.launch {
            var t = 0.0
            var batidas = 0
            var proxima = 0.0
            while (isActive) {
                val ciclo = t % 60
                val bpmBase = when {
                    ciclo < 25 -> 72.0
                    ciclo < 45 -> 112.0 - (ciclo - 25) * 1.6    // voltando ao repouso
                    else -> 74.0
                }
                val bpm = (bpmBase + 3 * sin(t / 7)).roundToInt()
                if (t >= proxima) {
                    batidas = (batidas + 1) and 0xFF
                    proxima = t + 60.0 / bpm
                }
                val novos = List(3) { k ->        // ~30 pontos por segundo, como a placa
                    val f = ((t + k * 0.033) * bpm / 60) % 1
                    (400 * exp(-((f - 0.2) / 0.07).let { it * it }) +
                        140 * exp(-((f - 0.5) / 0.1).let { it * it })).roundToInt()
                }
                adicionarOnda(novos)
                val desafio = when {
                    ciclo < 25 -> null
                    ciclo < 45 -> Desafio(FaseDesafio.RECUPERACAO, 68, 112, 75, (ciclo - 25 + 12).toFloat(), null)
                    else -> Desafio(FaseDesafio.RESULTADO, 68, 112, 75, 0f, 32f)
                }
                _leitura.value = Leitura(
                    versao = 1, situacao = SituacaoLeitura.PRONTO,
                    estavel = t > 6, spo2Presumido = true, somLigado = true,
                    bpm = if (t > 4) bpm else 0, spo2 = if (t > 6) 97 else 0,
                    progresso = (t / 6).coerceAtMost(1.0).toFloat(), batidas = batidas,
                    desafio = desafio, sequencia = 0,
                )
                delay(100)
                t += 0.1
            }
        }
    }

    override fun onCleared() {
        conexao.encerrar()
    }

    companion object {
        const val PONTOS_ONDA = 128
    }
}
