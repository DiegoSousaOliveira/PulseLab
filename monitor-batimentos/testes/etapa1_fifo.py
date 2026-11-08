# testes/etapa1_fifo.py
# ---------------------------------------------------------------------------
# ETAPA 1: scan I2C, conferir o PART_ID e mostrar a leitura crua da FIFO
# do MAX30102 no terminal.
#
# Como rodar (MicroPico no VS Code):
#   1. "MicroPico: Upload project to Pico" (envia lib/, config.py e testes/).
#   2. Abra este arquivo e clique em "Run" na barra de status
#      (ou "MicroPico: Run current file on Pico").
#   3. Ctrl+C no terminal do MicroPico para parar.
#
# Pelo REPL (>>>) também funciona:  import testes.etapa1_fifo
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

# ---- Constantes do teste ---------------------------------------------------
MODO_SAIDA = "resumo"        # "resumo" = 1 linha por segundo | "cru" = toda amostra
INTERVALO_RESUMO_MS = 1000
INTERVALO_LEITURA_MS = 10    # a FIFO enche em 320 ms; ler a cada 10 ms sobra folga
FRACAO_SATURACAO = 0.99      # acima de 99% do fundo de escala = saturado

# OLED da BitDogLab (só para conferir a pinagem)
OLED_I2C_ID = 1
OLED_SDA = 14
OLED_SCL = 15
OLED_ENDERECO = 0x3C
SENSOR_ENDERECO = 0x57

DICA_SEM_SENSOR = """
  >> Dicas:
     - Confira se o cabo está no conector I2C externo (I2C0: GP0/GP1).
     - Confira VCC (3,3 V), GND, SDA e SCL (SDA e SCL não podem estar trocados).
     - Alguns módulos roxos têm os resistores de pull-up do I2C ligados em
       1,8 V. Eles precisam ir para 3,3 V (ou ser removidos). Veja o README.
"""

try:
    import config
except ImportError:
    print("ERRO: config.py não está na placa. Faça o Upload project.")
    raise SystemExit

try:
    from max30102 import MAX30102, SensorNaoEncontrado, VALOR_MAXIMO
except ImportError:
    print("ERRO: lib/max30102.py não está na placa. Faça o Upload project.")
    raise SystemExit


def scan(nome, i2c):
    enderecos = i2c.scan()
    texto = ", ".join("0x{:02X}".format(a) for a in enderecos) or "nenhum"
    print("Scan {}: {}".format(nome, texto))
    return enderecos


def main():
    print("=" * 52)
    print(" Monitor de Batimentos - Etapa 1 (teste do sensor)")
    print(" Projeto educacional, NÃO é aparelho médico.")
    print("=" * 52)

    # ---- OLED: só confirma a pinagem da placa ------------------------------
    i2c_oled = I2C(OLED_I2C_ID, sda=Pin(OLED_SDA), scl=Pin(OLED_SCL), freq=400000)
    if OLED_ENDERECO not in scan("I2C1 (OLED, GP14/GP15)", i2c_oled):
        print("  AVISO: OLED não encontrado em 0x3C.")
    del i2c_oled

    # ---- Sensor ------------------------------------------------------------
    i2c = I2C(config.SENSOR_I2C_ID, sda=Pin(config.SENSOR_SDA),
              scl=Pin(config.SENSOR_SCL), freq=config.SENSOR_I2C_FREQ)
    if SENSOR_ENDERECO not in scan("I2C0 (sensor, GP0/GP1)", i2c):
        print("\nERRO: MAX30102 (0x57) não encontrado." + DICA_SEM_SENSOR)
        return
    try:
        sensor = MAX30102(i2c, config.LED_VERMELHO, config.LED_IR)
    except SensorNaoEncontrado as e:
        print("\nERRO:", e, DICA_SEM_SENSOR)
        return

    print("  PART_ID 0x{:02X} | REV_ID 0x{:02X} | MAX30102 OK".format(
        sensor.part_id, sensor.rev_id))
    print("  LEDs: vermelho {:.1f} mA | IR {:.1f} mA".format(
        config.LED_VERMELHO * 0.2, config.LED_IR * 0.2))
    temp = sensor.ler_temperatura()
    if temp is not None:
        print("  Temperatura do chip: {:.1f} °C".format(temp))
    gc.collect()
    print("  Memória livre: {} bytes".format(gc.mem_free()))
    print("\nLendo a FIFO... Teste SEM dedo e depois COM o dedo. Ctrl+C para parar.\n")
    if MODO_SAIDA == "cru":
        print("ir vermelho")

    limite = int(VALOR_MAXIMO * FRACAO_SATURACAO)
    sensor.limpar_fifo()
    inicio = ultimo_resumo = ultima_leitura = time.ticks_ms()
    contagem = total = 0
    ir_min = vm_min = VALOR_MAXIMO
    ir_max = vm_max = 0
    ultimo = (0, 0)

    try:
        while True:
            agora = time.ticks_ms()

            # Lê a FIFO em intervalos medidos com ticks_ms(), sem depender
            # de quanto tempo o print levou.
            if time.ticks_diff(agora, ultima_leitura) >= INTERVALO_LEITURA_MS:
                ultima_leitura = agora
                amostras = sensor.ler_fifo()
                for ir, vm in amostras:
                    if MODO_SAIDA == "cru":
                        print(ir, vm)
                    if ir < ir_min: ir_min = ir
                    if ir > ir_max: ir_max = ir
                    if vm < vm_min: vm_min = vm
                    if vm > vm_max: vm_max = vm
                if amostras:
                    ultimo = amostras[-1]
                    contagem += len(amostras)

            decorrido = time.ticks_diff(agora, ultimo_resumo)
            if MODO_SAIDA == "resumo" and decorrido >= INTERVALO_RESUMO_MS:
                total += contagem
                print("[{:4d}s] {:5.1f} am/s | IR {:6d} ({:6d}-{:6d}) | "
                      "VERM {:6d} ({:6d}-{:6d}) | perdidas {} | erros I2C {}".format(
                          time.ticks_diff(agora, inicio) // 1000,
                          contagem * 1000 / decorrido,
                          ultimo[0], ir_min, ir_max, ultimo[1], vm_min, vm_max,
                          sensor.amostras_perdidas, sensor.erros_i2c))
                if ir_max >= limite or vm_max >= limite:
                    print("        ^ SATURADO: diminua LED_IR / LED_VERMELHO no config.py")
                ultimo_resumo = agora
                contagem = 0
                ir_min = vm_min = VALOR_MAXIMO
                ir_max = vm_max = 0
                gc.collect()   # momento calmo: limpa a memória entre resumos

            time.sleep_ms(1)   # pausa mínima; a FIFO segura 320 ms
    except KeyboardInterrupt:
        pass
    finally:
        sensor.desligar()
        print("\nSensor desligado. Amostras: {} | perdidas: {} | erros I2C: {}".format(
            total + contagem, sensor.amostras_perdidas, sensor.erros_i2c))


main()
