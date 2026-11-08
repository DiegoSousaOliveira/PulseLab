package br.pulselab.batimentos.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.ParcelUuid
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Uma placa encontrada na busca. */
data class PlacaEncontrada(val nome: String, val endereco: String, val rssi: Int)

/** Em que ponto está a conexão (a tela mostra isso na "pílula" de status). */
sealed interface EstadoConexao {
    data object Desconectado : EstadoConexao
    data object Procurando : EstadoConexao
    data class Conectando(val nome: String) : EstadoConexao
    data class Conectado(val nome: String) : EstadoConexao
    data class Reconectando(val tentativa: Int, val maximo: Int) : EstadoConexao
    data class Erro(val mensagem: String) : EstadoConexao
}

/**
 * Fala com a placa pelo Bluetooth Low Energy (BLE).
 *
 * Passos de uma conexão:
 *  1. procurar() -> o celular "escuta" os anúncios e lista as placas Batimentos-XXXX;
 *  2. conectar() -> conecta no servidor GATT da placa;
 *  3. descobre o serviço e LIGA AS NOTIFICAÇÕES de ESTADO e ONDA (escrevendo
 *     no descritor CCCD de cada uma);
 *  4. lê o ESTADO uma vez, para a tela não ficar vazia até a próxima notificação.
 *
 * O Android só aceita UMA operação GATT por vez (escrever, ler...). Por isso
 * cada passo só começa na resposta (callback) do anterior.
 *
 * As funções que usam Bluetooth precisam das permissões BLUETOOTH_SCAN e
 * BLUETOOTH_CONNECT (Android 12+) ou da localização (Android 8 a 11). A tela
 * pede essas permissões ANTES de chamar procurar(); por isso o aviso
 * "MissingPermission" é suprimido aqui.
 */
