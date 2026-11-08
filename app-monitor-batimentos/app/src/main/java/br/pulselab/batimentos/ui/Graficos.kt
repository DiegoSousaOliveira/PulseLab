package br.pulselab.batimentos.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.sin

// ---- Faixas de BPM (as mesmas do LED RGB da placa) --------------------------
const val BPM_MIN_ESCALA = 40
const val BPM_MAX_ESCALA = 180

private data class Faixa(val de: Int, val ate: Int, val cor: Color, val nome: String)

private val FAIXAS = listOf(
    Faixa(40, 60, Cores.FaixaAzul, "abaixo de 60"),
    Faixa(60, 100, Cores.FaixaVerde, "entre 60 e 100"),
    Faixa(100, 140, Cores.FaixaLaranja, "entre 100 e 140"),
    Faixa(140, 180, Cores.FaixaVermelha, "acima de 140"),
)

private fun faixaDe(bpm: Int) = when {
    bpm < 60 -> FAIXAS[0]
    bpm <= 100 -> FAIXAS[1]
    bpm <= 140 -> FAIXAS[2]
    else -> FAIXAS[3]
}

/** Texto da faixa: só a faixa de valores, sem interpretação médica. */
fun textoFaixa(bpm: Int): String = if (bpm <= 0) "Aguardando leitura" else "Faixa ${faixaDe(bpm).nome} BPM"

fun corFaixa(bpm: Int): Color = if (bpm <= 0) Cores.Texto3 else faixaDe(bpm).cor

/**
 * Anel de 270° em volta do BPM (como o mostrador de um aparelho).
 *  - com BPM: o arco vai de 40 a 200 BPM, em degradê rosa;
 *  - medindo (sem BPM ainda): o arco vira uma barra de progresso âmbar;
 *  - [pulso] (0 a 1): brilho que acende a cada batida e apaga em seguida.
 */
@Composable
fun AnelBpm(
    bpm: Int,
    medindo: Boolean,
    progresso: Float,
    pulso: Float,
    modifier: Modifier = Modifier,
    centro: @Composable BoxScope.() -> Unit,
) {
    val alvo = when {
        bpm > 0 -> ((bpm - 40f) / 160f).coerceIn(0.02f, 1f)
        medindo -> progresso.coerceIn(0f, 1f)
        else -> 0f
    }
    val fracao by animateFloatAsState(alvo, tween(700), label = "anel")
    val emProgresso = bpm <= 0 && medindo

    Box(modifier.aspectRatio(1f), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val esp = size.minDimension * 0.055f
            val raio = size.minDimension / 2 - esp - size.minDimension * 0.04f
            val canto = Offset(center.x - raio, center.y - raio)
            val caixa = Size(raio * 2, raio * 2)

            // Brilho da batida
            if (pulso > 0f) {
                drawCircle(
                    Brush.radialGradient(
                        listOf(Cores.Bpm.copy(alpha = 0.32f * pulso), Color.Transparent),
                        center, raio * 1.25f,
                    ),
                    raio * 1.25f,
                )
            }
            // Marcas a cada 20 BPM (40, 60, ..., 200)
            for (i in 0..8) {
                val a = Math.toRadians(135.0 + 270.0 * i / 8)
                val r1 = raio - esp * 1.25f
                val r2 = r1 - esp * (if (i % 2 == 0) 0.7f else 0.4f)
                drawLine(
                    Cores.Texto3.copy(alpha = if (i % 2 == 0) 0.7f else 0.35f),
                    Offset(center.x + r1 * cos(a).toFloat(), center.y + r1 * sin(a).toFloat()),
                    Offset(center.x + r2 * cos(a).toFloat(), center.y + r2 * sin(a).toFloat()),
                    strokeWidth = esp * 0.16f, cap = StrokeCap.Round,
                )
            }
            // Trilho
            drawArc(Cores.Trilho, 135f, 270f, false, canto, caixa, style = Stroke(esp, cap = StrokeCap.Round))
            // Valor
            if (fracao > 0.005f) {
                val cores = if (emProgresso) listOf(Cores.Medindo, Cores.Coral, Cores.Medindo)
                else listOf(Cores.BpmClaro, Cores.Bpm, Cores.BpmClaro)
                rotate(135f, center) {
                    drawArc(
                        Brush.sweepGradient(0f to cores[0], 0.75f to cores[1], 1f to cores[2], center = center),
                        0f, 270f * fracao, false, canto, caixa, style = Stroke(esp, cap = StrokeCap.Round),
                    )
                }
                // Pontinho luminoso na ponta do arco
                val a = Math.toRadians(135.0 + 270.0 * fracao)
                val ponta = Offset(center.x + raio * cos(a).toFloat(), center.y + raio * sin(a).toFloat())
                val corPonta = if (emProgresso) Cores.Medindo else Cores.Bpm
                drawCircle(corPonta.copy(alpha = 0.35f), esp * 0.95f, ponta)
                drawCircle(Color.White, esp * 0.32f, ponta)
            }
        }
        centro()
    }
}

/**
 * Barra segmentada com as 4 faixas de BPM e um marcador no valor atual.
 * As larguras são proporcionais: 40-60, 60-100, 100-140, 140-180.
 */
