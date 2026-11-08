# main.py
# ---------------------------------------------------------------------------
# Monitor de Batimentos - BitDogLab + MAX30102
# Projeto EDUCACIONAL: NÃO é aparelho médico.
#
# COMO O PROGRAMA SE ORGANIZA (asyncio = várias "tarefas" revezando a CPU):
#
#   tarefa_sensor  (a cada 10 ms)  lê a FIFO do sensor e processa cada
#                                  amostra: filtros, batimentos, SpO2.
#                                  A cada batida: bipe + coração da matriz.
#   tarefa_tela    (a cada 100 ms) desenha o OLED (no máximo 10x por segundo).
#   tarefa_luzes   (a cada 30 ms)  anima a matriz 5x5 e o LED RGB.
#   tarefa_botoes  (a cada 20 ms)  botão A = som liga/desliga;
#                                  botão B = Desafio do Pátio (lib/desafio.py).
#   tarefa_ble     (a cada 50 ms)  painel por Bluetooth (lib/painel_ble.py):
#                                  envia as leituras para web/index.html.
#
# Nenhuma tarefa usa sleep() bloqueante: elas usam "await asyncio.sleep_ms()",
# que devolve a CPU para a outra tarefa enquanto espera. A FIFO do sensor
# guarda 320 ms de amostras, então mesmo quando a tela leva ~35 ms para ser
# enviada, nenhuma amostra se perde.
# ---------------------------------------------------------------------------

import gc
import time
from machine import I2C, Pin

try:
    import asyncio
except ImportError:              # firmwares antigos chamavam de uasyncio
    import uasyncio as asyncio

import config
import cores
import sinal
from max30102 import MAX30102, SensorNaoEncontrado, ENDERECO
from matriz import Matriz, LedRGB
from som import Buzzer
import desafio as dsf

# ---- Constantes ------------------------------------------------------------
INTERVALO_SENSOR_MS = 10       # leitura da FIFO (enche em 320 ms)
INTERVALO_TELA_MS = 100        # 10 quadros por segundo
INTERVALO_ABERTURA_MS = 40     # animação de abertura mais fluida
DECIMACAO_ONDA = 4             # 1 ponto da onda a cada 4 amostras (~26 por segundo)
TENTAR_SENSOR_MS = 2000        # sem sensor: tenta de novo a cada 2 s
FALHAS_PARA_DESCONECTAR = 50   # ~0,5 s de erros seguidos = sensor desconectado
DESCARTE_INICIAL = 20          # amostras (~200 ms) ignoradas ao ligar o sensor:
                               # as primeiras leituras do MAX30102 vêm erradas
INTERVALO_GC_MS = 1000         # coleta de lixo a cada 1 s, entre quadros
INTERVALO_LOG_MS = 2000        # resumo no terminal (útil no MicroPico)
INTERVALO_LUZES_MS = 30        # ~33 atualizações por segundo na matriz
INTERVALO_BOTOES_MS = 20
INTERVALO_BLE_MS = 50          # confere se há algo novo para mandar ao painel
ANTI_REPIQUE_MS = 250          # ignora o "tremido" do contato do botão

# Sinais sonoros do desafio: (frequência Hz, duração ms, pausa ms)
SONS_DESAFIO = {
    "inicio": [(1600, 60, 0)],
    "fase": [(1200, 80, 60), (1600, 120, 0)],
    "contagem": [(900, 120, 0)],
    "fim": [(1000, 100, 50), (1300, 100, 50), (1700, 250, 0)],
    "saiu": [(700, 120, 0)],
}


class Botao:
    """Botão com pull-up interno: solto = 1, apertado = 0.

    ANTI-REPIQUE (debounce): ao apertar, o contato metálico "quica" e gera
    vários 0/1 em poucos milissegundos. Só aceitamos um novo aperto depois
    de ANTI_REPIQUE_MS do anterior."""

    def __init__(self, pino):
        self.pino = Pin(pino, Pin.IN, Pin.PULL_UP)
        self.anterior = 1
        self.ultimo_ms = time.ticks_ms()

    def apertou(self):
        """True uma única vez, no momento em que o botão é apertado."""
        valor = self.pino.value()
        agora = time.ticks_ms()
        resultado = False
        if (valor == 0 and self.anterior == 1 and
                time.ticks_diff(agora, self.ultimo_ms) > ANTI_REPIQUE_MS):
            self.ultimo_ms = agora
            resultado = True
        self.anterior = valor
        return resultado


