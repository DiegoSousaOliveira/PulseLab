# testes/ver_leds.py
# ---------------------------------------------------------------------------
# Confere a olho qual LED do sensor é o vermelho.
#
# O SpO2 depende de saber qual canal é o vermelho e qual é o infravermelho.
# Olhe para a janelinha do sensor (de lado, não direto no olho):
#   1ª fase: LED 1 aceso -> deve aparecer VERMELHO forte.
#   2ª fase: LED 2 aceso -> infravermelho: quase invisível
#            (no máximo um brilho vermelho bem fraco e escuro).
# Se for o contrário, o módulo tem os canais trocados: avise!
# Dica: a câmera do celular enxerga o infravermelho como uma luz roxa/branca.
# ---------------------------------------------------------------------------

import time
from machine import I2C, Pin
import config
from max30102 import MAX30102

CORRENTE_TESTE = 0x60   # 19,2 mA: bem visível, ainda seguro
TEMPO_MS = 5000

sensor = MAX30102(I2C(config.SENSOR_I2C_ID, sda=Pin(config.SENSOR_SDA),
                      scl=Pin(config.SENSOR_SCL), freq=config.SENSOR_I2C_FREQ))
try:
    print("LED 1 (registrador do VERMELHO) aceso por 5 s... deve estar vermelho forte.")
    sensor.definir_correntes(CORRENTE_TESTE, 0)
    time.sleep_ms(TEMPO_MS)
    print("LED 2 (registrador do INFRAVERMELHO) aceso por 5 s... deve estar quase invisível.")
    sensor.definir_correntes(0, CORRENTE_TESTE)
    time.sleep_ms(TEMPO_MS)
finally:
    sensor.desligar()
    print("Pronto. Sensor desligado.")
