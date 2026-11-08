# lib/desafio.py
# ---------------------------------------------------------------------------
# DESAFIO DO PÁTIO: quanto o coração acelera com exercício e quanto tempo
# ele leva para voltar perto do repouso?
#
#   Botão B ──> 1/3 REPOUSO      mede o BPM parado por 15 s
#           ──> 2/3 EXERCÍCIO    tira o dedo e pula por 30 s (contagem)
#           ──> 3/3 RECUPERAÇÃO  põe o dedo de novo; acha o PICO do BPM e
#                                cronometra até ele voltar perto do repouso
#           ──> RESULTADO        repouso, pico, aumento e tempo de recuperação
#
# "Perto do repouso" = no máximo MARGEM acima do BPM de repouso, confirmado
# em algumas batidas seguidas (para um valor solto não encerrar o desafio).
# O tempo de recuperação é contado a partir do FIM do exercício.
#
# Este módulo não mexe em hardware: só recebe (hora, dedo, BPM, batida) e
# decide a fase. Assim ele pode ser testado no computador.
#
# PRIVACIDADE: nenhum nome ou identificação é pedido ou guardado; os
# números ficam só na memória e somem quando o desafio recomeça.
# ---------------------------------------------------------------------------

import time

INATIVO = 0
REPOUSO_ESPERA = 1       # esperando dedo + primeiro BPM
REPOUSO_MEDINDO = 2      # contando os 15 s de repouso
EXERCICIO = 3            # contagem regressiva do exercício
VOLTA_ESPERA = 4         # esperando o dedo voltar depois do exercício
RECUPERACAO = 5          # acompanhando o BPM até voltar perto do repouso
RESULTADO = 6

REPOUSO_S = 15
EXERCICIO_S = 30
MARGEM_BPM_MIN = 5          # "perto" = até repouso + 5 BPM ...
MARGEM_FRACAO = 0.10        # ... ou + 10% do repouso, o que for maior
BATIDAS_CONFIRMAR = 3       # batidas seguidas dentro da margem para confirmar
JANELA_PICO_S = 20          # o pico é procurado nos primeiros 20 s de leitura
RECUPERACAO_MAX_S = 180     # desiste depois de 3 min sem voltar ao repouso
AVISOS_FINAIS_S = 3         # bipes nos 3 últimos segundos do exercício


