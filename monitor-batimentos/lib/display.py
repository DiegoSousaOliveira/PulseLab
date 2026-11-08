# lib/display.py
# ---------------------------------------------------------------------------
# Telas do OLED SSD1306 (128x64) com visual de monitor cardíaco.
#
#   ┌──────────────────────────────────────┐
#   │█MONITOR████████████ ESTÁVEL ███ 🔊 ██│  barra superior invertida
#   │ ♥    ▄▄  ▄▄  ▄▄   ┊ 💧 SpO2*         │
#   │      █ █ █ █ █ █  ┊    ▄▄ ▄▄         │  BPM grande | SpO2
#   │ BPM  ▀▀  ▀▀  ▀▀   ┊    ▀▀ ▀▀ %       │
#   │──────────────────────────────────────│
#   │   /\_    /\_    /\_    /\_    /\_    │  onda PPG rolando
#   └──────────────────────────────────────┘
#
# Tudo é desenhado num "framebuffer" (uma imagem na memória) e só depois
# enviado ao display de uma vez com mostrar(). Enviar 1 KB por I2C leva
# ~25 ms; por isso o programa principal redesenha no máximo 10x por segundo.
# ---------------------------------------------------------------------------

import framebuf
import math
import time
from micropython import const
from ssd1306 import SSD1306_I2C

# ---- Geometria -------------------------------------------------------------
LARGURA = const(128)
ALTURA = const(64)
MARGEM = const(2)
LETRA = const(8)                # a fonte embutida tem 8x8 pixels

BARRA_ALTURA = const(11)        # barra superior: y de 0 a 10
TEXTO_BARRA_Y = const(2)        # deixa 2 linhas acima para acentos (É, Á...)

CORACAO_X = const(2)            # ícone de coração 16x16
CORACAO_Y = const(14)
ROTULO_BPM_Y = const(34)

BPM_X = const(24)               # dígitos grandes do BPM
BPM_Y = const(14)
BPM_L, BPM_A, BPM_T = 14, 24, 3       # largura, altura e espessura do traço
BPM_ESPACO = const(3)

DIVISOR_X = const(76)

SPO2_X = const(80)              # bloco do SpO2
SPO2_ROTULO_Y = const(15)
SPO2_NUM_Y = const(27)
SPO2_L, SPO2_A, SPO2_T = 10, 16, 2
SPO2_ESPACO = const(2)

ONDA_LINHA_Y = const(46)        # linha que separa a onda
ONDA_Y = const(48)              # a onda ocupa y de 48 a 63 (múltiplo de 8!)
ONDA_ALTURA = const(16)

PROGRESSO_MAX = const(36)       # largura máxima da barra de carregamento
PROGRESSO_MIN = const(12)
PULSO_MS = const(200)           # quanto tempo o coração fica "cheio" após a batida