@SuppressLint("MissingPermission")
class ConexaoBle(
    context: Context,
    private val escopo: CoroutineScope,
    private val aoReceberEstado: (Leitura) -> Unit,
    private val aoReceberOnda: (List<Int>) -> Unit,
) {
    private val app = context.applicationContext
    private val adaptador = (app.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter

    private val _estado = MutableStateFlow<EstadoConexao>(EstadoConexao.Desconectado)
    val estado: StateFlow<EstadoConexao> = _estado.asStateFlow()

    private val _placas = MutableStateFlow<List<PlacaEncontrada>>(emptyList())
    val placas: StateFlow<List<PlacaEncontrada>> = _placas.asStateFlow()

    private var gatt: BluetoothGatt? = null
    private var dispositivo: BluetoothDevice? = null
    private var querConectado = false
    private var buscaJob: Job? = null
    private var reconexaoJob: Job? = null

    val bluetoothLigado: Boolean get() = adaptador?.isEnabled == true

    // ------------------------------------------------------------------ busca
    private val callbackBusca = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val nome = result.scanRecord?.deviceName ?: result.device.name ?: return
            val temServico = result.scanRecord?.serviceUuids?.contains(ParcelUuid(Protocolo.SERVICO)) == true
            if (!nome.startsWith(Protocolo.PREFIXO_NOME) && !temServico) return
            val placa = PlacaEncontrada(nome, result.device.address, result.rssi)
            _placas.update { lista -> (lista.filter { it.endereco != placa.endereco } + placa).sortedBy { it.nome } }
        }

        override fun onScanFailed(errorCode: Int) {
            _estado.value = EstadoConexao.Erro("A busca falhou (código $errorCode)")
        }
    }

    /** Procura placas por [segundos] segundos. As encontradas aparecem em [placas]. */
    fun procurar(segundos: Long = 10) {
        val scanner = adaptador?.bluetoothLeScanner ?: run {
            _estado.value = EstadoConexao.Erro("Bluetooth desligado")
            return
        }
        pararBusca()
        _placas.value = emptyList()
        _estado.value = EstadoConexao.Procurando
        // LOW_LATENCY = busca "ativa": o celular pede a resposta de scan, onde
        // a placa coloca o UUID do serviço.
        val ajustes = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanner.startScan(null, ajustes, callbackBusca)
        buscaJob = escopo.launch {
            delay(segundos * 1000)
            pararBusca()
            if (_estado.value == EstadoConexao.Procurando) {
                _estado.value = if (_placas.value.isEmpty())
                    EstadoConexao.Erro("Nenhuma placa encontrada")
                else EstadoConexao.Desconectado
            }
        }
    }

    fun pararBusca() {
        buscaJob?.cancel()
        buscaJob = null
        if (bluetoothLigado) runCatching { adaptador?.bluetoothLeScanner?.stopScan(callbackBusca) }
    }

    // ---------------------------------------------------------------- conexão
    fun conectar(placa: PlacaEncontrada) {
        pararBusca()
        reconexaoJob?.cancel()
        querConectado = true
        dispositivo = adaptador?.getRemoteDevice(placa.endereco)
        abrirGatt()
    }

    private fun abrirGatt() {
        val d = dispositivo ?: return
        _estado.value = EstadoConexao.Conectando(d.name ?: Protocolo.PREFIXO_NOME)
        gatt?.close()
        // O Android 37 criou um connectGatt novo (BluetoothGattConnectionSettings),
        // mas ele só existe nessa versão. Este funciona do Android 8 em diante.
        @Suppress("DEPRECATION")
        gatt = d.connectGatt(app, false, callbackGatt, BluetoothDevice.TRANSPORT_LE)
    }

    fun desconectar() {
        querConectado = false
        reconexaoJob?.cancel()
        pararBusca()
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        _estado.value = EstadoConexao.Desconectado
    }

    /** Conexão caiu sem o usuário pedir: tenta voltar algumas vezes (como a página web). */
    private fun tentarReconectar() {
        reconexaoJob?.cancel()
        reconexaoJob = escopo.launch {
            for (tentativa in 1..TENTATIVAS) {
                _estado.value = EstadoConexao.Reconectando(tentativa, TENTATIVAS)
                delay(1500)
                if (!querConectado) return@launch
                abrirGatt()
                delay(6000)          // tempo para conectar e ligar as notificações
                if (_estado.value is EstadoConexao.Conectado || !querConectado) return@launch
            }
            querConectado = false
            gatt?.close()
            gatt = null
            _estado.value = EstadoConexao.Erro("Conexão perdida")
        }
    }

    // ------------------------------------------------------------ callbacks GATT
    private val callbackGatt = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, novoEstado: Int) {
            if (novoEstado == BluetoothProfile.STATE_CONNECTED) {
                // Intervalo de conexão curto = dados chegam com menos atraso.
                g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                g.discoverServices()
            } else if (novoEstado == BluetoothProfile.STATE_DISCONNECTED) {
                g.close()
                if (gatt == g) gatt = null
                if (querConectado) {
                    if (reconexaoJob?.isActive != true) tentarReconectar()
                } else {
                    _estado.value = EstadoConexao.Desconectado
                }
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            val servico = g.getService(Protocolo.SERVICO)
            if (servico == null) {
                _estado.value = EstadoConexao.Erro("Esta placa não tem o serviço do Monitor")
                g.disconnect()
                return
            }
            ligarNotificacoes(g, servico.getCharacteristic(Protocolo.ESTADO))   // passo 1 de 3
        }

        override fun onDescriptorWrite(g: BluetoothGatt, descritor: BluetoothGattDescriptor, status: Int) {
            val servico = g.getService(Protocolo.SERVICO) ?: return
            when (descritor.characteristic.uuid) {
                Protocolo.ESTADO -> ligarNotificacoes(g, servico.getCharacteristic(Protocolo.ONDA))   // passo 2
                Protocolo.ONDA -> g.readCharacteristic(servico.getCharacteristic(Protocolo.ESTADO))  // passo 3
            }
        }

        // Android 13+ entrega o valor junto; versões antigas usam characteristic.value.
        override fun onCharacteristicRead(
            g: BluetoothGatt, c: BluetoothGattCharacteristic, valor: ByteArray, status: Int,
        ) = leituraConcluida(g, c, valor)

        @Deprecated("Usado só até o Android 12")
        override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                @Suppress("DEPRECATION")
                leituraConcluida(g, c, c.value ?: return)
            }
        }

        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, valor: ByteArray) =
            tratar(c.uuid, valor)

        @Deprecated("Usado só até o Android 12")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
                @Suppress("DEPRECATION")
                tratar(c.uuid, c.value ?: return)
            }
        }
    }

    private fun leituraConcluida(g: BluetoothGatt, c: BluetoothGattCharacteristic, valor: ByteArray) {
        tratar(c.uuid, valor)
        reconexaoJob?.cancel()
        _estado.value = EstadoConexao.Conectado(g.device.name ?: Protocolo.PREFIXO_NOME)
    }

    private fun tratar(uuid: java.util.UUID, valor: ByteArray) {
        when (uuid) {
            Protocolo.ESTADO -> Protocolo.lerEstado(valor)?.let(aoReceberEstado)
            Protocolo.ONDA -> Protocolo.lerOnda(valor).takeIf { it.isNotEmpty() }?.let(aoReceberOnda)
        }
    }

    /** Liga as notificações: avisa o Android e escreve 0x0001 no descritor CCCD da placa. */
    private fun ligarNotificacoes(g: BluetoothGatt, c: BluetoothGattCharacteristic?) {
        if (c == null) return
        g.setCharacteristicNotification(c, true)
        val descritor = c.getDescriptor(Protocolo.CCCD) ?: return
        val valor = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            g.writeDescriptor(descritor, valor)
        } else {
            @Suppress("DEPRECATION")
            descritor.value = valor
            @Suppress("DEPRECATION")
            g.writeDescriptor(descritor)
        }
    }

    fun encerrar() {
        desconectar()
    }

    private companion object {
        const val TENTATIVAS = 5
    }
}
