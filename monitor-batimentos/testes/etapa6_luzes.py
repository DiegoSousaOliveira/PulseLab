# testes/etapa6_luzes.py
# ---------------------------------------------------------------------------
# ETAPA 6: matriz 5x5, LED RGB, buzzer e botão A - sem precisar do sensor.
#
# Olhe para a placa enquanto o teste roda:
#   1. Matriz: uma SETA VERDE apontando para CIMA (lado do OLED).
#      Se aparecer de ponta-cabeça ou espelhada, ajuste INVERTER_LINHAS /
#      INVERTER_COLUNAS em lib/matriz.py.
#   2. LED RGB: azul -> verde -> laranja -> vermelho (as 4 faixas de BPM).
#   3. Buzzer: 3 bipes de monitor.
#   4. Coração da matriz batendo a 70 BPM, com bipe, por 6 s.
#   5. Botão A: aperte algumas vezes em 8 s (liga/desliga o som).
# ---------------------------------------------------------------------------

import time
import config
import cores
from matriz import Matriz, LedRGB
from som import Buzzer
from machine import Pin

matriz = Matriz(config.MATRIZ_PINO)
rgb = LedRGB(config.LED_R_PINO, config.LED_G_PINO, config.LED_B_PINO)
buzzer = Buzzer(config.BUZZER_PINO, config.SOM_VOLUME)


def esperar_ms(ms):
    """Espera sem travar o buzzer (o bipe precisa ser desligado no tempo)."""
    fim = time.ticks_add(time.ticks_ms(), ms)
    while time.ticks_diff(fim, time.ticks_ms()) > 0:
        buzzer.atualizar()
        time.sleep_ms(5)


try:
    print("1) Matriz: seta verde apontando para CIMA (lado do OLED)?")
    matriz.mostrar_seta()
    esperar_ms(3000)

    print("2) LED RGB: as 4 faixas de BPM")
    for nome, bpm in (("azul (< 60)", 50), ("verde (60-100)", 75),
                      ("laranja (100-140)", 120), ("vermelho (> 140)", 160)):
        print("   ", nome)
        rgb.definir(cores.cor_da_faixa(bpm))
        esperar_ms(1200)
    rgb.desligar()

    print("3) Buzzer: 3 bipes")
    for _ in range(3):
        buzzer.bipe()
        esperar_ms(500)

    print("4) Coração batendo a 70 BPM por 6 s")
    rgb.definir(cores.cor_da_faixa(70))
    inicio = proxima = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), inicio) < 6000:
        agora = time.ticks_ms()
        if time.ticks_diff(agora, proxima) >= 0:
            matriz.batida()
            buzzer.bipe()
            proxima = time.ticks_add(proxima, 60000 // 70)
        matriz.atualizar(agora, com_dedo=True)
        esperar_ms(30)
    rgb.desligar()

    print("5) Aperte o botão A algumas vezes (8 s)...")
    botao = Pin(config.BOTAO_A_PINO, Pin.IN, Pin.PULL_UP)
    anterior = 1
    ultimo = time.ticks_ms()
    inicio = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), inicio) < 8000:
        v = botao.value()
        agora = time.ticks_ms()
        if v == 0 and anterior == 1 and time.ticks_diff(agora, ultimo) > 250:
            ultimo = agora
            print("   som", "LIGADO" if buzzer.alternar() else "DESLIGADO")
        anterior = v
        matriz.atualizar(agora, com_dedo=False)
        esperar_ms(20)
    print("Fim do teste.")
finally:
    buzzer.desligar()
    matriz.apagar()
    rgb.desligar()