# ---- Ícones em "arte de texto" ---------------------------------------------
# Cada "#" é um pixel aceso. Fica fácil de enxergar e de editar!
CORACAO_GRANDE = (
    "................",
    "..####....####..",
    ".######..######.",
    "################",
    "################",
    "################",
    ".##############.",
    "..############..",
    "...##########...",
    "....########....",
    ".....######.....",
    "......####......",
    ".......##.......",
    "................",
    "................",
    "................",
)
CORACAO_PEQUENO = (
    "................",
    "................",
    "....##....##....",
    "...####..####...",
    "..############..",
    "..############..",
    "..############..",
    "...##########...",
    "....########....",
    ".....######.....",
    "......####......",
    ".......##.......",
    "................",
    "................",
    "................",
    "................",
)
GOTA = (                        # gota de sangue / O2
    "...##...",
    "...##...",
    "..####..",
    "..####..",
    ".######.",
    ".######.",
    "########",
    "########",
    ".######.",
    "..####..",
)
SOM_LIGADO = (
    "..#.....",
    ".##..#..",
    "###...#.",
    "###.#.#.",
    "###.#.#.",
    "###...#.",
    ".##..#..",
    "..#.....",
)
SOM_MUDO = (
    "..#.....",
    ".##.....",
    "###.#..#",
    "###..##.",
    "###..##.",
    "###.#..#",
    ".##.....",
    "..#.....",
)
CONFIRMA = (                    # "certinho" de leitura estável
    ".......#",
    "......##",
    "#....##.",
    "##..##..",
    ".####...",
    "..##....",
    "........",
    "........",
)
ASTERISCO = (                   # marca de "calibração presumida"
    "#.#",
    ".#.",
    "#.#",
)
BONECO_ALTO = (                 # pulando: braços para cima, pernas abertas
    ".......##.......",
    ".......##.......",
    "...#...##...#...",
    "....#.####.#....",
    ".....######.....",
    ".......##.......",
    ".......##.......",
    ".......##.......",
    "......####......",
    ".....##..##.....",
    "....##....##....",
    "...##......##...",
    "..##........##..",
    "................",
    "................",
    "................",
)
BONECO_BAIXO = (                # agachado: braços para baixo, pernas juntas
    "................",
    "................",
    "................",
    ".......##.......",
    ".......##.......",
    "......####......",
    ".....#.##.#.....",
    "....#..##..#....",
    ".......##.......",
    ".......##.......",
    "......####......",
    "......#..#......",
    "......#..#......",
    ".....##..##.....",
    "................",
    "................",
)
BLUETOOTH = (                   # o símbolo do Bluetooth (5x9)
    "..#..",
    "..##.",
    "#.#.#",
    ".###.",
    "..#..",
    ".###.",
    "#.#.#",
    "..##.",
    "..#..",
)
SETA_BAIXO = (
    "...##...",
    "...##...",
    "...##...",
    "#..##..#",
    ".#.##.#.",
    "..####..",
    "...##...",
)


def criar_icone(arte):
    """Converte a arte de texto em DOIS framebuffers:
    um para desenhar em fundo preto e outro (invertido) para fundo branco.
    Usamos blit() com uma "cor transparente" para copiar só os pixels acesos."""
    altura = len(arte)
    largura = len(arte[0])
    bytes_linha = (largura + 7) // 8
    normal = bytearray(bytes_linha * altura)
    invertido = bytearray(b"\xff" * (bytes_linha * altura))
    fb_n = framebuf.FrameBuffer(normal, largura, altura, framebuf.MONO_HLSB)
    fb_i = framebuf.FrameBuffer(invertido, largura, altura, framebuf.MONO_HLSB)
    for y, linha in enumerate(arte):
        for x, c in enumerate(linha):
            if c == "#":
                fb_n.pixel(x, y, 1)
                fb_i.pixel(x, y, 0)
    return (fb_n, fb_i, largura, altura)


# ---- Acentos ---------------------------------------------------------------
# A fonte do framebuf só tem letras sem acento. Desenhamos a letra base e
# depois o acento pixel a pixel. Nas minúsculas o acento cabe nas 2 linhas
# de cima da própria letra; nas maiúsculas ele fica 2 pixels ACIMA.
_ACENTO = {
    "agudo": ((3, 1), (4, 0)),
    "grave": ((2, 0), (3, 1)),
    "circ": ((1, 1), (2, 0), (3, 0), (4, 1)),
    "til": ((0, 1), (1, 0), (2, 0), (3, 1), (4, 1), (5, 0)),
}
_LETRAS_ACENTUADAS = {
    "á": ("a", "agudo"), "à": ("a", "grave"), "â": ("a", "circ"), "ã": ("a", "til"),
    "é": ("e", "agudo"), "ê": ("e", "circ"), "í": ("i", "agudo"),
    "ó": ("o", "agudo"), "ô": ("o", "circ"), "õ": ("o", "til"), "ú": ("u", "agudo"),
    "ç": ("c", "cedilha"),
    "Á": ("A", "agudo"), "À": ("A", "grave"), "Â": ("A", "circ"), "Ã": ("A", "til"),
    "É": ("E", "agudo"), "Ê": ("E", "circ"), "Í": ("I", "agudo"),
    "Ó": ("O", "agudo"), "Ô": ("O", "circ"), "Õ": ("O", "til"), "Ú": ("U", "agudo"),
    "Ç": ("C", "cedilha"),
}


