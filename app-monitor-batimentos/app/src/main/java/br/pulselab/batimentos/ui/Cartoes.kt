package br.pulselab.batimentos.ui

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.pulselab.batimentos.ble.Desafio
import br.pulselab.batimentos.ble.FaseDesafio
import kotlin.math.ceil
import kotlin.math.roundToInt

// ---- Blocos básicos ------------------------------------------------------
private val Formato = RoundedCornerShape(22.dp)

/** Cartão com fundo em degradê suave e borda fina. */
@Composable
fun Superficie(
    modifier: Modifier = Modifier,
    preenchimento: Int = 18,
    conteudo: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .clip(Formato)
            .background(Cores.Superficie)
            .border(1.dp, Cores.Borda, Formato)
            .padding(preenchimento.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = conteudo,
    )
}

/** Título de seção em caixa-alta, com ícone opcional e algo à direita. */
@Composable
fun TituloSecao(
    texto: String,
    icone: Path? = null,
    corIcone: Color = Cores.Texto3,
    contorno: Boolean = true,
    direita: (@Composable () -> Unit)? = null,
) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        if (icone != null) {
            Icone(icone, corIcone, 15.dp, contorno)
            Spacer(Modifier.width(8.dp))
        }
        Text(texto.uppercase(), style = Estilos.Rotulo, modifier = Modifier.weight(1f))
        direita?.invoke()
    }
}

/** Pílula colorida de status, com uma bolinha que pode "piscar". */
@Composable
fun ChipStatus(texto: String, cor: Color, piscando: Boolean = false, modifier: Modifier = Modifier) {
    val transicao = rememberInfiniteTransition(label = "chip")
    val brilho by transicao.animateFloat(
        1f, 0.25f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "bolinha",
    )
    Row(
        modifier
            .clip(CircleShape)
            .background(cor.copy(alpha = 0.12f))
            .border(1.dp, cor.copy(alpha = 0.28f), CircleShape)
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(7.dp).alpha(if (piscando) brilho else 1f).clip(CircleShape).background(cor))
        Spacer(Modifier.width(8.dp))
        Text(texto, color = cor, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ---- Métricas ------------------------------------------------------------
@Composable
fun CartaoSpo2(spo2: Int, presumido: Boolean, modifier: Modifier = Modifier) {
    Superficie(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconeEmBadge(Icones.Gota, Cores.Spo2)
            Spacer(Modifier.width(10.dp))
            Text("SpO₂", color = Cores.Texto2, fontSize = 15.sp, fontWeight = FontWeight.Medium)
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Text(if (spo2 > 0) spo2.toString() else "--", style = Estilos.Numero, fontSize = 44.sp,
                color = Cores.Spo2, lineHeight = 44.sp)
            Text("%", color = Cores.Texto2, fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(start = 3.dp, bottom = 6.dp))
        }
        MiniBarra(if (spo2 > 0) (spo2 - 70) / 30f else 0f, Cores.Spo2)
        Text(
            if (presumido) "Calibração presumida" else "Fórmula empírica",
            color = Cores.Texto3, fontSize = 11.sp, lineHeight = 14.sp,
        )
    }
}

@Composable
fun CartaoSinal(titulo: String, detalhe: String, cor: Color, progresso: Float?, modifier: Modifier = Modifier) {
    Superficie(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconeEmBadge(Icones.Pulso, cor, contorno = true)
            Spacer(Modifier.width(10.dp))
            Text("Sinal", color = Cores.Texto2, fontSize = 15.sp, fontWeight = FontWeight.Medium)
        }
        Text(titulo, color = cor, fontSize = 24.sp, fontWeight = FontWeight.Bold, lineHeight = 28.sp, maxLines = 1,
            modifier = Modifier.padding(top = 6.dp, bottom = 4.dp))
        MiniBarra(progresso ?: 1f, if (progresso == null) cor.copy(alpha = 0.5f) else cor)
        Text(detalhe, color = Cores.Texto3, fontSize = 11.sp, lineHeight = 14.sp)
    }
}

// ---- Desafio do Pátio -------------------------------------------------------
private fun tempo(segundos: Float): String {
    val s = segundos.roundToInt().coerceAtLeast(0)
    return "%d:%02d".format(s / 60, s % 60)
}

