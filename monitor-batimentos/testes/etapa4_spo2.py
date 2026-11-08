# testes/etapa4_spo2.py
# ---------------------------------------------------------------------------
# ETAPA 4: BPM + SpO2 aproximado (razão das razões).
#
# A cada batida mostra o BPM, o SpO2 e os números usados na conta:
#   R  = razão das razões (veja lib/sinal.py, classe CalculadoraSpO2)
#   PI = índice de perfusão = tamanho do pulso / nível médio, no IR.
#        PI muito baixo (< 0,2%) = pulso fraco: dedo frio ou apertado demais.
#
# Para calibrar o SpO2 (config.py: SPO2_A e SPO2_B), compare com um
# oxímetro de dedo comercial na mesma pessoa, em repouso.
#
# Projeto EDUCACIONAL: o SpO2 mostrado é aproximado e NÃO serve para
# nenhuma decisão de saúde.
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

import config
from max30102 import MAX30102, SensorNaoEncontrado
import sinal

INTERVALO_LEITURA_MS = 10
CORACAO = "♥"


def iniciar_sensor():
    i2c = I2C(config.SENSOR_I2C_ID, sda=Pin(config.SENSOR_SDA),
              scl=Pin(config.SENSOR_SCL), freq=config.SENSOR_I2C_FREQ)
    if 0x57 not in i2c.scan():
        print("ERRO: MAX30102 não encontrado. Rode a Etapa 1 para diagnosticar.")
        raise SystemExit
    try:
        return MAX30102(i2c, config.LED_VERMELHO, config.LED_IR)
    except SensorNaoEncontrado as e:
        print("ERRO: {}".format(e))
        raise SystemExit


def main():
    print("=" * 56)
    print(" Monitor de Batimentos - Etapa 4 (BPM e SpO2)")
    print(" Projeto educacional, NÃO é aparelho médico.")
    print("=" * 56)

    sensor = iniciar_sensor()
    proc = sinal.ProcessadorSinal(
        taxa_hz=config.TAXA_AMOSTRAGEM_HZ,
        limiar_dedo=config.LIMIAR_DEDO,
        limiar_saida=config.LIMIAR_DEDO_SAIDA,
        alfa=config.ALFA_PASSA_ALTA,
        corte_hz=config.CORTE_PASSA_BAIXA_HZ,
        tempo_estabilizar_ms=config.TEMPO_ESTABILIZAR_MS,
        spo2_a=config.SPO2_A, spo2_b=config.SPO2_B,
        spo2_modelo=config.SPO2_MODELO)
    if config.SPO2_MODELO == "maxim":
        print("SpO2 pela curva da Maxim: -45,060·R² + 30,354·R + 94,845")
    else:
        print("SpO2 = {} - {} x R".format(config.SPO2_A, config.SPO2_B))
    if config.SPO2_PRESUMIDO:
        print("ATENÇÃO: calibração PRESUMIDA (R {} = {}% em repouso), não medida.".format(
            config.R_REPOUSO, config.SPO2_REFERENCIA))
    print("Apoie o dedo sem apertar. Ctrl+C para parar.\n")
    gc.collect()

    sensor.limpar_fifo()
    ultima_leitura = ultimo_gc = time.ticks_ms()
    estado_anterior = -1

    try:
        while True:
            agora = time.ticks_ms()
            if time.ticks_diff(agora, ultima_leitura) >= INTERVALO_LEITURA_MS:
                ultima_leitura = agora
                for ir, vm in sensor.ler_fifo():
                    estado = proc.processar(ir, vm)
                    if estado != estado_anterior:
                        estado_anterior = estado
                        print(("\n[sem dedo] Coloque o dedo no sensor",
                               "[medindo] Dedo detectado, estabilizando...",
                               "[pronto] Procurando batidas...")[estado])
                    if proc.batimento:
                        ox = proc.oximetro
                        # altura típica do pico x 2 ≈ pico-a-vale do pulso
                        pi = 2 * proc.detector.amplitude / proc.ir.dc * 100
                        texto_bpm = "{:3d}".format(proc.bpm) if proc.bpm else "---"
                        texto_spo2 = ("{:3d}%".format(proc.spo2) if proc.spo2
                                      else " ---")
                        print("{} BPM {} {} | SpO2 ~{} (R {:.2f}) | PI {:.2f}%".format(
                            CORACAO, texto_bpm,
                            "ESTÁVEL " if proc.estavel else "medindo",
                            texto_spo2, ox.r, pi))

            # Limpa a memória a cada 5 s, num momento calmo.
            if time.ticks_diff(agora, ultimo_gc) >= 5000:
                ultimo_gc = agora
                gc.collect()
            time.sleep_ms(1)
    except KeyboardInterrupt:
        pass
    finally:
        sensor.desligar()
        print("\nSensor desligado. Perdidas: {} | erros I2C: {}".format(
            sensor.amostras_perdidas, sensor.erros_i2c))


main()