def digito(fb, d, x, y, larg, alt, t, cor=1):
    """Desenha um dígito no estilo "display de 7 segmentos".

         aaa
        f   b       Cada segmento é um retângulo. Os cantos ficam
        f   b       vazios, o que dá o visual de aparelho eletrônico.
         ggg
        e   c       d = None desenha só o traço do meio ("-").
        e   c
         ddd
    """
    segs = _SEGMENTOS[d] if d is not None else "g"
    meio = (alt - t) // 2
    if "a" in segs: fb.fill_rect(x + t, y, larg - 2 * t, t, cor)
    if "g" in segs: fb.fill_rect(x + t, y + meio, larg - 2 * t, t, cor)
    if "d" in segs: fb.fill_rect(x + t, y + alt - t, larg - 2 * t, t, cor)
    if "f" in segs: fb.fill_rect(x, y + t, t, meio - t, cor)
    if "b" in segs: fb.fill_rect(x + larg - t, y + t, t, meio - t, cor)
    if "e" in segs: fb.fill_rect(x, y + meio + t, t, alt - meio - 2 * t, cor)
    if "c" in segs: fb.fill_rect(x + larg - t, y + meio + t, t, alt - meio - 2 * t, cor)


_SEGMENTOS = ("abcdef", "bc", "abged", "abgcd", "fgbc",
              "afgcd", "afgedc", "abc", "abcdefg", "abcdfg")