def mediana(valores):
    o = sorted(valores)
    return o[len(o) // 2]


def formatar_tempo(segundos):
    """125 -> "2:05" """
    segundos = int(segundos)
    return "{}:{:02d}".format(segundos // 60, segundos % 60)


class Desafio:
    def __init__(self, repouso_s=REPOUSO_S, exercicio_s=EXERCICIO_S):
        self.repouso_s = repouso_s
        self.exercicio_s = exercicio_s
        self.cancelar()

    # ---------------------------------------------------------- comandos
    def cancelar(self):
        self.estado = INATIVO
        self.bpm_repouso = 0
        self.bpm_pico = 0
        self.recuperacao_s = None      # None = não voltou ao repouso a tempo
        self._valores = []
        self._inicio = 0
        self._fim_exercicio = 0
        self._primeira_leitura = None
        self._confirmacoes = 0
        self._ultimo_aviso = -1

    @property
    def ativo(self):
        return self.estado != INATIVO

    def botao_b(self, agora):
        """Botão B: inicia, encerra o exercício antes da hora, ou sai."""
        if self.estado == INATIVO:
            self.cancelar()
            self.estado = REPOUSO_ESPERA
            return "inicio"
        if self.estado == EXERCICIO:
            self._terminar_exercicio(agora)    # "já pulei o suficiente"
            return "fase"
        self.cancelar()                         # resultado visto, ou desistiu
        return "saiu"

    # ---------------------------------------------------------- consultas
    def decorrido_s(self, agora):
        return time.ticks_diff(agora, self._inicio) / 1000

    def restante_s(self, agora):
        total = self.repouso_s if self.estado == REPOUSO_MEDINDO else self.exercicio_s
        r = total - self.decorrido_s(agora)
        return r if r > 0 else 0

    def desde_exercicio_s(self, agora):
        return time.ticks_diff(agora, self._fim_exercicio) / 1000

    def limite_bpm(self):
        """BPM máximo para considerar que voltou "perto do repouso"."""
        margem = self.bpm_repouso * MARGEM_FRACAO
        if margem < MARGEM_BPM_MIN:
            margem = MARGEM_BPM_MIN
        return int(self.bpm_repouso + margem + 0.5)

    @property
    def aumento(self):
        return self.bpm_pico - self.bpm_repouso

    # ---------------------------------------------------------- máquina de estados
    def atualizar(self, agora, com_dedo, bpm, batida):
        """Chamado a cada leitura do sensor. Devolve um evento para sons:
        "fase" (mudou de fase), "contagem" (últimos segundos), "fim" ou None."""
        e = self.estado

        if e == REPOUSO_ESPERA:
            if com_dedo and bpm:
                self.estado = REPOUSO_MEDINDO
                self._inicio = agora
                self._valores = [bpm]
                return "fase"

        elif e == REPOUSO_MEDINDO:
            if not com_dedo or not bpm:
                self.estado = REPOUSO_ESPERA   # dedo saiu: recomeça a contagem
                return None
            if batida:
                self._valores.append(bpm)
            if self.decorrido_s(agora) >= self.repouso_s:
                # Mediana: uma leitura estranha não estraga o repouso.
                self.bpm_repouso = mediana(self._valores)
                self.estado = EXERCICIO
                self._inicio = agora
                self._ultimo_aviso = -1
                return "fase"

        elif e == EXERCICIO:
            restante = self.restante_s(agora)
            if restante <= 0:
                self._terminar_exercicio(agora)
                return "fase"
            segundo = int(restante) + 1
            if segundo <= AVISOS_FINAIS_S and segundo != self._ultimo_aviso:
                self._ultimo_aviso = segundo
                return "contagem"

        elif e == VOLTA_ESPERA:
            if com_dedo and bpm:
                self.estado = RECUPERACAO
                self._primeira_leitura = agora
                self.bpm_pico = bpm
                self._confirmacoes = 0
                return "fase"
            if self.desde_exercicio_s(agora) > RECUPERACAO_MAX_S:
                self.estado = RESULTADO
                return "fim"

        elif e == RECUPERACAO:
            if self.desde_exercicio_s(agora) > RECUPERACAO_MAX_S:
                self.estado = RESULTADO        # recuperacao_s fica None
                return "fim"
            if batida and bpm:
                # O pico costuma vir logo que o dedo volta; depois só desce.
                if (time.ticks_diff(agora, self._primeira_leitura) <= JANELA_PICO_S * 1000
                        and bpm > self.bpm_pico):
                    self.bpm_pico = bpm
                if bpm <= self.limite_bpm():
                    self._confirmacoes += 1
                    if self._confirmacoes >= BATIDAS_CONFIRMAR:
                        self.recuperacao_s = self.desde_exercicio_s(agora)
                        self.estado = RESULTADO
                        return "fim"
                else:
                    self._confirmacoes = 0
        return None

    def _terminar_exercicio(self, agora):
        self.estado = VOLTA_ESPERA
        self._fim_exercicio = agora

    # ---------------------------------------------------------- textos
    def titulo(self):
        return ("", "DESAFIO 1/3", "REPOUSO", "DESAFIO 2/3", "DESAFIO 3/3",
                "ALVO {}".format(self.limite_bpm()), "RESULTADO")[self.estado]

    def resumo(self):
        rec = (formatar_tempo(self.recuperacao_s) if self.recuperacao_s is not None
               else "mais de " + formatar_tempo(RECUPERACAO_MAX_S))
        return "Repouso {} BPM | pico {} BPM | aumento {:+d} BPM | recuperação {}".format(
            self.bpm_repouso, self.bpm_pico, self.aumento, rec)
