package br.pulselab.batimentos.ui

import android.os.Build
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.pulselab.batimentos.MonitorViewModel
import br.pulselab.batimentos.ble.EstadoConexao
import br.pulselab.batimentos.ble.Leitura
import br.pulselab.batimentos.ble.PlacaEncontrada
import br.pulselab.batimentos.ble.SituacaoLeitura
import kotlinx.coroutines.delay

/** Como está a leitura, em palavras e cor (usado no chip do anel e no cartão "Sinal"). */
private data class Situacao(
    val titulo: String, val chip: String, val detalhe: String, val cor: Color,
    val progresso: Float?, val piscando: Boolean,
)

private fun situacao(semConexao: Boolean, semDados: Boolean, l: Leitura?): Situacao = when {
    semConexao -> Situacao("Offline", "Aguardando conexão", "Conecte-se à placa", Cores.Texto3, null, false)
    semDados -> Situacao("Sem dados", "Sem dados da placa", "Nada chega há mais de 3 s", Cores.Bpm, null, true)
    l == null -> Situacao("Conectado", "Conectado", "Aguardando a placa", Cores.Ok, null, false)
    l.situacao == SituacaoLeitura.SEM_SENSOR ->
        Situacao("Sem sensor", "Sensor não encontrado", "Confira o cabo da placa", Cores.Bpm, null, true)
    l.situacao == SituacaoLeitura.SEM_DEDO ->
        Situacao("Sem dedo", "Coloque o dedo no sensor", "Apoie o dedo sem apertar", Cores.Texto2, null, false)
    l.estavel -> Situacao("Estável", "Leitura estável", "Intervalos regulares", Cores.Ok, null, false)
    else -> {
        val pct = (l.progresso * 100).toInt()
        Situacao("Medindo", "Medindo… $pct%", "Juntando batidas · $pct%", Cores.Medindo, l.progresso, true)
    }
}