class Estado:
    """Tudo o que as tarefas compartilham."""

    def __init__(self):
        self.sensor = None
        self.erro_sensor = ""
        self.proc = sinal.ProcessadorSinal(
            taxa_hz=config.TAXA_AMOSTRAGEM_HZ,
            limiar_dedo=config.LIMIAR_DEDO,
            limiar_saida=config.LIMIAR_DEDO_SAIDA,
            alfa=config.ALFA_PASSA_ALTA,
            corte_hz=config.CORTE_PASSA_BAIXA_HZ,
            tempo_estabilizar_ms=config.TEMPO_ESTABILIZAR_MS,
            spo2_a=config.SPO2_A, spo2_b=config.SPO2_B,
            spo2_modelo=config.SPO2_MODELO)
        self.ultima_batida_ms = None
        self.modo = "MONITOR"
        self.matriz = Matriz(config.MATRIZ_PINO)
        self.rgb = LedRGB(config.LED_R_PINO, config.LED_G_PINO, config.LED_B_PINO)
        self.buzzer = Buzzer(config.BUZZER_PINO, config.SOM_VOLUME)
        self.buzzer.ligado = config.SOM_LIGADO_AO_INICIAR
        self.botao_a = Botao(config.BOTAO_A_PINO)
        self.botao_b = Botao(config.BOTAO_B_PINO)
        self.desafio = dsf.Desafio(config.DESAFIO_REPOUSO_S, config.DESAFIO_EXERCICIO_S)
        self.painel = None              # painel Bluetooth (None = desligado)
        self.batidas = 0                # contador: o painel anima o coração quando muda

    def evento_desafio(self, evento):
        """Toca o sinal sonoro de cada evento do desafio e avisa no terminal."""
        if not evento:
            return
        self.buzzer.sequencia(SONS_DESAFIO[evento])
        if evento == "fim":
            print("DESAFIO:", self.desafio.resumo())
        elif evento != "contagem":
            print("Desafio:", self.desafio.titulo() or "encerrado")

    @property
    def som(self):
        return self.buzzer.ligado


def conectar_sensor(i2c, est):
    """Faz o scan do I2C e confere o PART_ID. Devolve o sensor ou None."""
    try:
        if ENDERECO not in i2c.scan():
            est.erro_sensor = "0x57"
            return None
        sensor = MAX30102(i2c, config.LED_VERMELHO, config.LED_IR)
        est.erro_sensor = ""
        print("Sensor MAX30102 OK (PART_ID 0x{:02X}).".format(sensor.part_id))
        return sensor
    except SensorNaoEncontrado as e:
        est.erro_sensor = "ID"
        print("Sensor:", e)
    except OSError as e:
        est.erro_sensor = "I2C"
        print("Sensor: erro de I2C", e)
    return None


async def tarefa_sensor(est, tela):
    i2c = I2C(config.SENSOR_I2C_ID, sda=Pin(config.SENSOR_SDA),
              scl=Pin(config.SENSOR_SCL), freq=config.SENSOR_I2C_FREQ)
    proc = est.proc
    soma_onda = 0.0
    n_onda = 0
    estado_anterior = sinal.SEM_DEDO
    falhas = 0
    descartar = 0

    while True:
        # ---- Sem sensor: tenta conectar de tempos em tempos ----------------
        if est.sensor is None:
            est.sensor = conectar_sensor(i2c, est)
            if est.sensor is None:
                print("Sensor não encontrado: confira o conector I2C0 (GP0/GP1) "
                      "e os pull-ups (README).")
                await asyncio.sleep_ms(TENTAR_SENSOR_MS)
                continue
            descartar = DESCARTE_INICIAL

        # ---- Lê e processa todas as amostras novas -------------------------
        erros_antes = est.sensor.erros_i2c
        houve_batida = False
        for ir, vm in est.sensor.ler_fifo():
            if descartar:
                descartar -= 1
                continue
            estado = proc.processar(ir, vm)
            if estado != estado_anterior:
                if estado == sinal.SEM_DEDO or estado_anterior == sinal.SEM_DEDO:
                    if tela:
                        tela.onda.limpar()      # dedo chegou ou saiu: onda nova
                    est.ultima_batida_ms = None
                estado_anterior = estado
            if estado == sinal.PRONTO:
                # A onda do display recebe a média de 4 amostras: o display
                # tem só 128 colunas, então ~5 s de onda cabem na tela.
                soma_onda += proc.ir.ac
                n_onda += 1
                if n_onda == DECIMACAO_ONDA:
                    if tela:
                        tela.onda.adicionar(soma_onda / DECIMACAO_ONDA)
                    if est.painel:
                        est.painel.adicionar_onda(soma_onda / DECIMACAO_ONDA)
                    soma_onda = 0.0
                    n_onda = 0
            if proc.batimento:
                houve_batida = True
                est.batidas += 1
                est.ultima_batida_ms = time.ticks_ms()
                est.buzzer.bipe()
                est.matriz.batida()
        if est.desafio.ativo:
            est.evento_desafio(est.desafio.atualizar(
                time.ticks_ms(), proc.estado != sinal.SEM_DEDO, proc.bpm, houve_batida))
        est.buzzer.atualizar()        # desliga o bipe na hora certa

        # ---- Sensor desconectado? ------------------------------------------
        if est.sensor.erros_i2c != erros_antes:
            falhas += 1
            if falhas >= FALHAS_PARA_DESCONECTAR:
                print("Sensor parou de responder.")
                est.sensor = None
                est.erro_sensor = "I2C"
                falhas = 0
        else:
            falhas = 0

        await asyncio.sleep_ms(INTERVALO_SENSOR_MS)


