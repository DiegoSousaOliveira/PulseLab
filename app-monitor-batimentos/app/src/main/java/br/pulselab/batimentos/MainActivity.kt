package br.pulselab.batimentos

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import br.pulselab.batimentos.ble.EstadoConexao
import br.pulselab.batimentos.ui.PainelTela
import br.pulselab.batimentos.ui.TemaMonitor

/**
 * Monitor de Batimentos - painel Android.
 * Projeto EDUCACIONAL: NÃO é aparelho médico.
 *
 * Conecta por Bluetooth Low Energy na placa BitDogLab (programa em
 * monitor-batimentos/) e mostra BPM, SpO2, a onda do pulso e o Desafio do Pátio.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Barras do sistema transparentes com ícones CLAROS (o app é sempre escuro).
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        setContent {
            TemaMonitor {
                App(viewModel())
            }
        }
    }
}

/** Permissões de Bluetooth: Android 12+ tem permissões próprias; antes, a busca exigia a Localização. */
private val PERMISSOES = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
    arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
else
    arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)

@Composable
private fun App(vm: MonitorViewModel) {
    val contexto = LocalContext.current
    val conexao by vm.estadoConexao.collectAsStateWithLifecycle()
    val leitura by vm.leitura.collectAsStateWithLifecycle()
    val onda by vm.onda.collectAsStateWithLifecycle()
    val placas by vm.placas.collectAsStateWithLifecycle()
    val demonstracao by vm.demonstracao.collectAsStateWithLifecycle()
    val ultimoPacote by vm.ultimoPacoteMs.collectAsStateWithLifecycle()
    var mostrarSeletor by remember { mutableStateOf(false) }

    // Tela sempre acesa enquanto mostra leituras (como um monitor de verdade).
    val view = LocalView.current
    val mantendoTela = demonstracao || conexao is EstadoConexao.Conectado
    DisposableEffect(mantendoTela) {
        view.keepScreenOn = mantendoTela
        onDispose { view.keepScreenOn = false }
    }

    fun avisar(texto: String) = Toast.makeText(contexto, texto, Toast.LENGTH_LONG).show()
    fun temPermissoes() = PERMISSOES.all {
        ContextCompat.checkSelfPermission(contexto, it) == PackageManager.PERMISSION_GRANTED
    }

    // Passo 3: Bluetooth ligado -> abre a lista e começa a procurar.
    fun procurar() {
        mostrarSeletor = true
        vm.procurar()
    }

    // Passo 2: pede para ligar o Bluetooth, se estiver desligado.
    val pedirParaLigar = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (vm.bluetoothLigado) procurar() else avisar("Ligue o Bluetooth para conectar à placa.")
    }

    fun continuar() {
        if (vm.bluetoothLigado) procurar()
        else pedirParaLigar.launch(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE))
    }

    // Passo 1: permissões.
    val pedirPermissoes = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { r ->
        if (r.values.all { it }) continuar()
        else avisar("Sem a permissão de Bluetooth o app não consegue encontrar a placa.")
    }

    PainelTela(
        vm = vm,
        conexao = conexao,
        leitura = leitura,
        onda = onda,
        placas = placas,
        demonstracao = demonstracao,
        ultimoPacoteMs = ultimoPacote,
        mostrarSeletor = mostrarSeletor,
        aoFecharSeletor = { mostrarSeletor = false },
        aoConectar = { if (temPermissoes()) continuar() else pedirPermissoes.launch(PERMISSOES) },
    )
}