/** Linha de status da conexão (embaixo do nome do app). */
private fun linhaConexao(c: EstadoConexao, demonstracao: Boolean): Pair<String, Color> = when {
    demonstracao -> "Modo demonstração" to Cores.Medindo
    c is EstadoConexao.Procurando -> "Procurando placas…" to Cores.Medindo
    c is EstadoConexao.Conectando -> "Conectando a ${c.nome}…" to Cores.Medindo
    c is EstadoConexao.Reconectando -> "Reconectando (${c.tentativa}/${c.maximo})…" to Cores.Medindo
    c is EstadoConexao.Conectado -> c.nome to Cores.Ok          // a bolinha verde já diz "conectado"
    c is EstadoConexao.Erro -> c.mensagem to Cores.Bpm
    else -> "Desconectado" to Cores.Texto3
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PainelTela(
    vm: MonitorViewModel,
    conexao: EstadoConexao,
    leitura: Leitura?,
    onda: List<Int>,
    placas: List<PlacaEncontrada>,
    demonstracao: Boolean,
    ultimoPacoteMs: Long,
    mostrarSeletor: Boolean,
    aoFecharSeletor: () -> Unit,
    aoConectar: () -> Unit,
) {
    // Relógio de 1 s só para perceber "sem dados há mais de 3 s".
    var agora by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); agora = System.currentTimeMillis() } }

    // Pulso: acende (1) a cada batida e apaga em meio segundo. O coração e o anel usam.
    val pulso = remember { Animatable(0f) }
    var batidasAntes by remember { mutableStateOf<Int?>(null) }
    LaunchedEffect(leitura?.batidas) {
        val b = leitura?.batidas
        if (b != null && batidasAntes != null && b != batidasAntes) {
            pulso.snapTo(1f)
            pulso.animateTo(0f, tween(550))
        }
        batidasAntes = b
    }

    val conectado = conexao is EstadoConexao.Conectado
    val ocupado = conectado || conexao is EstadoConexao.Conectando || conexao is EstadoConexao.Reconectando
    val semConexao = !conectado && !demonstracao
    val semDados = conectado && !demonstracao && agora - ultimoPacoteMs > 3000
    val sit = situacao(semConexao, semDados, if (semConexao) null else leitura)
    val bpm = if (semConexao) 0 else leitura?.bpm ?: 0
    var menuAberto by remember { mutableStateOf(false) }
    var sobreAberto by remember { mutableStateOf(false) }

    BoxWithConstraints(
        Modifier
            .fillMaxSize()
            .background(Cores.FundoTela)
            .drawBehind {           // brilho rosado suave no alto da tela
                drawCircle(
                    Brush.radialGradient(listOf(Cores.Bpm.copy(alpha = 0.13f), Color.Transparent),
                        Offset(size.width * 0.5f, 0f), size.width * 0.9f),
                    size.width * 0.9f, Offset(size.width * 0.5f, 0f),
                )
            }
            .safeDrawingPadding()
            .padding(horizontal = 16.dp, vertical = 12.dp)
    ) {
        // Três arrumações: tablet (tudo numa tela), celular deitado (2 colunas com
        // rolagem) e celular em pé (1 coluna com rolagem).
        val largo = maxWidth >= 600.dp
        val fixo = largo && maxHeight >= 560.dp

        val topo: @Composable () -> Unit = {
            BarraTopo(
                conexao, demonstracao, ocupado,
                aoBotao = { if (ocupado) vm.desconectar() else aoConectar() },
                menuAberto = menuAberto, aoMenu = { menuAberto = it },
                aoDemo = { menuAberto = false; vm.alternarDemonstracao() },
                aoSobre = { menuAberto = false; sobreAberto = true },
            )
        }
        val heroi: @Composable (Modifier) -> Unit = { m ->
            CartaoHeroi(bpm, leitura, semConexao, sit, pulso.value, aoConectar, m)
        }
        val metricas: @Composable () -> Unit = {
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                CartaoSpo2(if (semConexao) 0 else leitura?.spo2 ?: 0, leitura?.spo2Presumido != false,
                    Modifier.weight(1f).fillMaxHeight())
                CartaoSinal(sit.titulo, sit.detalhe, sit.cor, sit.progresso, Modifier.weight(1f).fillMaxHeight())
            }
        }
        val desafio = if (semConexao) null else leitura?.desafio
        val aoVivo = !semConexao && !semDados && onda.isNotEmpty()

        when {
            fixo -> Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                topo()
                Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    heroi(Modifier.weight(1f).fillMaxHeight())
                    Column(Modifier.weight(1.2f).fillMaxHeight(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        metricas()
                        if (desafio != null) CartaoDesafio(desafio, Modifier.fillMaxWidth())
                        CartaoOnda(onda, aoVivo, preencher = true, Modifier.fillMaxWidth().weight(1f))
                        Rodape({ sobreAberto = true })
                    }
                }
            }
            largo -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                topo()
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    heroi(Modifier.weight(1f))
                    Column(Modifier.weight(1.2f), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        metricas()
                        if (desafio != null) CartaoDesafio(desafio, Modifier.fillMaxWidth())
                        CartaoOnda(onda, aoVivo, preencher = false, Modifier.fillMaxWidth())
                    }
                }
                Rodape({ sobreAberto = true })
            }
            else -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                topo()
                heroi(Modifier.fillMaxWidth())
                metricas()
                if (desafio != null) CartaoDesafio(desafio, Modifier.fillMaxWidth())
                CartaoOnda(onda, aoVivo, preencher = false, Modifier.fillMaxWidth())
                Rodape({ sobreAberto = true })
                Spacer(Modifier.height(4.dp))
            }
        }
    }

    if (mostrarSeletor) {
        SeletorPlaca(
            procurando = conexao is EstadoConexao.Procurando,
            placas = placas,
            aoEscolher = { placa -> aoFecharSeletor(); vm.conectar(placa) },
            aoProcurarDeNovo = { vm.procurar() },
            aoFechar = { vm.pararBusca(); aoFecharSeletor() },
        )
    }
    if (sobreAberto) DialogoSobre { sobreAberto = false }
}

