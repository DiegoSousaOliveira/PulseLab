# testes/experimento_spo2.py
# ---------------------------------------------------------------------------
# EXPERIMENTO: o que muda a razão R (e portanto o SpO2) deste sensor?
#
# Mede 25 s em 3 condições e mostra uma tabela no final. Siga as instruções
# que aparecem no terminal. Em cada fase:
#   1. coloque o dedo como pedido;  2. fique parado;  3. tire quando pedir.
# Na fase A, no final, os LEDs do sensor apagam por 5 s (deixe o dedo!):
# assim medimos quanta luz da SALA chega ao sensor através do dedo.
#
# Por que isso importa: a fórmula do SpO2 supõe que só o sangue que pulsa
# muda a luz. Luz ambiente vazando, pressão do dedo ou um LED fora da faixa
# também mudam o R. Descobrindo o que deixa o R estável, sabemos como
# usar o sensor na apresentação.
#
# Projeto EDUCACIONAL: NÃO é aparelho médico.
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

import config
from max30102 import MAX30102
import sinal

SEGUNDOS_POR_FASE = 25
SEGUNDOS_LEDS_APAGADOS = 5
ESPERA_DEDO_MS = 90000       # tempo máximo esperando o dedo em cada fase

# (letra, instrução, correntes (vermelho, IR) ou None = as do config.py,
#  medir luz ambiente no final?)
FASES = (
    ("A", "Dedo LEVE (só encostado, sem apertar)", None, True),
    ("B", "Dedo com PRESSÃO firme (aperte um pouco)", None, False),
    ("C", "Dedo LEVE, LEDs mais FORTES (12,8 mA)", (0x40, 0x40), False),
)


def criar():
    i2c = I2C(config.SENSOR_I2C_ID, sda=Pin(config.SENSOR_SDA),
              scl=Pin(config.SENSOR_SCL), freq=config.SENSOR_I2C_FREQ)
    sensor = MAX30102(i2c, config.LED_VERMELHO, config.LED_IR)
    proc = sinal.ProcessadorSinal(
        taxa_hz=config.TAXA_AMOSTRAGEM_HZ, limiar_dedo=config.LIMIAR_DEDO,
        limiar_saida=config.LIMIAR_DEDO_SAIDA, alfa=config.ALFA_PASSA_ALTA,
        corte_hz=config.CORTE_PASSA_BAIXA_HZ,
        tempo_estabilizar_ms=config.TEMPO_ESTABILIZAR_MS)
    return sensor, proc


def quartis(lista):
    o = sorted(lista)
    n = len(o)
    return o[n // 4], o[n // 2], o[(3 * n) // 4]


def esperar(sensor, proc, condicao, limite_ms, mostrar_nivel=False):
    """Lê o sensor até condicao(proc) ser verdadeira. False se estourar o tempo.
    Com mostrar_nivel=True, imprime o nível do IR a cada 2 s (para você ver
    se o sensor está "enxergando" o dedo)."""
    inicio = ultimo = time.ticks_ms()
    while not condicao(proc):
        agora = time.ticks_ms()
        if time.ticks_diff(agora, inicio) > limite_ms:
            return False
        for ir, vm in sensor.ler_fifo():
            proc.processar(ir, vm)
        if mostrar_nivel and time.ticks_diff(agora, ultimo) >= 2000:
            ultimo = agora
            print("   nível IR {:6.0f} (precisa passar de {}) | {}".format(
                proc.nivel_dedo, proc.limiar_dedo, sinal.NOMES_ESTADO[proc.estado]))
        time.sleep_ms(10)
    return True


def medir_fase(sensor, proc, segundos):
    """Mede durante `segundos` com o sinal pronto. Devolve um dicionário."""
    razoes, pis = [], []
    soma_dc_ir = soma_dc_vm = 0.0
    n_dc = 0
    contagem = proc.oximetro.contagem
    inicio = ultimo_aviso = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), inicio) < segundos * 1000:
        for ir, vm in sensor.ler_fifo():
            if proc.processar(ir, vm) == sinal.SEM_DEDO:
                return None                       # dedo saiu no meio
            soma_dc_ir += proc.ir.dc
            soma_dc_vm += proc.vermelho.dc
            n_dc += 1
            if proc.batimento:
                pis.append(2 * proc.detector.amplitude / proc.ir.dc * 100)
            if proc.oximetro.contagem != contagem:
                contagem = proc.oximetro.contagem
                razoes.append(proc.oximetro.r_batida)
        agora = time.ticks_ms()
        if time.ticks_diff(agora, ultimo_aviso) >= 5000:
            ultimo_aviso = agora
            restam = segundos - time.ticks_diff(agora, inicio) // 1000
            print("   ... medindo, faltam {} s | batidas com R: {} | BPM {}".format(
                restam, len(razoes), proc.bpm or "--"))
        time.sleep_ms(10)
    return {"razoes": razoes, "pis": pis, "bpm": proc.bpm,
            "dc_ir": soma_dc_ir / max(n_dc, 1), "dc_vm": soma_dc_vm / max(n_dc, 1)}


