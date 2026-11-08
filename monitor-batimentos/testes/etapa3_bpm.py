# testes/etapa3_bpm.py
# ---------------------------------------------------------------------------
# ETAPA 3: detecção de batimentos e BPM.
#
# Mostra uma linha a cada batida detectada, com o intervalo desde a batida
# anterior e o BPM (média dos últimos intervalos). Quando os intervalos
# ficam parecidos entre si, a leitura aparece como "ESTÁVEL".
#
# Como rodar: "MicroPico: Upload project to Pico", abra este arquivo e
# clique em "Run". Apoie o dedo sem apertar e fique parado. Ctrl+C para parar.
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

import config
from max30102 import MAX30102, SensorNaoEncontrado
import sinal

INTERVALO_LEITURA_MS = 10
INTERVALO_STATUS_MS = 1000
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
    print("=" * 52)
    print(" Monitor de Batimentos - Etapa 3 (batimentos e BPM)")
    print(" Projeto educacional, NÃO é aparelho médico.")
    print("=" * 52)

    sensor = iniciar_sensor()
    proc = sinal.ProcessadorSinal(
        taxa_hz=config.TAXA_AMOSTRAGEM_HZ,
        limiar_dedo=config.LIMIAR_DEDO,
        limiar_saida=config.LIMIAR_DEDO_SAIDA,
        alfa=config.ALFA_PASSA_ALTA,
        corte_hz=config.CORTE_PASSA_BAIXA_HZ,
        tempo_estabilizar_ms=config.TEMPO_ESTABILIZAR_MS)
    print("Apoie o dedo sem apertar e fique parado. Ctrl+C para parar.\n")
    gc.collect()

    sensor.limpar_fifo()
    agora = time.ticks_ms()
    ultima_leitura = ultimo_status = agora
    estado_anterior = -1
    batidas = 0

    try:
        while True:
            agora = time.ticks_ms()
            if time.ticks_diff(agora, ultima_leitura) >= INTERVALO_LEITURA_MS:
                ultima_leitura = agora
                for ir, vm in sensor.ler_fifo():
                    estado = proc.processar(ir, vm)
                    if estado != estado_anterior:
                        estado_anterior = estado
                        if estado == sinal.SEM_DEDO:
                            print("\n[sem dedo] Coloque o dedo no sensor")
                            batidas = 0
                        elif estado == sinal.ESTABILIZANDO:
                            print("[medindo] Dedo detectado, estabilizando...")
                        else:
                            print("[pronto] Procurando batidas...")
                        ultimo_status = agora
                    if proc.batimento:
                        batidas += 1
                        det = proc.detector
                        if proc.bpm:
                            print("{} batida {:3d} | intervalo {:4d} ms | BPM {:3d} {}".format(
                                CORACAO, batidas, det.intervalo_ms(), proc.bpm,
                                "ESTÁVEL" if proc.estavel else
                                "(medindo, {} intervalos)".format(len(det.intervalos))))
                        else:
                            print("{} batida {:3d} | aguardando mais batidas...".format(
                                CORACAO, batidas))

            # A cada 5 s: lembra de colocar o dedo e limpa a memória (gc),
            # num momento calmo, fora do processamento das amostras.
            if time.ticks_diff(agora, ultimo_status) >= INTERVALO_STATUS_MS * 5:
                ultimo_status = agora
                if proc.estado == sinal.SEM_DEDO:
                    print("[sem dedo] Coloque o dedo no sensor")
                gc.collect()

            time.sleep_ms(1)
    except KeyboardInterrupt:
        pass
    finally:
        sensor.desligar()
        print("\nSensor desligado. Perdidas: {} | erros I2C: {}".format(
            sensor.amostras_perdidas, sensor.erros_i2c))


main()