// ---- Barra superior ----------------------------------------------------------
@Composable
private fun BarraTopo(
    conexao: EstadoConexao,
    demonstracao: Boolean,
    ocupado: Boolean,
    aoBotao: () -> Unit,
    menuAberto: Boolean,
    aoMenu: (Boolean) -> Unit,
    aoDemo: () -> Unit,
    aoSobre: () -> Unit,
) {
    val (linha, corLinha) = linhaConexao(conexao, demonstracao)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Logotipo(42.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            // Sobretítulo pequeno + nome em destaque: cabe até em telas de 360 dp.
            Text("MONITOR DE", style = Estilos.Rotulo, fontSize = 10.sp, lineHeight = 12.sp)
            Text("Batimentos", color = Cores.Texto, fontSize = 20.sp, fontWeight = FontWeight.Bold,
                maxLines = 1, lineHeight = 24.sp)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(corLinha))
                Spacer(Modifier.width(6.dp))
                Text(linha, color = Cores.Texto2, fontSize = 12.sp, maxLines = 1)
            }
        }
        // Botão redondo do Bluetooth: em degradê = conectar; contornado = desconectar.
        Box(
            Modifier
                .size(42.dp)
                .clip(CircleShape)
                .then(
                    if (ocupado) Modifier.background(Cores.Cartao).border(1.dp, Cores.Spo2.copy(alpha = 0.45f), CircleShape)
                    else Modifier.background(Cores.Marca)
                )
                .clickable(onClick = aoBotao),
            contentAlignment = Alignment.Center,
        ) {
            Icone(Icones.Bluetooth, if (ocupado) Cores.Spo2 else Color.White, 19.dp, contorno = true, espessura = 2.3f)
        }
        Box {
            Box(
                Modifier.padding(start = 4.dp).size(40.dp).clip(CircleShape).clickable { aoMenu(true) },
                contentAlignment = Alignment.Center,
            ) { IconeMenu(Cores.Texto2) }
            DropdownMenu(expanded = menuAberto, onDismissRequest = { aoMenu(false) },
                containerColor = Cores.CartaoClaro, shape = RoundedCornerShape(14.dp)) {
                DropdownMenuItem(
                    text = { Text(if (demonstracao) "Sair do modo demonstração" else "Modo demonstração") },
                    leadingIcon = { Icone(Icones.Pulso, Cores.Medindo, 18.dp, contorno = true) },
                    onClick = aoDemo,
                )
                DropdownMenuItem(
                    text = { Text("Sobre o projeto") },
                    leadingIcon = { Icone(Icones.Info, Cores.Texto2, 18.dp, contorno = true) },
                    onClick = aoSobre,
                )
            }
        }
    }
}