class Onda:
    """A onda PPG rolando, como num monitor de hospital.

    TÉCNICA: a onda tem o SEU PRÓPRIO framebuffer pequeno (128x16 pixels).
    A cada ponto novo, a imagem rola 1 pixel para a esquerda e só a última
    coluna é desenhada. Redesenhar as 128 colunas a cada quadro levava 10 ms.

    O TRUQUE DOS BYTES: o SSD1306 guarda a imagem em "páginas" de 8 linhas;
    cada byte é uma coluninha de 8 pixels. A onda (y = 48 a 63) ocupa
    exatamente as páginas 6 e 7 do display. Então:
      - rolar = mover os bytes de cada página 1 posição para a esquerda;
      - desenhar = copiar os 256 bytes direto para o buffer do display.
    São cópias de memória feitas em C: microssegundos, em vez de milissegundos.

    ESCALA AUTOMÁTICA: guardamos o maior e o menor valor recentes. Eles
    "encolhem" devagar em direção um ao outro, então se a onda diminuir a
    escala se ajusta sozinha em alguns segundos.
    """

    def __init__(self, largura=LARGURA, altura=ONDA_ALTURA):
        self.largura = largura
        self.altura = altura
        self.buf = bytearray(largura * altura // 8)
        self.fb = framebuf.FrameBuffer(self.buf, largura, altura, framebuf.MONO_VLSB)
        self.limpar()

    def limpar(self):
        self.fb.fill(0)
        self.maior = None
        self.menor = None
        self.y_ant = self.altura // 2

    def adicionar(self, valor):
        if self.maior is None:
            self.maior = self.menor = valor
        if valor > self.maior:
            self.maior = valor
        if valor < self.menor:
            self.menor = valor
        faixa = self.maior - self.menor
        # Encolhe a faixa 1% por ponto (~26 pontos por segundo).
        self.maior -= faixa * 0.01
        self.menor += faixa * 0.01
        if faixa < 1:
            faixa = 1
        y = self.altura - 1 - int((valor - self.menor) * (self.altura - 1) / faixa)
        if y < 0:
            y = 0
        elif y >= self.altura:
            y = self.altura - 1
        fb = self.fb
        b = self.buf
        n = self.largura
        for p in range(0, len(b), n):                  # cada página (8 linhas)
            b[p:p + n - 1] = b[p + 1:p + n]            # rola 1 coluna para a esquerda
        fb.vline(n - 1, 0, self.altura, 0)             # apaga a coluna nova
        fb.line(self.largura - 2, self.y_ant, self.largura - 1, y, 1)
        self.y_ant = y

    def desenhar(self, tela_buf, pagina):
        """Copia a onda para o buffer do display a partir da `pagina` (y/8)."""
        inicio = pagina * self.largura
        tela_buf[inicio:inicio + len(self.buf)] = self.buf


class Tela:
    """Todas as telas do Monitor de Batimentos."""

    def __init__(self, i2c, endereco=0x3C):
        self.oled = SSD1306_I2C(LARGURA, ALTURA, i2c, endereco)
        self.onda = Onda()
        self._coracao_g = criar_icone(CORACAO_GRANDE)
        self._coracao_p = criar_icone(CORACAO_PEQUENO)
        self._gota = criar_icone(GOTA)
        self._som_on = criar_icone(SOM_LIGADO)
        self._som_off = criar_icone(SOM_MUDO)
        self._confirma = criar_icone(CONFIRMA)
        self._asterisco = criar_icone(ASTERISCO)
        self._seta = criar_icone(SETA_BAIXO)
        self._bluetooth = criar_icone(BLUETOOTH)
        # Ícone do Bluetooth na barra: None = sem Bluetooth (não ocupa espaço),
        # True = desenha, False = guarda o lugar mas não desenha (pisca).
        self.bluetooth = None
        self._boneco = (criar_icone(BONECO_ALTO), criar_icone(BONECO_BAIXO))

    # ------------------------------------------------------------ básicos
    def mostrar(self):
        """Envia o framebuffer ao display (~25 ms a 400 kHz)."""
        self.oled.show()

    def limpar(self):
        self.oled.fill(0)

    def icone(self, icone, x, y, cor=1):
        fb_n, fb_i, _, _ = icone
        if cor:
            self.oled.blit(fb_n, x, y, 0)    # copia só os pixels acesos
        else:
            self.oled.blit(fb_i, x, y, 1)    # copia só os pixels apagados

    def texto(self, s, x, y, cor=1):
        """Escreve texto com acentos (á, ã, ç, É...). 8 pixels por letra."""
        fb = self.oled
        for ch in s:
            base, acento = _LETRAS_ACENTUADAS.get(ch, (ch, None))
            fb.text(base, x, y, cor)
            if acento == "cedilha":
                fb.pixel(x + 2, y + 7, cor)
                fb.pixel(x + 3, y + 7, cor)
            elif acento:
                topo = y if base.islower() else y - 2
                if base == "i":
                    fb.fill_rect(x, y, 6, 2, 1 - cor)   # apaga o pingo do i
                for dx, dy in _ACENTO[acento]:
                    fb.pixel(x + dx, topo + dy, cor)
            x += LETRA

    def centralizado(self, s, y, cor=1):
        self.texto(s, (LARGURA - len(s) * LETRA) // 2, y, cor)

    def barra(self, titulo, som=None, direita=None, progresso=None, ok=False):
        """Barra superior invertida: título à esquerda; som e Bluetooth à direita.
        No meio: um texto (direita), uma barra de progresso, ou o "certinho"."""
        fb = self.oled
        fb.fill_rect(0, 0, LARGURA, BARRA_ALTURA, 1)
        self.texto(titulo, MARGEM, TEXTO_BARRA_Y, 0)
        limite = LARGURA - MARGEM
        if som is not None:
            self.icone(self._som_on if som else self._som_off,
                       LARGURA - MARGEM - 8, 1, 0)
            limite -= 11
            if self.bluetooth is not None:
                if self.bluetooth:
                    self.icone(self._bluetooth, limite - 5, 1, 0)
                limite -= 9
        if progresso is not None:
            x0 = MARGEM + len(titulo) * LETRA + 6
            larg = limite - x0 - 2
            if larg > PROGRESSO_MAX:
                x0 += larg - PROGRESSO_MAX      # barra curta, encostada nos ícones
                larg = PROGRESSO_MAX
            if larg >= PROGRESSO_MIN:
                fb.rect(x0, 3, larg, 5, 0)
                fb.fill_rect(x0 + 1, 4, int((larg - 2) * progresso), 3, 0)
        elif direita:
            x0 = limite - len(direita) * LETRA
            if ok:
                x0 -= 10
                self.icone(self._confirma, x0, 1, 0)
                x0 += 10
            self.texto(direita, x0, TEXTO_BARRA_Y, 0)

    def numero(self, valor, digitos, x, y, larg, alt, t, espaco):
        """Escreve um número alinhado à direita num campo de `digitos` casas.
        valor = None (ou 0) desenha traços: "---"."""
        if not valor:
            for i in range(digitos):
                digito(self.oled, None, x + i * (larg + espaco), y, larg, alt, t)
            return
        s = str(valor)[-digitos:]          # aceita número ou texto ("05")
        x += (digitos - len(s)) * (larg + espaco)
        for ch in s:
            digito(self.oled, ord(ch) - 48, x, y, larg, alt, t)
            x += larg + espaco

    # ------------------------------------------------------------- telas
    def abertura(self, t_ms, presumido=False):
        """Tela de abertura animada. Devolve False quando terminou.
        Fases: traçado de ECG -> nome + coração -> aviso -> (aviso do SpO2)."""
        fb = self.oled
        fb.fill(0)
        if t_ms < 1100:
            # 1) Um traçado de eletrocardiograma sendo desenhado.
            fim = LARGURA * t_ms // 1000
            ant = None
            for x in range(min(fim, LARGURA)):
                y = _ecg(x)
                if ant is not None:
                    fb.line(x - 1, ant, x, y, 1)
                ant = y
            if fim < LARGURA:
                fb.fill_rect(fim - 1, _ecg(max(fim - 1, 0)) - 1, 3, 3, 1)   # "caneta"
            return True
        if t_ms < 2700:
            # 2) Coração pulsando + nome do projeto.
            grande = (t_ms // 350) % 2 == 0
            self.icone(self._coracao_g if grande else self._coracao_p, 56, 4)
            self.centralizado("Monitor de", 26)
            self.centralizado("Batimentos", 38)
            fb.hline(24, 50, 80, 1)
            self.centralizado("BitDogLab", 54)
            return True
        if t_ms < 5200:
            # 3) Aviso obrigatório.
            self.barra("AVISO")
            self.centralizado("Projeto", 15)
            self.centralizado("educacional.", 25)
            self.centralizado("NÃO é aparelho", 39)
            self.centralizado("médico.", 49)
            return True
        if presumido and t_ms < 7200:
            # 4) Transparência sobre o SpO2.
            self.barra("SpO2*")
            self.centralizado("Calibração", 17)
            self.centralizado("presumida:", 27)
            self.centralizado("valor só para", 41)
            self.centralizado("estudo.", 51)
            return True
        return False

    def sem_dedo(self, t_ms, modo="MONITOR", som=True,
                 linhas=("Coloque o dedo", "no sensor", "(sem apertar)")):
        """Pede para colocar o dedo, com uma seta que "pula" sobre o sensor."""
        fb = self.oled
        fb.fill(0)
        self.barra(modo, som)
        y = 15
        for linha in linhas:
            self.centralizado(linha, y)
            y += 10
        pulo = int(3 * math.sin(t_ms / 150))
        self.icone(self._seta, 60, 47 + pulo)
        fb.fill_rect(50, 58, 28, 4, 1)              # o "sensor"
        fb.fill_rect(61, 59, 6, 2, 0)               # a janelinha dele

    def principal(self, t_ms, bpm, spo2, estavel, progresso, ultima_batida_ms,
                  modo="MONITOR", som=True, presumido=False):
        """Tela de monitor: BPM grande, SpO2, coração que pulsa e onda."""
        fb = self.oled
        fb.fill(0)
        if estavel:
            self.barra(modo, som, direita="OK", ok=True)
        else:
            self.barra(modo, som, progresso=progresso)

        self._bloco_bpm(t_ms, bpm, ultima_batida_ms)

        # SpO2
        self.icone(self._gota, SPO2_X, SPO2_ROTULO_Y - 1)
        self.texto("SpO2", SPO2_X + 10, SPO2_ROTULO_Y)
        if presumido:
            self.icone(self._asterisco, SPO2_X + 43, SPO2_ROTULO_Y - 1)
        self.numero(spo2, 3, SPO2_X, SPO2_NUM_Y, SPO2_L, SPO2_A, SPO2_T, SPO2_ESPACO)
        self.texto("%", SPO2_X + 3 * (SPO2_L + SPO2_ESPACO), SPO2_NUM_Y + SPO2_A - LETRA)

        self._rodape_onda()

    def _bloco_bpm(self, t_ms, bpm, ultima_batida_ms):
        """Lado esquerdo: coração que pulsa + BPM grande + divisor."""
        fb = self.oled
        # Coração: "cheio" logo depois de cada batida, menor no resto do tempo.
        # (ticks_diff, e não "-": o relógio ticks_ms dá a volta depois de
        # ~12 dias e a subtração simples daria um valor errado.)
        cheio = (ultima_batida_ms is not None and
                 0 <= time.ticks_diff(t_ms, ultima_batida_ms) < PULSO_MS)
        self.icone(self._coracao_g if cheio else self._coracao_p, CORACAO_X, CORACAO_Y)
        self.texto("BPM", MARGEM, ROTULO_BPM_Y)
        self.numero(bpm, 3, BPM_X, BPM_Y, BPM_L, BPM_A, BPM_T, BPM_ESPACO)
        for y in range(BARRA_ALTURA + 3, ONDA_LINHA_Y - 1, 2):   # divisor pontilhado
            fb.pixel(DIVISOR_X, y, 1)

    def _rodape_onda(self):
        """Linha separadora + onda PPG (copiada direto para o buffer)."""
        self.oled.hline(0, ONDA_LINHA_Y, LARGURA, 1)
        self.onda.desenhar(self.oled.buffer, ONDA_Y // 8)

    def tempo_medio(self, segundos, x, y):
        """Escreve m:ss com os dígitos médios (ex.: 1:25). Máximo 9:59."""
        segundos = int(segundos)
        if segundos > 599:
            segundos = 599
        digito(self.oled, segundos // 60, x, y, SPO2_L, SPO2_A, SPO2_T)
        x += SPO2_L + 3
        self.oled.fill_rect(x, y + 4, 2, 2, 1)          # os dois pontos ":"
        self.oled.fill_rect(x, y + SPO2_A - 6, 2, 2, 1)
        x += 5
        self.numero("{:02d}".format(segundos % 60), 2, x, y,
                    SPO2_L, SPO2_A, SPO2_T, SPO2_ESPACO)

    # ------------------------------------------------- Desafio do Pátio
    def desafio_medicao(self, t_ms, titulo, bpm, ultima_batida_ms, rotulo,
                        segundos, som=True, como_tempo=False):
        """Monitor com um cronômetro no lugar do SpO2 (repouso e recuperação)."""
        self.oled.fill(0)
        self.barra(titulo, som)
        self._bloco_bpm(t_ms, bpm, ultima_batida_ms)
        self.texto(rotulo, SPO2_X + 2, SPO2_ROTULO_Y)
        if como_tempo:
            self.tempo_medio(segundos, SPO2_X + 2, SPO2_NUM_Y)
        else:
            self.numero(int(segundos + 0.999), 2, SPO2_X + 2, SPO2_NUM_Y,
                        SPO2_L, SPO2_A, SPO2_T, SPO2_ESPACO)
            self.texto("s", SPO2_X + 2 + 2 * (SPO2_L + SPO2_ESPACO) + 2,
                       SPO2_NUM_Y + SPO2_A - LETRA)
        self._rodape_onda()

    def desafio_exercicio(self, t_ms, restante_s, som=True):
        """Contagem regressiva do exercício, com bonequinhos pulando."""
        fb = self.oled
        fb.fill(0)
        self.barra("DESAFIO 2/3", som)
        quadro = (t_ms // 300) % 2                 # troca de pose a cada 300 ms
        y = 15 if quadro == 0 else 18
        self.icone(self._boneco[quadro], 6, y)
        self.icone(self._boneco[1 - quadro], LARGURA - 22, 33 - y)
        self.numero(int(restante_s + 0.999), 2, 44, 14, BPM_L, BPM_A, BPM_T, BPM_ESPACO)
        self.texto("s", 44 + 2 * (BPM_L + BPM_ESPACO) + 1, 30)
        self.centralizado("Tire o dedo e", 43)
        self.centralizado("PULE no lugar!", 54)

    def desafio_resultado(self, repouso, pico, recuperacao_s, som=True):
        """Resultado final. O aumento ganha destaque (faixa invertida)."""
        fb = self.oled
        fb.fill(0)
        self.barra("RESULTADO", som)

        def linha(rotulo, valor, y, cor=1):
            self.texto(rotulo, MARGEM, y, cor)
            self.texto(valor, LARGURA - MARGEM - len(valor) * LETRA, y, cor)

        linha("Repouso", "{} BPM".format(repouso), 14)
        linha("Pico", "{} BPM".format(pico), 24)
        fb.fill_rect(0, 33, LARGURA, 10, 1)
        linha("Aumento", "{:+d} BPM".format(pico - repouso), 34, 0)
        if recuperacao_s is None:
            linha("Recuperou", ">3:00", 45)
        else:
            s_ = int(recuperacao_s)
            linha("Recuperou", "{}:{:02d}".format(s_ // 60, s_ % 60), 45)
        self.centralizado("B: voltar", 56)

    def erro_sensor(self, detalhe=""):
        """Sensor não encontrado: mensagem clara com as dicas do README."""
        self.oled.fill(0)
        self.barra("ERRO")
        self.centralizado("Sensor não", 14)
        self.centralizado("encontrado!", 23)
        self.texto("Confira o cabo", MARGEM, 35)
        self.texto("no I2C0 (GP0/1)", MARGEM, 44)
        self.texto("e os pull-ups", MARGEM, 53)
        if detalhe:
            self.texto(detalhe[:4], LARGURA - MARGEM - 32, TEXTO_BARRA_Y, 0)


def _ecg(x):
    """Formato de um batimento de ECG (P, QRS, T) repetido a cada 64 pixels,
    para a animação de abertura."""
    p = x % 64
    base = 36
    if 8 <= p < 14:                  # onda P (pequena subida)
        return base - (3 if 9 <= p < 13 else 1)
    if p == 20: return base + 3      # Q
    if p == 21: return base - 12     # R (pico)
    if p == 22: return base - 24
    if p == 23: return base - 8
    if p == 24: return base + 8      # S
    if 32 <= p < 42:                 # onda T
        return base - (4 if 34 <= p < 40 else 2)
    return base