def medir_luz_ambiente(sensor, segundos):
    """Apaga os LEDs e mede o que chega ao sensor só com a luz da sala.
    O MAX30102 tem um circuito que desconta a luz ambiente; se ele estiver
    funcionando bem, a leitura fica perto de zero mesmo com a sala acesa."""
    sensor.definir_correntes(0, 0)
    time.sleep_ms(200)
    sensor.ler_fifo()                             # descarta o que estava na fila
    ir_min = vm_min = 1 << 20
    ir_max = vm_max = 0
    soma_ir = soma_vm = n = 0
    inicio = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), inicio) < segundos * 1000:
        for ir, vm in sensor.ler_fifo():
            soma_ir += ir
            soma_vm += vm
            n += 1
            ir_min = min(ir_min, ir); ir_max = max(ir_max, ir)
            vm_min = min(vm_min, vm); vm_max = max(vm_max, vm)
        time.sleep_ms(10)
    sensor.definir_correntes(config.LED_VERMELHO, config.LED_IR)
    if not n:
        return None
    return (soma_ir / n, ir_max - ir_min, soma_vm / n, vm_max - vm_min)


def main():
    print("=" * 60)
    print(" Experimento: o que muda a razão R do SpO2?")
    print(" Projeto educacional, NÃO é aparelho médico.")
    print("=" * 60)
    sensor, proc = criar()
    calc_lin = sinal.CalculadoraSpO2(config.SPO2_A, config.SPO2_B, "linear")
    calc_max = sinal.CalculadoraSpO2(modelo="maxim")
    resultados = []
    ambiente = None

    try:
        for letra, descricao, correntes, medir_ambiente in FASES:
            print("\n>>> FASE {}: {}".format(letra, descricao))
            if correntes:
                sensor.definir_correntes(*correntes)
            else:
                sensor.definir_correntes(config.LED_VERMELHO, config.LED_IR)
            sensor.limpar_fifo()
            print("   Coloque o dedo agora...")
            if not esperar(sensor, proc, lambda p: p.estado == sinal.PRONTO,
                           ESPERA_DEDO_MS, mostrar_nivel=True):
                print("   Sem dedo: fase pulada.")
                resultados.append((letra, None))
                continue
            print("   Dedo OK. Fique PARADO por {} s.".format(SEGUNDOS_POR_FASE))
            r = medir_fase(sensor, proc, SEGUNDOS_POR_FASE)
            if r is None:
                print("   O dedo saiu no meio: fase perdida.")
            resultados.append((letra, r))
            if medir_ambiente and r is not None:
                print("   NÃO tire o dedo: LEDs apagados por {} s (medindo a luz da sala)...".format(
                    SEGUNDOS_LEDS_APAGADOS))
                ambiente = medir_luz_ambiente(sensor, SEGUNDOS_LEDS_APAGADOS)
            print("   Pronto! TIRE o dedo.")
            esperar(sensor, proc, lambda p: p.estado == sinal.SEM_DEDO, 60000)
            time.sleep_ms(1500)
            gc.collect()
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        sensor.desligar()

    print("\n" + "=" * 86)
    print(" Fase | batidas | R mediana (quartis) | PI    | BPM | SpO2 linear | SpO2 Maxim | DC IR/VERM")
    print("-" * 86)
    for letra, r in resultados:
        if not r or len(r["razoes"]) < 3:
            print("  {}   | sem dados suficientes".format(letra))
            continue
        q1, med, q3 = quartis(r["razoes"])
        pi = quartis(r["pis"])[1] if r["pis"] else 0
        print("  {}   |  {:3d}    | {:.2f} ({:.2f}-{:.2f})    | {:.2f}% | {:3d} |    {:5.1f}    |   {:5.1f}    | {:.0f}/{:.0f}".format(
            letra, len(r["razoes"]), med, q1, q3, pi, r["bpm"],
            calc_lin.converter(med), calc_max.converter(med), r["dc_ir"], r["dc_vm"]))
    print("-" * 86)
    if ambiente:
        print(" Luz da sala com LEDs apagados (dedo no sensor):")
        print("   IR média {:.0f} (variação {}) | VERM média {:.0f} (variação {})".format(*ambiente))
    print("=" * 86)
    print("Copie esta tabela e mande para análise.")


main()
