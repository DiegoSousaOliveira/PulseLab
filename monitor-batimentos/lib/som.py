# lib/som.py
# ---------------------------------------------------------------------------
# Buzzer não bloqueante: bipe curto a cada batimento, como num monitor de
# hospital.
#
# POR QUE "NÃO BLOQUEANTE"? Um bipe de 60 ms com time.sleep_ms(60) pararia
# o programa inteiro (e a leitura do sensor) durante o bipe. Aqui, bipe()
# só LIGA o som e anota a hora de desligar; atualizar(), chamado a cada
# ~10 ms pelo laço principal, desliga quando chegar a hora.
#
# O buzzer passivo da BitDogLab precisa de uma onda quadrada: o PWM gera
# essa onda sozinho, no hardware, na frequência (tom) escolhida.
# ---------------------------------------------------------------------------

import time
from machine import Pin, PWM

FREQ_BATIDA = 1000           # Hz: o "bip" clássico de monitor
DURACAO_BATIDA_MS = 60
VOLUME = 0.15                # 0 a 1 (fração do ciclo do PWM); 0.5 = mais alto


class Buzzer:
    def __init__(self, pino=21, volume=VOLUME):
        self.pwm = PWM(Pin(pino))
        self.pwm.duty_u16(0)
        self.volume = volume
        self.ligado = True       # botão A liga/desliga
        self._fim = None         # quando o bipe atual deve parar
        self._fila = []          # próximas notas de uma sequência

    def bipe(self, freq=FREQ_BATIDA, duracao_ms=DURACAO_BATIDA_MS, forcar=False):
        """Começa um bipe e volta na hora (não espera ele terminar)."""
        if not self.ligado and not forcar:
            return
        self._fila = []
        self.pwm.freq(freq)
        self.pwm.duty_u16(int(65535 * self.volume))
        self._fim = time.ticks_add(time.ticks_ms(), duracao_ms)

    def sequencia(self, notas):
        """Toca várias notas em seguida, sem bloquear.
        notas = [(freq_hz, duracao_ms, pausa_ms), ...]  (freq 0 = silêncio)"""
        if not self.ligado:
            return
        self._fila = list(notas)
        self._proxima_nota()

    def _proxima_nota(self):
        freq, duracao, pausa = self._fila.pop(0)
        if freq:
            self.pwm.freq(freq)
            self.pwm.duty_u16(int(65535 * self.volume))
        else:
            self.pwm.duty_u16(0)
        self._fim = time.ticks_add(time.ticks_ms(), duracao)
        if pausa:
            self._fila.insert(0, (0, pausa, 0))     # a pausa vira uma "nota muda"

    def atualizar(self):
        """Desliga o bipe (ou passa para a próxima nota) quando o tempo acaba.
        Chame com frequência (a cada ~10 ms)."""
        if self._fim is not None and time.ticks_diff(time.ticks_ms(), self._fim) >= 0:
            if self._fila:
                self._proxima_nota()
            else:
                self.pwm.duty_u16(0)
                self._fim = None

    def alternar(self):
        """Liga/desliga o som. Devolve o novo estado."""
        self.ligado = not self.ligado
        if self.ligado:
            self.bipe(1500, 40)      # confirma com um bipe agudo curto
        else:
            self.pwm.duty_u16(0)
            self._fim = None
            self._fila = []
        return self.ligado

    def desligar(self):
        self.pwm.duty_u16(0)
        self._fim = None
        self._fila = []