@Composable
private fun Etapas(atual: Int, modifier: Modifier = Modifier) {
    val nomes = listOf("Repouso", "Exercício", "Recuperação")
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        nomes.forEachIndexed { i, nome ->
            val n = i + 1
            val feito = n < atual
            val ativo = n == atual
            val cor = when {
                feito -> Cores.Ok
                ativo -> Cores.Bpm
                else -> Cores.Texto3
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Box(
                    Modifier
                        .size(30.dp)
                        .clip(CircleShape)
                        .background(if (ativo || feito) cor.copy(alpha = 0.18f) else Color.Transparent)
                        .border(1.5.dp, cor, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    if (feito) Icone(Icones.Certo, cor, 15.dp, contorno = true, espessura = 3f)
                    else Text("$n", color = cor, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.height(6.dp))
                Text(nome, color = if (ativo) Cores.Texto else Cores.Texto3, fontSize = 11.sp,
                    fontWeight = if (ativo) FontWeight.SemiBold else FontWeight.Normal)
            }
            if (i < nomes.lastIndex) {
                Box(
                    Modifier
                        .weight(1f)
                        .padding(horizontal = 6.dp)
                        .padding(bottom = 18.dp)
                        .height(2.dp)
                        .clip(CircleShape)
                        .background(if (n < atual) Cores.Ok else Cores.Trilho)
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CartaoDesafio(d: Desafio, modifier: Modifier = Modifier) {
    val etapa = when (d.fase) {
        FaseDesafio.REPOUSO_ESPERA, FaseDesafio.REPOUSO -> 1
        FaseDesafio.EXERCICIO -> 2
        FaseDesafio.VOLTA, FaseDesafio.RECUPERACAO -> 3
        FaseDesafio.RESULTADO -> 4
    }
    val instrucao = when (d.fase) {
        FaseDesafio.REPOUSO_ESPERA -> "Coloque o dedo no sensor e fique parado"
        FaseDesafio.REPOUSO -> "Medindo o repouso. Fique parado."
        FaseDesafio.EXERCICIO -> "Tire o dedo e pule no lugar!"
        FaseDesafio.VOLTA -> "Coloque o dedo no sensor de novo"
        FaseDesafio.RECUPERACAO -> "Acompanhando a volta ao repouso"
        FaseDesafio.RESULTADO -> "Desafio concluído"
    }
    // Cronômetro grande: tempo que falta (repouso/exercício) ou desde o exercício.
    val cronometro: Pair<String, String>? = when (d.fase) {
        FaseDesafio.REPOUSO, FaseDesafio.EXERCICIO -> "${ceil(d.tempoS).toInt()} s" to "faltam"
        FaseDesafio.VOLTA, FaseDesafio.RECUPERACAO -> tempo(d.tempoS) to "desde o fim do exercício"
        FaseDesafio.RESULTADO -> (d.recuperacaoS?.let { tempo(it) } ?: "> 3:00") to "tempo de recuperação"
        else -> null
    }

    Superficie(modifier) {
        TituloSecao(
            "Desafio do Pátio",
            icone = if (d.fase == FaseDesafio.RESULTADO) Icones.Trofeu else Icones.Bandeira,
            corIcone = if (d.fase == FaseDesafio.RESULTADO) Cores.Medindo else Cores.Texto3,
        )
        Etapas(etapa)
        Text(instrucao, color = Cores.Texto, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        if (cronometro != null) {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(cronometro.first, style = Estilos.Numero, fontSize = 40.sp, lineHeight = 40.sp,
                    color = if (d.fase == FaseDesafio.RESULTADO) Cores.Ok else Cores.Texto)
                Spacer(Modifier.width(10.dp))
                Text(cronometro.second, color = Cores.Texto3, fontSize = 13.sp, modifier = Modifier.padding(bottom = 6.dp))
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (d.repouso > 0) Estatistica("Repouso", "${d.repouso}", "BPM")
            if (d.pico > 0) Estatistica("Pico", "${d.pico}", "BPM")
            if (d.repouso > 0 && d.pico > 0) Estatistica("Aumento", "%+d".format(d.pico - d.repouso), "BPM", destaque = true)
            if (d.fase == FaseDesafio.RECUPERACAO) Estatistica("Alvo", "≤ ${d.alvo}", "BPM")
        }
    }
}

@Composable
private fun Estatistica(rotulo: String, valor: String, unidade: String, destaque: Boolean = false) {
    val cor = if (destaque) Cores.Bpm else Cores.Texto
    Column(
        Modifier
            .widthIn(min = 92.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(if (destaque) Cores.Bpm.copy(alpha = 0.12f) else Cores.FundoTopo.copy(alpha = 0.6f))
            .border(1.dp, if (destaque) Cores.Bpm.copy(alpha = 0.35f) else Cores.Borda, RoundedCornerShape(14.dp))
            .padding(horizontal = 14.dp, vertical = 10.dp)
    ) {
        Text(rotulo.uppercase(), style = Estilos.Rotulo, fontSize = 10.sp)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(valor, style = Estilos.Numero, fontSize = 24.sp, color = cor, lineHeight = 26.sp)
            Text(" $unidade", color = Cores.Texto3, fontSize = 11.sp, modifier = Modifier.padding(bottom = 3.dp))
        }
    }
}

// ---- Rodapé ----------------------------------------------------------------
@Composable
fun Rodape(aoTocar: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .clickable(onClick = aoTocar)
            .background(Cores.Medindo.copy(alpha = 0.07f))
            .border(1.dp, Cores.Medindo.copy(alpha = 0.18f), RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icone(Icones.Info, Cores.Medindo, 18.dp, contorno = true)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text("Projeto educacional: não é aparelho médico", color = Cores.Texto, fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold)
            Text("Sem nome, sem gravação, sem internet. Toque para saber mais.",
                color = Cores.Texto3, fontSize = 12.sp, lineHeight = 15.sp)
        }
        Icone(Icones.Seta, Cores.Texto3, 16.dp, contorno = true)
    }
}