@Composable
fun BarraFaixas(bpm: Int, modifier: Modifier = Modifier) {
    val posicao by animateFloatAsState(
        ((bpm.coerceIn(BPM_MIN_ESCALA, BPM_MAX_ESCALA) - 40f) / 140f), tween(600), label = "faixa",
    )
    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(18.dp)) {
            val alt = 7.dp.toPx()
            val vao = 4.dp.toPx()
            val y = (size.height - alt) / 2
            val ativa = if (bpm > 0) faixaDe(bpm) else null
            FAIXAS.forEach { f ->
                val x0 = (f.de - 40f) / 140f * size.width + if (f.de > 40) vao / 2 else 0f
                val x1 = (f.ate - 40f) / 140f * size.width - if (f.ate < 180) vao / 2 else 0f
                drawRoundRect(
                    f.cor.copy(alpha = if (f == ativa) 1f else 0.22f),
                    Offset(x0, y), Size(x1 - x0, alt), CornerRadius(alt / 2),
                )
            }
            if (ativa != null) {
                val x = posicao * size.width
                drawCircle(ativa.cor.copy(alpha = 0.35f), 9.dp.toPx(), Offset(x, size.height / 2))
                drawCircle(Color.White, 6.dp.toPx(), Offset(x, size.height / 2))
                drawCircle(ativa.cor, 3.5.dp.toPx(), Offset(x, size.height / 2))
            }
        }
        // Números nas divisas entre as faixas
        Row(Modifier.fillMaxWidth()) {
            listOf(20f to "", 40f to "60", 40f to "100", 40f to "140").forEachIndexed { i, (peso, rotulo) ->
                Box(Modifier.weight(peso)) {
                    if (i > 0) Text(rotulo, style = Estilos.Rotulo.copy(letterSpacing = 0.sp), fontSize = 10.sp,
                        textAlign = TextAlign.Start)
                }
            }
        }
    }
}

/** Barrinha fina de progresso (0 a 1). */
@Composable
fun MiniBarra(fracao: Float, cor: Color, modifier: Modifier = Modifier) {
    val f by animateFloatAsState(fracao.coerceIn(0f, 1f), tween(500), label = "mini")
    Canvas(modifier.fillMaxWidth().height(5.dp)) {
        val r = CornerRadius(size.height / 2)
        drawRoundRect(Cores.Trilho, cornerRadius = r)
        if (f > 0f) drawRoundRect(cor, size = Size(size.width * f, size.height), cornerRadius = r)
    }
}

/**
 * A onda do pulso num "papel de monitor": grade quadriculada, área em
 * degradê sob a curva, a linha com brilho e um ponto luminoso na ponta.
 */
@Composable
fun MonitorOnda(pontos: List<Int>, totalPontos: Int, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val w = size.width
        val h = size.height
        // Grade: linhas finas a cada 12 dp e mais fortes a cada 5 quadradinhos
        val passoGrade = 12.dp.toPx()
        var i = 0
        var x = 0f
        while (x <= w) {
            drawLine(if (i % 5 == 0) Cores.GradeForte else Cores.Grade, Offset(x, 0f), Offset(x, h), 1f)
            x += passoGrade; i++
        }
        i = 0
        var y = h
        while (y >= 0f) {
            drawLine(if (i % 5 == 0) Cores.GradeForte else Cores.Grade, Offset(0f, y), Offset(w, y), 1f)
            y -= passoGrade; i++
        }
        if (pontos.size < 2) return@Canvas

        var menor = pontos.min().toFloat()
        var maior = pontos.max().toFloat()
        if (maior - menor < 1f) { maior += 1f; menor -= 1f }
        val margem = h * 0.12f
        val passo = w / (totalPontos - 1)
        val x0 = w - (pontos.size - 1) * passo           // a onda "entra" pela direita
        val linha = Path()
        pontos.forEachIndexed { k, v ->
            val px = x0 + k * passo
            val py = h - margem - (v - menor) * (h - 2 * margem) / (maior - menor)
            if (k == 0) linha.moveTo(px, py) else linha.lineTo(px, py)
        }
        val ultimoX = x0 + (pontos.size - 1) * passo
        val ultimoY = h - margem - (pontos.last() - menor) * (h - 2 * margem) / (maior - menor)

        // Área sob a curva
        val area = Path().apply {
            addPath(linha)
            lineTo(ultimoX, h); lineTo(x0, h); close()
        }
        drawPath(area, Brush.verticalGradient(listOf(Cores.Bpm.copy(alpha = 0.28f), Color.Transparent)))
        // Brilho + linha
        drawPath(linha, Cores.Bpm.copy(alpha = 0.22f),
            style = Stroke(8.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawPath(linha, Cores.BpmClaro,
            style = Stroke(2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        // Ponta luminosa
        drawCircle(Cores.Bpm.copy(alpha = 0.35f), 9.dp.toPx(), Offset(ultimoX, ultimoY))
        drawCircle(Color.White, 3.5.dp.toPx(), Offset(ultimoX, ultimoY))
    }
}
