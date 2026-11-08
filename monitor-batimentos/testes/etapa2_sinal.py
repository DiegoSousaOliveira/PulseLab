# testes/etapa2_sinal.py
# ---------------------------------------------------------------------------
# ETAPA 2: detecção do dedo e filtros (passa-alta + passa-baixa).
#
# Três modos de saída (mude SAIDA abaixo):
#   "grafico"  -> desenha a onda PPG com texto, direto no terminal do
#                 MicroPico. Não precisa instalar nada.
#   "resumo"   -> uma linha por segundo com DC, AC, índice de perfusão e uso
#                 de CPU. Bom para calibrar o limiar do dedo.
#   "teleplot" -> formato ">nome:valor" da extensão Teleplot do VS Code.
#
# Como rodar: "MicroPico: Upload project to Pico", abra este arquivo e
# clique em "Run". Ctrl+C para parar.
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

import config
from max30102 import MAX30102, SensorNaoEncontrado
import sinal

# ---- Constantes do teste ---------------------------------------------------
SAIDA = "grafico"            # "grafico" | "resumo" | "teleplot"
INTERVALO_LEITURA_MS = 10    # a FIFO enche em 320 ms; ler a cada 10 ms sobra folga
INTERVALO_STATUS_MS = 1000   # mensagens "coloque o dedo" etc.

# Gráfico de texto
DECIMACAO = 4                # 1 linha a cada 4 amostras (~26 linhas/s)
LARGURA = 41                 # colunas do gráfico (ímpar: o centro é o zero)
DECAIMENTO_ESCALA = 0.98     # a escala "encolhe" 2% por linha se a onda diminuir
BARRA = "█"             # bloco cheio

# Teleplot
DECIMACAO_TELEPLOT = 2       # ~52 pontos/s por curva já fica suave


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


def linha_grafico(valor, escala):
    """Desenha uma barra saindo do centro: para a direita se o valor é
    positivo, para a esquerda se é negativo. Empilhando as linhas, a
    onda do pulso aparece "de lado", descendo pela tela."""
    meio = LARGURA // 2
    pos = int(valor / escala * meio)
    if pos > meio:
        pos = meio
    elif pos < -meio:
        pos = -meio
    if pos >= 0:
        return " " * meio + "|" + BARRA * pos + " " * (meio - pos)
    return " " * (meio + pos) + BARRA * (-pos) + "|" + " " * meio


def main():
    print("=" * 52)
    print(" Monitor de Batimentos - Etapa 2 (dedo e filtros)")
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
    print("Sensor OK. Limiar do dedo: {} (sai abaixo de {})".format(
        proc.limiar_dedo, proc.limiar_saida))
    print("Modo de saída: {}. Ctrl+C para parar.\n".format(SAIDA))
    gc.collect()

    sensor.limpar_fifo()
    agora = time.ticks_ms()
    ultima_leitura = ultimo_status = ultimo_resumo = agora
    estado_anterior = -1

    # Gráfico de texto
    soma = 0.0
    n_soma = 0
    escala = 1.0

    # Resumo
    ac_min = ac_max = 0.0
    tempo_us = 0
    amostras_resumo = 0
    contador_teleplot = 0

    try:
        while True:
            agora = time.ticks_ms()

            if time.ticks_diff(agora, ultima_leitura) >= INTERVALO_LEITURA_MS:
                ultima_leitura = agora
                for ir, vm in sensor.ler_fifo():
                    t0 = time.ticks_us()
                    estado = proc.processar(ir, vm)
                    tempo_us += time.ticks_diff(time.ticks_us(), t0)
                    amostras_resumo += 1
                    ac = proc.ir.ac

                    if estado != sinal.SEM_DEDO:
                        if ac < ac_min: ac_min = ac
                        if ac > ac_max: ac_max = ac

                    if SAIDA == "grafico" and estado == sinal.PRONTO:
                        # Média de DECIMACAO amostras = 1 linha (menos texto,
                        # e a própria média ainda suaviza um pouco mais).
                        soma += ac
                        n_soma += 1
                        if n_soma == DECIMACAO:
                            v = soma / DECIMACAO
                            soma = 0.0
                            n_soma = 0
                            # Escala automática: cresce na hora se a onda
                            # aumentar e encolhe devagar se ela diminuir.
                            escala = max(abs(v), escala * DECAIMENTO_ESCALA, 1.0)
                            pi = 2 * escala / proc.ir.dc * 100
                            print("{} PI~{:.2f}%".format(linha_grafico(v, escala), pi))

                    elif SAIDA == "teleplot":
                        contador_teleplot += 1
                        if contador_teleplot >= DECIMACAO_TELEPLOT:
                            contador_teleplot = 0
                            print(">ir_ac:{:.1f}\n>verm_ac:{:.1f}\n>ir_cru:{}\n>estado:{}".format(
                                proc.ir.ac, proc.vermelho.ac, ir, estado))

                    if estado != estado_anterior:
                        estado_anterior = estado
                        ultimo_status = time.ticks_add(agora, -INTERVALO_STATUS_MS)

            # ---- Mensagens de estado (1 por segundo) -----------------------
            if (SAIDA == "grafico" and proc.estado != sinal.PRONTO and
                    time.ticks_diff(agora, ultimo_status) >= INTERVALO_STATUS_MS):
                ultimo_status = agora
                if proc.estado == sinal.SEM_DEDO:
                    print("[sem dedo] Coloque o dedo no sensor  (IR {:.0f} / limiar {})".format(
                        proc.nivel_dedo, proc.limiar_dedo))
                else:
                    cheio = int(proc.progresso() * 20)
                    print("[medindo]  {}{} {:3.0f}%".format(
                        BARRA * cheio, "." * (20 - cheio), proc.progresso() * 100))
                escala = 1.0

            # ---- Resumo (1 por segundo) ------------------------------------
            decorrido = time.ticks_diff(agora, ultimo_resumo)
            if SAIDA == "resumo" and decorrido >= 1000:
                pp = ac_max - ac_min
                pi = pp / proc.ir.dc * 100 if proc.estado != sinal.SEM_DEDO else 0.0
                print("[{:13s}] IR DC {:6.0f} | VERM DC {:6.0f} | AC p-p {:6.0f} | "
                      "PI {:.2f}% | {:5.1f} am/s | {} us/amostra".format(
                          sinal.NOMES_ESTADO[proc.estado], proc.nivel_dedo,
                          proc.vermelho.dc, pp, pi,
                          amostras_resumo * 1000 / decorrido,
                          tempo_us // max(amostras_resumo, 1)))
                ultimo_resumo = agora
                ac_min = ac_max = 0.0
                tempo_us = amostras_resumo = 0
                gc.collect()   # momento calmo: limpa a memória entre resumos

            time.sleep_ms(1)   # pausa mínima; a FIFO segura 320 ms
    except KeyboardInterrupt:
        pass
    finally:
        sensor.desligar()
        print("\nSensor desligado. Perdidas: {} | erros I2C: {}".format(
            sensor.amostras_perdidas, sensor.erros_i2c))


main()