// ---- Cartão principal: o anel do BPM ---------------------------------------------
@Composable
private fun CartaoHeroi(
    bpm: Int, leitura: Leitura?, semConexao: Boolean, sit: Situacao, pulso: Float,
    aoConectar: () -> Unit, modifier: Modifier,
) {
    val medindo = !semConexao && leitura != null && (leitura.situacao == SituacaoLeitura.ESTABILIZANDO ||
        (leitura.situacao == SituacaoLeitura.PRONTO && !leitura.estavel))
    Superficie(modifier, preenchimento = 20) {
        TituloSecao("Frequência cardíaca", Icones.Coracao, Cores.Bpm, contorno = false)
        AnelBpm(
            bpm = bpm, medindo = medindo, progresso = leitura?.progresso ?: 0f, pulso = pulso,
            modifier = Modifier.fillMaxWidth(0.86f).widthIn(max = 340.dp).align(Alignment.CenterHorizontally),
        ) {
            BoxWithConstraints(contentAlignment = Alignment.Center) {
                CentroAnel(bpm, leitura, semConexao, pulso, maxWidth.value)
            }
        }
        if (semConexao) {
            Row(
                Modifier
                    .align(Alignment.CenterHorizontally)
                    .clip(CircleShape)
                    .background(Cores.Marca)
                    .clickable(onClick = aoConectar)
                    .padding(horizontal = 24.dp, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icone(Icones.Bluetooth, Color.White, 18.dp, contorno = true, espessura = 2.4f)
                Spacer(Modifier.width(10.dp))
                Text("Conectar à placa", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
        } else {
            ChipStatus(sit.chip, sit.cor, sit.piscando, Modifier.align(Alignment.CenterHorizontally))
        }
        Spacer(Modifier.height(2.dp))
        BarraFaixas(bpm)
        Text(textoFaixa(bpm), color = if (bpm > 0) corFaixa(bpm) else Cores.Texto3, fontSize = 12.sp,
            fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun CentroAnel(bpm: Int, leitura: Leitura?, semConexao: Boolean, pulso: Float, lado: Float) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        when {
            semConexao -> {
                Box(Modifier.size(56.dp).clip(CircleShape).background(Cores.Spo2.copy(alpha = 0.12f)),
                    contentAlignment = Alignment.Center) {
                    Icone(Icones.Bluetooth, Cores.Spo2, 26.dp, contorno = true, espessura = 2.2f)
                }
                Spacer(Modifier.height(12.dp))
                Text("Sem conexão", color = Cores.Texto, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("nenhuma placa conectada", color = Cores.Texto3, fontSize = 13.sp)
            }
            leitura?.situacao == SituacaoLeitura.SEM_SENSOR -> {
                Icone(Icones.Info, Cores.Bpm, 40.dp, contorno = true)
                Spacer(Modifier.height(10.dp))
                Text("Sensor não\nencontrado", color = Cores.Texto, fontSize = 18.sp, fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center)
            }
            leitura == null || leitura.situacao == SituacaoLeitura.SEM_DEDO -> {
                Icone(Icones.Dedo, Cores.Texto2, 44.dp, contorno = true, espessura = 1.6f)
                Spacer(Modifier.height(10.dp))
                Text("Coloque o dedo", color = Cores.Texto, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                Text("só encostado, sem apertar", color = Cores.Texto3, fontSize = 13.sp)
            }
            bpm <= 0 -> {
                Text("MEDINDO", style = Estilos.Rotulo, color = Cores.Medindo)
                Text("${(leitura.progresso * 100).toInt()}%", style = Estilos.Numero,
                    fontSize = (lado * 0.2f).sp, color = Cores.Texto, lineHeight = (lado * 0.22f).sp)
                Text("fique parado", color = Cores.Texto3, fontSize = 13.sp)
            }
            else -> {
                Icone(Icones.Coracao, Cores.Bpm, 26.dp,
                    modifier = Modifier.graphicsLayer { val e = 1f + 0.22f * pulso; scaleX = e; scaleY = e })
                Text(bpm.toString(), style = Estilos.Numero, fontSize = (lado * 0.3f).sp,
                    color = Cores.Texto, lineHeight = (lado * 0.32f).sp)
                Text("BPM", style = Estilos.Rotulo, fontSize = 13.sp, color = Cores.Texto2)
            }
        }
    }
}

// ---- Cartão da onda --------------------------------------------------------------
@Composable
private fun CartaoOnda(pontos: List<Int>, aoVivo: Boolean, preencher: Boolean, modifier: Modifier) {
    Superficie(modifier) {
        TituloSecao("Onda do pulso · PPG", Icones.Pulso, Cores.Bpm) {
            ChipStatus(if (aoVivo) "AO VIVO" else "PAUSADO", if (aoVivo) Cores.Bpm else Cores.Texto3, piscando = aoVivo)
        }
        val m = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Cores.FundoTopo.copy(alpha = 0.55f))
        MonitorOnda(pontos, MonitorViewModel.PONTOS_ONDA, if (preencher) m.weight(1f) else m.height(170.dp))
    }
}

// ---- Lista de placas -------------------------------------------------------------
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SeletorPlaca(
    procurando: Boolean,
    placas: List<PlacaEncontrada>,
    aoEscolher: (PlacaEncontrada) -> Unit,
    aoProcurarDeNovo: () -> Unit,
    aoFechar: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = aoFechar,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = Cores.Cartao,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconeEmBadge(Icones.Bluetooth, Cores.Spo2, contorno = true, tamanho = 40.dp)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Placas por perto", color = Cores.Texto, fontSize = 19.sp, fontWeight = FontWeight.Bold)
                    Text(if (procurando) "Procurando “Batimentos-XXXX”…" else "${placas.size} encontrada(s)",
                        color = Cores.Texto3, fontSize = 13.sp)
                }
            }
            if (procurando) {
                LinearProgressIndicator(Modifier.fillMaxWidth().clip(CircleShape), color = Cores.Spo2,
                    trackColor = Cores.Trilho)
            }
            if (placas.isEmpty() && !procurando) {
                Text("Nenhuma placa encontrada. Confira se ela está ligada e se nenhum outro aparelho " +
                    "(ou a página web) está conectado nela.", color = Cores.Texto2, fontSize = 14.sp)
                if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
                    Text("No Android 11 ou anterior, a Localização do celular também precisa estar ligada.",
                        color = Cores.Texto3, fontSize = 13.sp)
                }
            }
            placas.forEach { placa ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(16.dp))
                        .background(Cores.CartaoClaro)
                        .border(1.dp, Cores.Borda, RoundedCornerShape(16.dp))
                        .clickable { aoEscolher(placa) }
                        .padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Logotipo(38.dp)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(placa.nome, color = Cores.Texto, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        Text(placa.endereco, color = Cores.Texto3, fontSize = 12.sp)
                    }
                    IconeSinal(nivelSinal(placa.rssi), Cores.Ok)
                    Spacer(Modifier.width(10.dp))
                    Icone(Icones.Seta, Cores.Texto3, 18.dp, contorno = true)
                }
            }
            if (!procurando) {
                TextButton(onClick = aoProcurarDeNovo, modifier = Modifier.align(Alignment.CenterHorizontally)) {
                    Text("Procurar de novo", color = Cores.Spo2, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

private fun nivelSinal(rssi: Int) = when {
    rssi >= -55 -> 4
    rssi >= -67 -> 3
    rssi >= -80 -> 2
    else -> 1
}

@Composable
private fun DialogoSobre(aoFechar: () -> Unit) {
    AlertDialog(
        onDismissRequest = aoFechar,
        confirmButton = { TextButton(onClick = aoFechar) { Text("Entendi", color = Cores.BpmClaro) } },
        icon = { Logotipo(44.dp) },
        title = { Text("Monitor de Batimentos", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ItemSobre(Icones.Info, Cores.Medindo, "Projeto educacional",
                    "Não é aparelho médico. Os valores não servem para nenhuma decisão de saúde.")
                ItemSobre(Icones.Gota, Cores.Spo2, "SpO₂ com calibração presumida",
                    "Serve só para estudar o princípio de funcionamento de um oxímetro.", contorno = false)
                ItemSobre(Icones.Escudo, Cores.Ok, "Privacidade",
                    "Sem nome e sem gravação: as leituras chegam da placa por Bluetooth, ficam só na memória " +
                        "e somem ao fechar o app. O app nem tem permissão de internet.")
            }
        },
        containerColor = Cores.Cartao,
        titleContentColor = Cores.Texto,
        textContentColor = Cores.Texto2,
    )
}

@Composable
private fun ItemSobre(icone: Path, cor: Color, titulo: String, texto: String, contorno: Boolean = true) {
    Row {
        IconeEmBadge(icone, cor, contorno, 32.dp)
        Spacer(Modifier.width(12.dp))
        Column {
            Text(titulo, color = Cores.Texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(texto, color = Cores.Texto2, fontSize = 13.sp, lineHeight = 17.sp)
        }
    }
}
