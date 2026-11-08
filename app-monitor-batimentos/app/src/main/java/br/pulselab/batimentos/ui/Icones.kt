package br.pulselab.batimentos.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Ícones desenhados a partir de caminhos SVG numa caixa de 24x24 (o mesmo
 * formato dos ícones da página web). Assim o app não depende de nenhuma
 * biblioteca de ícones.
 */
object Icones {
    private fun p(d: String) = PathParser().parsePathString(d).toPath()

    // Preenchidos
    val Coracao = p("M12 21s-7.5-4.6-10-9.3C.4 8.6 2.1 4.5 6 4.1c2.3-.2 4.4 1.1 6 3.1 1.6-2 3.7-3.3 6-3.1 3.9.4 5.6 4.5 4 7.6C19.5 16.4 12 21 12 21z")
    val Gota = p("M12 2s7 7.6 7 12.5A7 7 0 0 1 5 14.5C5 9.6 12 2 12 2z")

    // De contorno (desenhados com traço)
    val Bluetooth = p("M6.5 6.5L17.5 17.5L12 23V1l5.5 5.5L6.5 17.5")
    val Pulso = p("M22 12h-4l-3 9L9 3l-3 9H2")
    val Info = p("M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20M12 16v-4M12 8h.01")
    val Certo = p("M20 6L9 17l-5-5")
    val Bandeira = p("M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7")
    val Trofeu = p("M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3")
    val Dedo = p("M12 2a3 3 0 0 0-3 3v8M15 5a3 3 0 0 0-3-3M9 13l-1.5-1.5a2 2 0 0 0-2.8 2.8L9 19a5 5 0 0 0 4 2h1a5 5 0 0 0 5-5v-5a2 2 0 0 0-4 0M15 11V5")
    val Seta = p("M9 18l6-6-6-6")
    val Escudo = p("M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z")
}

/** Desenha um ícone: preenchido ou só o contorno (traço com pontas arredondadas). */
@Composable
fun Icone(
    caminho: Path,
    cor: Color,
    tamanho: Dp = 20.dp,
    contorno: Boolean = false,
    espessura: Float = 2f,          // em unidades da caixa 24x24
    modifier: Modifier = Modifier,
) {
    Canvas(modifier.size(tamanho)) {
        scale(size.width / 24f, size.height / 24f, pivot = Offset.Zero) {
            if (contorno) drawPath(caminho, cor, style = Stroke(espessura, cap = StrokeCap.Round, join = StrokeJoin.Round))
            else drawPath(caminho, cor)
        }
    }
}

/** Ícone dentro de um quadradinho com fundo da mesma cor, bem clarinho. */
@Composable
fun IconeEmBadge(caminho: Path, cor: Color, contorno: Boolean = false, tamanho: Dp = 34.dp) {
    Box(
        Modifier.size(tamanho).clip(RoundedCornerShape(10.dp)).background(cor.copy(alpha = 0.14f)),
        contentAlignment = Alignment.Center,
    ) { Icone(caminho, cor, tamanho * 0.52f, contorno) }
}

/** Logotipo: coração branco num quadrado arredondado com o degradê da marca. */
@Composable
fun Logotipo(tamanho: Dp = 40.dp) {
    Box(
        Modifier.size(tamanho).clip(RoundedCornerShape(tamanho * 0.3f)).background(Cores.Marca),
        contentAlignment = Alignment.Center,
    ) {
        Icone(Icones.Coracao, Color.White, tamanho * 0.5f)
    }
}

/** Três pontinhos verticais (menu). */
@Composable
fun IconeMenu(cor: Color, tamanho: Dp = 22.dp) {
    Canvas(Modifier.size(tamanho)) {
        val r = size.width * 0.09f
        for (i in -1..1) drawCircle(cor, r, Offset(size.width / 2, size.height / 2 + i * size.height * 0.28f))
    }
}

/** Barrinhas de sinal (0 a 4) para a lista de placas. */
@Composable
fun IconeSinal(nivel: Int, cor: Color, tamanho: Dp = 18.dp) {
    Canvas(Modifier.size(tamanho)) {
        val larg = size.width / 7
        for (i in 0 until 4) {
            val alt = size.height * (i + 1) / 4
            drawRoundRect(
                if (i < nivel) cor else cor.copy(alpha = 0.25f),
                topLeft = Offset(i * larg * 1.9f, size.height - alt),
                size = androidx.compose.ui.geometry.Size(larg, alt),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(larg / 2),
            )
        }
    }
}
