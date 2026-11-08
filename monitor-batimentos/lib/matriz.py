# lib/matriz.py
# ---------------------------------------------------------------------------
# Luzes da BitDogLab: a matriz 5x5 de LEDs WS2812 e o LED RGB.
#
# MATRIZ EM ZIGUE-ZAGUE:
#   Os 25 LEDs formam UMA fila só (o sinal de dados passa de um para o
#   outro). A fila começa no canto de BAIXO à DIREITA e vai serpenteando:
#
#        coluna:  0   1   2   3   4
#     linha 0:   24  23  22  21  20     <- (de cima)
#     linha 1:   15  16  17  18  19
#     linha 2:   14  13  12  11  10
#     linha 3:    5   6   7   8   9
#     linha 4:    4   3   2   1   0     <- o primeiro LED da fila
#
#   Para desenhar pensando em (linha, coluna), convertemos para a posição
#   na fila com indice(). Se na sua placa a imagem sair espelhada ou de
#   ponta-cabeça, ajuste as constantes INVERTER_* abaixo.
# ---------------------------------------------------------------------------

import math
from machine import Pin, PWM
from neopixel import NeoPixel

import cores

LADO = 5
INVERTER_LINHAS = False      # True se a imagem sair de ponta-cabeça
INVERTER_COLUNAS = False     # True se a imagem sair espelhada

# Desenhos 5x5 ("#" = aceso)
DESENHO_CORACAO = (
    ".#.#.",
    "#####",
    "#####",
    ".###.",
    "..#..",
)
DESENHO_X = (
    "#...#",
    ".#.#.",
    "..#..",
    ".#.#.",
    "#...#",
)
DESENHO_SETA = (             # para conferir a orientação da matriz
    "..#..",
    ".###.",
    "#.#.#",
    "..#..",
    "..#..",
)

# Animação do coração
BRILHO_REPOUSO = 0.25        # fração do brilho de cores.CORACAO entre as batidas
DECAIMENTO = 0.85            # a cada atualização (~30 ms) o brilho cai 15%
RESPIRAR_MIN = 0.04          # sem dedo: coração bem fraquinho "respirando"
RESPIRAR_MAX = 0.14
RESPIRAR_PERIODO_MS = 3000


def indice(linha, coluna):
    """Converte (linha, coluna) - linha 0 em cima - na posição da fila."""
    if INVERTER_LINHAS:
        linha = LADO - 1 - linha
    if INVERTER_COLUNAS:
        coluna = LADO - 1 - coluna
    de_baixo = LADO - 1 - linha          # 0 = linha de baixo
    if de_baixo % 2 == 0:
        # linhas pares (contando de baixo) andam da direita para a esquerda
        return de_baixo * LADO + (LADO - 1 - coluna)
    # linhas ímpares andam da esquerda para a direita
    return de_baixo * LADO + coluna


class Matriz:
    def __init__(self, pino=7):
        self.np = NeoPixel(Pin(pino), LADO * LADO)
        # Pré-calcula as posições acesas de cada desenho (economiza tempo).
        self._coracao = self._posicoes(DESENHO_CORACAO)
        self._x = self._posicoes(DESENHO_X)
        self._seta = self._posicoes(DESENHO_SETA)
        self.nivel = 0.0            # brilho atual do coração (0 a 1)
        self._ultimo = None         # última cor escrita (evita reescrever igual)

    @staticmethod
    def _posicoes(desenho):
        return [indice(l, c) for l in range(LADO) for c in range(LADO)
                if desenho[l][c] == "#"]

    def _desenhar(self, posicoes, cor):
        if (id(posicoes), cor) == self._ultimo:
            return                  # nada mudou: não precisa reenviar
        self._ultimo = (id(posicoes), cor)
        np = self.np
        np.fill(cores.APAGADO)
        for i in posicoes:
            np[i] = cor
        np.write()

    def apagar(self):
        self._ultimo = None
        self.np.fill(cores.APAGADO)
        self.np.write()

    def batida(self):
        """Chamado a cada batimento: o coração acende no brilho máximo."""
        self.nivel = 1.0

    def atualizar(self, t_ms, com_dedo, erro=False):
        """Chamado ~30x por segundo: anima o coração."""
        if erro:
            self._desenhar(self._x, cores.escalar(cores.VERMELHO, 0.3))
            return
        if not com_dedo:
            # Sem dedo: coração bem fraco, "respirando" devagar.
            fase = (1 + math.sin(2 * math.pi * t_ms / RESPIRAR_PERIODO_MS)) / 2
            nivel = RESPIRAR_MIN + (RESPIRAR_MAX - RESPIRAR_MIN) * fase
            self.nivel = 0.0
        else:
            # Com dedo: depois de cada batida o brilho "apaga" aos poucos,
            # como a luz de um monitor, até o nível de repouso.
            self.nivel *= DECAIMENTO
            nivel = self.nivel if self.nivel > BRILHO_REPOUSO else BRILHO_REPOUSO
        self._desenhar(self._coracao, cores.escalar(cores.CORACAO, nivel))

    def mostrar_seta(self, cor=cores.VERDE):
        """Desenha uma seta para cima: serve para conferir a orientação."""
        self._desenhar(self._seta, cor)


class LedRGB:
    """LED RGB da BitDogLab controlado por PWM (brilho de 0 a 255 por cor)."""

    FREQ_PWM = 1000

    def __init__(self, pino_r=13, pino_g=11, pino_b=12):
        self.canais = [PWM(Pin(p)) for p in (pino_r, pino_g, pino_b)]
        for c in self.canais:
            c.freq(self.FREQ_PWM)
        self.cor = None
        self.definir(cores.APAGADO)

    def definir(self, cor):
        if cor == self.cor:
            return
        self.cor = cor
        for canal, valor in zip(self.canais, cor):
            # duty_u16 vai de 0 a 65535; 255 x 257 = 65535
            canal.duty_u16(valor * 257)

    def desligar(self):
        self.definir(cores.APAGADO)