async def tarefa_tela(est, tela):
    proc = est.proc
    presumido = getattr(config, "SPO2_PRESUMIDO", False)

    # ---- Abertura animada --------------------------------------------------
    inicio = time.ticks_ms()
    while tela.abertura(time.ticks_diff(time.ticks_ms(), inicio), presumido):
        tela.mostrar()
        await asyncio.sleep_ms(INTERVALO_ABERTURA_MS)

    ultimo_gc = ultimo_log = time.ticks_ms()
    while True:
        t0 = time.ticks_ms()
        # Ícone do Bluetooth: aceso = painel conectado; piscando = esperando.
        if est.painel:
            tela.bluetooth = est.painel.conectado or (t0 // 500) % 2 == 0
        if est.sensor is None:
            tela.erro_sensor(est.erro_sensor)
        elif est.desafio.ativo:
            desenhar_desafio(est, tela, t0)
        elif proc.estado == sinal.SEM_DEDO:
            tela.sem_dedo(t0, est.modo, est.som)
        else:
            tela.principal(t0, proc.bpm, proc.spo2, proc.estavel,
                           proc.progresso_medicao(), est.ultima_batida_ms,
                           est.modo, est.som, presumido)
        tela.mostrar()

        # Coleta de lixo e resumo no terminal, entre um quadro e outro.
        agora = time.ticks_ms()
        if time.ticks_diff(agora, ultimo_gc) >= INTERVALO_GC_MS:
            ultimo_gc = agora
            gc.collect()
        if time.ticks_diff(agora, ultimo_log) >= INTERVALO_LOG_MS:
            ultimo_log = agora
            if est.sensor is not None and proc.estado != sinal.SEM_DEDO:
                print("BPM {} {} | SpO2 {}{} | R {:.2f}".format(
                    proc.bpm or "--", "estável" if proc.estavel else "medindo",
                    proc.spo2 or "--", "*" if presumido else "", proc.oximetro.r))

        gasto = time.ticks_diff(time.ticks_ms(), t0)
        await asyncio.sleep_ms(max(INTERVALO_TELA_MS - gasto, 5))


async def tarefa_ble(est):
    """Envia as leituras para o painel (web/index.html) por Bluetooth."""
    proc = est.proc
    d = est.desafio
    while True:
        p = est.painel
        if p.conectado:
            agora = time.ticks_ms()
            if est.sensor is None:
                estado = 0                       # 0 = sem sensor
            else:
                estado = proc.estado + 1         # 1 sem dedo, 2 estabilizando, 3 pronto
            tempo = 0
            if d.estado in (dsf.REPOUSO_MEDINDO, dsf.EXERCICIO):
                tempo = d.restante_s(agora)
            elif d.estado in (dsf.VOLTA_ESPERA, dsf.RECUPERACAO):
                tempo = d.desde_exercicio_s(agora)
            p.publicar(agora, estado, proc.estavel, config.SPO2_PRESUMIDO, est.som,
                       proc.bpm, proc.spo2, proc.progresso_medicao(), est.batidas,
                       fase=d.estado, repouso=d.bpm_repouso, pico=d.bpm_pico,
                       alvo=d.limite_bpm() if d.ativo else 0, tempo_s=tempo,
                       recuperacao_s=d.recuperacao_s)
        await asyncio.sleep_ms(INTERVALO_BLE_MS)


def desenhar_desafio(est, tela, t0):
    """Escolhe a tela de cada fase do Desafio do Pátio."""
    d = est.desafio
    proc = est.proc
    com_dedo = proc.estado != sinal.SEM_DEDO
    e = d.estado
    if e == dsf.REPOUSO_ESPERA:
        if com_dedo:          # dedo no lugar, esperando o primeiro BPM
            # Título curto ("REPOUSO") para caber a barra de carregamento.
            tela.principal(t0, proc.bpm, proc.spo2, proc.estavel,
                           proc.progresso_medicao(), est.ultima_batida_ms,
                           "REPOUSO", est.som, config.SPO2_PRESUMIDO)
        else:
            tela.sem_dedo(t0, d.titulo(), est.som,
                          ("REPOUSO:", "Dedo no sensor", "e fique parado"))
    elif e == dsf.REPOUSO_MEDINDO:
        tela.desafio_medicao(t0, d.titulo(), proc.bpm, est.ultima_batida_ms,
                             "falta", d.restante_s(t0), est.som)
    elif e == dsf.EXERCICIO:
        tela.desafio_exercicio(t0, d.restante_s(t0), est.som)
    elif e == dsf.VOLTA_ESPERA:
        desde = d.desde_exercicio_s(t0)
        if com_dedo:          # dedo voltou, medindo o primeiro BPM
            tela.desafio_medicao(t0, d.titulo(), proc.bpm, est.ultima_batida_ms,
                                 "tempo", desde, est.som, como_tempo=True)
        else:
            tela.sem_dedo(t0, d.titulo(), est.som,
                          ("Dedo no sensor", "de novo!",
                           "tempo " + dsf.formatar_tempo(desde)))
    elif e == dsf.RECUPERACAO:
        tela.desafio_medicao(t0, d.titulo(), proc.bpm, est.ultima_batida_ms,
                             "tempo", d.desde_exercicio_s(t0), est.som, como_tempo=True)
    elif e == dsf.RESULTADO:
        tela.desafio_resultado(d.bpm_repouso, d.bpm_pico, d.recuperacao_s, est.som)


async def tarefa_luzes(est):
    """Matriz: coração que acende a cada batida. LED RGB: faixa do BPM."""
    proc = est.proc
    while True:
        agora = time.ticks_ms()
        com_dedo = proc.estado != sinal.SEM_DEDO
        est.matriz.atualizar(agora, com_dedo, erro=est.sensor is None)
        if proc.estado == sinal.PRONTO:
            est.rgb.definir(cores.cor_da_faixa(proc.bpm))
        else:
            est.rgb.definir(cores.APAGADO)
        est.buzzer.atualizar()
        await asyncio.sleep_ms(INTERVALO_LUZES_MS)


async def tarefa_botoes(est):
    while True:
        if est.botao_a.apertou():
            ligado = est.buzzer.alternar()
            print("Som", "ligado" if ligado else "desligado")
        if est.botao_b.apertou():
            est.evento_desafio(est.desafio.botao_b(time.ticks_ms()))
        await asyncio.sleep_ms(INTERVALO_BOTOES_MS)


def criar_tela():
    """Abre o OLED. Sem OLED, o programa continua mostrando tudo no terminal."""
    try:
        from display import Tela
        i2c_oled = I2C(config.OLED_I2C_ID, sda=Pin(config.OLED_SDA),
                       scl=Pin(config.OLED_SCL), freq=config.OLED_FREQ)
        return Tela(i2c_oled, config.OLED_ENDERECO)
    except OSError as e:
        print("OLED não encontrado ({}); seguindo só com o terminal.".format(e))
        return None


async def principal(est, tela):
    tarefas = [asyncio.create_task(tarefa_sensor(est, tela)),
               asyncio.create_task(tarefa_luzes(est)),
               asyncio.create_task(tarefa_botoes(est))]
    if config.BLE_ATIVO:
        try:
            from painel_ble import PainelBLE
            est.painel = PainelBLE(config.BLE_NOME)
            print("Painel Bluetooth: procure", est.painel.nome)
            tarefas.append(asyncio.create_task(tarefa_ble(est)))
        except Exception as e:
            print("Bluetooth indisponível:", e)
    if tela:
        tarefas.append(asyncio.create_task(tarefa_tela(est, tela)))
    await asyncio.gather(*tarefas)


print("Monitor de Batimentos - projeto educacional, NÃO é aparelho médico.")
estado_global = Estado()
tela_global = criar_tela()
gc.collect()
try:
    asyncio.run(principal(estado_global, tela_global))
except KeyboardInterrupt:
    print("Programa interrompido.")
finally:
    # Fica aqui fora (e não dentro das tarefas) para rodar mesmo com Ctrl+C.
    if estado_global.sensor:
        estado_global.sensor.desligar()
    estado_global.buzzer.desligar()
    estado_global.matriz.apagar()
    estado_global.rgb.desligar()
    if estado_global.painel:
        estado_global.painel.desligar()
    if tela_global:
        tela_global.limpar()
        tela_global.mostrar()
    asyncio.new_event_loop()     # deixa o asyncio limpo para a próxima execução
