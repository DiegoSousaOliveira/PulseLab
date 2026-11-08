package br.pulselab.batimentos.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import br.pulselab.batimentos.R

/**
 * Paleta do app. Parte das mesmas cores do painel web (rosa = batimentos,
 * azul = oxigenação, fundo azul-marinho) com tons extras para dar
 * profundidade: superfícies em degradê, bordas finas e cores de faixa.
 */
object Cores {
    val FundoTopo = Color(0xFF060A14)
    val Fundo = Color(0xFF0F172A)
    val Cartao = Color(0xFF111A2E)
    val CartaoClaro = Color(0xFF16213A)
    val Borda = Color(0xFF1E2A44)
    val Trilho = Color(0xFF1C2740)        // fundo de anéis e barras
    val Grade = Color(0xFF16213A)         // grade do "papel de monitor"
    val GradeForte = Color(0xFF1F2C48)

    val Texto = Color(0xFFF1F5F9)
    val Texto2 = Color(0xFF94A3B8)
    val Texto3 = Color(0xFF64748B)

    val Bpm = Color(0xFFF43F5E)           // rosa-vermelho: batimentos
    val BpmClaro = Color(0xFFFB7185)
    val Coral = Color(0xFFFB923C)
    val Spo2 = Color(0xFF38BDF8)          // azul: oxigenação
    val Spo2Escuro = Color(0xFF0EA5E9)
    val Ok = Color(0xFF34D399)
    val Medindo = Color(0xFFFBBF24)

    // As 4 faixas do LED RGB da placa (só faixas de valor, sem interpretação médica).
    val FaixaAzul = Color(0xFF60A5FA)
    val FaixaVerde = Color(0xFF34D399)
    val FaixaLaranja = Color(0xFFFB923C)
    val FaixaVermelha = Color(0xFFF43F5E)

    val Marca = Brush.linearGradient(listOf(BpmClaro, Bpm, Coral))
    val FundoTela = Brush.verticalGradient(listOf(FundoTopo, Fundo))
    val Superficie = Brush.verticalGradient(listOf(CartaoClaro, Cartao))
}

/** DM Sans (licença SIL OFL, veja docs/OFL-DMSans.txt): uma fonte variável com todos os pesos. */
@OptIn(ExperimentalTextApi::class)
private fun peso(w: Int) = Font(
    R.font.dm_sans, FontWeight(w),
    variationSettings = FontVariation.Settings(FontVariation.weight(w)),
)

val DmSans = FontFamily(peso(400), peso(500), peso(600), peso(700), peso(800))

/** Estilos usados nas telas. */
object Estilos {
    /** Rótulo de seção: caixa-alta pequena e espaçada, típico de painéis profissionais. */
    val Rotulo = TextStyle(fontFamily = DmSans, fontWeight = FontWeight(600), fontSize = 11.sp,
        letterSpacing = 1.4.sp, color = Cores.Texto3)
    /** Números: algarismos de largura fixa (não "pulam" quando o valor muda). */
    val Numero = TextStyle(fontFamily = DmSans, fontWeight = FontWeight(800),
        fontFeatureSettings = "tnum", letterSpacing = (-1).sp)
}

@Composable
fun TemaMonitor(conteudo: @Composable () -> Unit) {
    val base = Typography()
    fun TextStyle.dm() = copy(fontFamily = DmSans)
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Cores.Bpm,
            onPrimary = Color.White,
            secondary = Cores.Spo2,
            background = Cores.Fundo,
            onBackground = Cores.Texto,
            surface = Cores.Cartao,
            onSurface = Cores.Texto,
            surfaceContainer = Cores.CartaoClaro,
            surfaceContainerLow = Cores.Cartao,
            surfaceContainerHigh = Cores.CartaoClaro,
            onSurfaceVariant = Cores.Texto2,
            outline = Cores.Borda,
        ),
        typography = Typography(
            displayLarge = base.displayLarge.dm(), displayMedium = base.displayMedium.dm(),
            displaySmall = base.displaySmall.dm(), headlineLarge = base.headlineLarge.dm(),
            headlineMedium = base.headlineMedium.dm(), headlineSmall = base.headlineSmall.dm(),
            titleLarge = base.titleLarge.dm(), titleMedium = base.titleMedium.dm(),
            titleSmall = base.titleSmall.dm(), bodyLarge = base.bodyLarge.dm(),
            bodyMedium = base.bodyMedium.dm(), bodySmall = base.bodySmall.dm(),
            labelLarge = base.labelLarge.dm(), labelMedium = base.labelMedium.dm(),
            labelSmall = base.labelSmall.dm(),
        ),
        content = conteudo,
    )
}
