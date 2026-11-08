# lib/sinal.py
# ---------------------------------------------------------------------------
# Processamento do sinal do oxímetro: detecção do dedo, filtros,
# detecção de batimentos (BPM) e oxigenação aproximada (SpO2).
#
# O QUE O SENSOR ENTREGA (exemplo real medido na Etapa 1):
#
#   IR cru ≈ 153.000  ±  300
#            ^^^^^^^     ^^^
#            "DC"        "AC"
#
#   - DC (componente contínua): a luz que volta de pele, osso, tecido e do
#     sangue que está sempre lá. É ENORME e muda devagar (pressão do dedo,
#     temperatura, luz ambiente).
#   - AC (componente alternada): a pequena oscilação causada por cada batida
#     do coração. É só ~0,2% do total, mas é ela que interessa!
#
#   O trabalho dos filtros é jogar fora o DC e o ruído, deixando só o AC:
#
#     cru ──> [mediana] ──> [passa-alta] ──> [passa-baixa] ──> onda PPG
#             tira picos     tira o DC        tira o "chiado"
#             isolados
#
# Este projeto é EDUCACIONAL e NÃO é um aparelho médico.
# ---------------------------------------------------------------------------

import math

# Estados da detecção do dedo
SEM_DEDO = 0          # nada sobre o sensor
ESTABILIZANDO = 1     # dedo chegou; esperando o sinal assentar
PRONTO = 2            # sinal bom para medir

NOMES_ESTADO = ("sem dedo", "estabilizando", "pronto")

# Valores padrão (o config.py pode sobrescrever)
TAXA_PADRAO_HZ = 100
ALFA_PASSA_ALTA = 0.95      # quanto maior, mais devagar o filtro "esquece" o DC
CORTE_PASSA_BAIXA_HZ = 4.0  # acima disso é ruído (200 BPM = só 3,3 Hz)
TEMPO_ESTABILIZAR_MS = 1500
BETA_DC = 0.02              # média do DC: segue o nível em ~0,5 s
BETA_DEDO = 0.1             # média rápida (~0,1 s) só para detectar o dedo

# Detecção de batimentos
REFRATARIO_MS = 300         # depois de uma batida, ignora picos por 300 ms (máx. 200 BPM)
FRACAO_REFRATARIO = 0.6     # ... ou por 60% do intervalo médio, se for maior
BPM_MIN = 40
BPM_MAX = 200
FRACAO_LIMIAR = 0.4         # o limiar fica em 40% da altura típica dos picos (testado em gravações reais)
FRACAO_REARME = 0.0         # depois de um pico, espera a onda cair abaixo disso x limiar
PESO_AMPLITUDE = 0.25       # quanto cada pico novo muda a "altura típica"
PISO_LIMIAR = 0.0005        # limiar mínimo = 0,05% do DC (abaixo disso é ruído)
DECAIMENTO_SEM_BATIDA = 0.99  # se as batidas somem, o limiar desce ~1% por amostra
INTERVALOS_MEDIA = 8        # BPM = média dos últimos 8 intervalos
INTERVALOS_MINIMOS = 4      # precisa de pelo menos 4 para mostrar um BPM
TOLERANCIA_INTERVALO = 0.35 # intervalo 35% fora da média = batida perdida ou falsa
MAX_REJEICOES = 3           # 3 rejeições seguidas = o ritmo mudou de verdade
VARIACAO_ESTAVEL = 0.20     # estável se (maior - menor intervalo) <= 20% da média

# SpO2 (veja a classe CalculadoraSpO2)
SPO2_MODELO = "linear"      # "linear" (A - B x R) ou "maxim" (curva da Maxim)
SPO2_A = 110.0              # SpO2 ≈ A - B x R  (fórmula EMPÍRICA, calibre em config.py)
SPO2_B = 25.0
# Curva de calibração da Maxim Integrated (projeto de referência MAXREFDES117)
MAXIM_A = -45.060           # SpO2 = A·R² + B·R + C
MAXIM_B = 30.354
MAXIM_C = 94.845
SPO2_MIN = 70
SPO2_MAX = 100
R_MIN = 0.2                 # razões fora desta faixa são erro de medida
R_MAX = 3.0
BATIDAS_SPO2 = 5            # SpO2 = mediana dos R das últimas 5 batidas
BATIDAS_SPO2_MIN = 3        # precisa de pelo menos 3 para mostrar
PI_MIN_SPO2 = 0.002         # ignora batidas com pulso < 0,2% do DC (sinal fraco)


class Mediana3:
    """Filtro de mediana de 3 amostras: elimina "picos" isolados.

    De vez em quando o sensor entrega UMA amostra absurda (na Etapa 2 vimos
    o vermelho saltar de 101.000 para 115.000 e voltar). Os filtros lineares
    espalhariam esse salto e ele pareceria uma batida. A mediana olha a
    amostra atual e as duas anteriores e fica com a do MEIO:
        [101740, 115913, 101688] -> ordena -> 101688, 101740, 115913 -> 101740
    Um valor isolado nunca fica no meio, então some. Custo: atraso de 1 amostra.
    """

    def __init__(self):
        self.a = 0
        self.b = 0

    def reiniciar(self, x):
        self.a = self.b = x

    def filtrar(self, x):
        a, b = self.a, self.b
        self.a, self.b = b, x
        # Mediana de (a, b, x) só com comparações (rápido e sem listas).
        if a > b:
            a, b = b, a
        # agora a <= b
        if x <= a:
            return a
        if x >= b:
            return b
        return x


class PassaAlta:
    """Filtro passa-alta de 1ª ordem: remove a componente DC.

    Fórmula (circuito RC digital):
        y[n] = alfa * (y[n-1] + x[n] - x[n-1])

    Intuição: "x[n] - x[n-1]" só enxerga o que MUDOU entre uma amostra e a
    outra. Um nível parado (DC) não muda, então some. O termo "alfa * y[n-1]"
    dá uma "memória" para o filtro, para que ondas lentas como o pulso
    (1 a 3 Hz) passem e não só as mudanças bruscas.

    Frequência de corte: fc ≈ (1 - alfa) / (2π · alfa · dt)
        alfa = 0,95 a 100 Hz  ->  fc ≈ 0,84 Hz  (≈ 50 BPM)
    O pulso passa um pouco atenuado abaixo disso, mas a detecção de picos
    usa um limiar adaptativo e não depende do tamanho exato da onda.
    Experimente alfa = 0,98 (fc ≈ 0,3 Hz): o sinal fica mais fiel, mas o
    filtro demora mais para assentar quando o dedo chega.
    """

    def __init__(self, alfa=ALFA_PASSA_ALTA):
        self.alfa = alfa
        self.x_ant = 0
        self.y = 0.0

    def reiniciar(self, x):
        # Começar com x_ant = x evita um "degrau" gigante na saída quando o
        # dedo chega (o IR pula de ~2.000 para ~150.000 de uma vez).
        self.x_ant = x
        self.y = 0.0

    def filtrar(self, x):
        # x e x_ant são inteiros: a subtração é exata, sem erro de ponto flutuante.
        self.y = self.alfa * (self.y + (x - self.x_ant))
        self.x_ant = x
        return self.y


class PassaBaixa:
    """Filtro passa-baixa Butterworth de 2ª ordem: suaviza o ruído.

    Fórmula (um "biquad", com transformação bilinear):
        y[n] = b0 · (x[n] + 2·x[n-1] + x[n-2]) - a1 · y[n-1] - a2 · y[n-2]

    Intuição: é uma média ponderada das últimas 3 entradas e das últimas 2
    saídas. Variações rápidas (ruído) se anulam; variações lentas (a onda do
    pulso) passam inteiras.

    POR QUE 2ª ORDEM? Medimos o sinal real e achamos ruído entre 8 e 17 Hz
    (pico em 14,5 Hz, provavelmente o "pisca" de 120 Hz das lâmpadas
    "dobrado" pela amostragem de 104 Hz). Com corte em 4 Hz:
        filtro de 1ª ordem: o ruído de 14,5 Hz cai para ~27%
        filtro de 2ª ordem: o ruído de 14,5 Hz cai para ~7%
    Nos dados gravados, a relação pulso/ruído melhorou 3,5 vezes.

    Os coeficientes saem da frequência de corte fc e da taxa fs:
        k = tan(π·fc/fs),  d = 1 + √2·k + k²
        b0 = k²/d,  a1 = 2·(k² - 1)/d,  a2 = (1 - √2·k + k²)/d
    """

    def __init__(self, corte_hz=CORTE_PASSA_BAIXA_HZ, taxa_hz=TAXA_PADRAO_HZ):
        k = math.tan(math.pi * corte_hz / taxa_hz)
        r2 = math.sqrt(2)
        d = 1 + r2 * k + k * k
        self.b0 = k * k / d
        self.a1 = 2 * (k * k - 1) / d
        self.a2 = (1 - r2 * k + k * k) / d
        self.reiniciar()

    def reiniciar(self, x=0.0):
        self.x1 = self.x2 = x
        self.y1 = self.y2 = x

    def filtrar(self, x):
        y = (self.b0 * (x + 2 * self.x1 + self.x2)
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y


class Canal:
    """Um canal de luz (IR ou vermelho): mede o DC e extrai a onda AC."""

    def __init__(self, taxa_hz, alfa, corte_hz):
        self.mediana = Mediana3()
        self.passa_alta = PassaAlta(alfa)
        self.passa_baixa = PassaBaixa(corte_hz, taxa_hz)
        self.dc = 0.0     # nível médio (usado no SpO2 e para achar o dedo)
        self.ac = 0.0     # onda PPG filtrada

    def reiniciar(self, x):
        self.mediana.reiniciar(x)
        self.passa_alta.reiniciar(x)
        self.passa_baixa.reiniciar(0.0)
        self.dc = float(x)
        self.ac = 0.0

    def processar(self, x):
        x = self.mediana.filtrar(x)
        # Média móvel exponencial: o DC anda só 2% em direção ao valor novo
        # a cada amostra, então segue o nível sem se mexer com cada batida.
        self.dc += BETA_DC * (x - self.dc)
        # Mais sangue no dedo = MENOS luz volta ao sensor. Então a batida
        # aparece como um "vale" no sinal cru. Invertemos o sinal (o "-")
        # para a batida virar um PICO, como num monitor de hospital.
        self.ac = -self.passa_baixa.filtrar(self.passa_alta.filtrar(x))
        return self.ac


class DetectorBatimentos:
    """Encontra os picos da onda PPG e calcula o BPM.

    COMO ACHAMOS UMA BATIDA (pense numa montanha-russa):
      1. LIMIAR ADAPTATIVO: guardamos a "altura típica" dos últimos picos e
         só aceitamos picos acima de 40% dela. Se o dedo apertar mais e a
         onda crescer (ou diminuir), o limiar acompanha sozinho.
      2. PICO = o sinal estava SUBINDO e começou a DESCER, acima do limiar.
      3. "ARMAR/DESARMAR": depois de contar um pico, só aceitamos outro
         depois que a onda voltar para baixo de zero. Isso ignora a pequena
         "segunda corcova" (nó dicrótico) que vem logo depois de cada batida.
      4. PERÍODO REFRATÁRIO: nenhum coração bate 2 vezes em menos de 300 ms
         (seria mais de 200 BPM), então picos tão próximos são ignorados.
         Quando já conhecemos o ritmo, o refratário cresce para 60% do
         intervalo médio. Nos dados reais, a "segunda corcova" vinha ~300 ms
         depois de cada batida e escapava do refratário fixo, dobrando o BPM!

    COMO CALCULAMOS O BPM:
      intervalo = tempo entre duas batidas (em amostras)
      BPM = 60 s x taxa / média dos últimos 8 intervalos
      Intervalos muito diferentes da média (batida perdida ou falsa, dedo
      mexendo) são descartados. A leitura é "estável" quando os intervalos
      guardados são parecidos entre si.
    """

    def __init__(self, taxa_hz=TAXA_PADRAO_HZ):
        self.taxa_hz = taxa_hz
        self.refratario = REFRATARIO_MS * taxa_hz // 1000
        self.max_intervalo = taxa_hz * 60 // BPM_MIN
        self.reiniciar()

    def reiniciar(self):
        self.n = 0              # contador de amostras (o nosso "relógio")
        self.ultimo = None      # amostra do último pico
        self.amplitude = 0.0    # altura típica dos picos
        self.limiar = 0.0
        self.armado = True
        self.anterior = 0.0
        self.intervalos = []    # últimos intervalos válidos, em amostras
        self.media = 0          # intervalo médio, em amostras
        self.rejeicoes = 0
        self.bpm = 0
        self.estavel = False

    def processar(self, v, dc):
        """Recebe uma amostra da onda (já filtrada) e o DC do canal.
        Devolve True na amostra em que uma batida é detectada."""
        self.n += 1
        batida = False

        # Mais de 1,5 s (40 BPM) sem batida? Baixa o limiar aos poucos, para
        # reencontrar a onda se ela ficou menor.
        if self.ultimo is None or self.n - self.ultimo > self.max_intervalo:
            self.amplitude *= DECAIMENTO_SEM_BATIDA
        # Batidas sumiram de vez (mais que 2 intervalos de 40 BPM): zera o BPM.
        if self.ultimo is not None and self.n - self.ultimo > 2 * self.max_intervalo:
            self.intervalos = []
            self.media = 0
            self.bpm = 0
            self.estavel = False
            self.ultimo = None

        limiar = FRACAO_LIMIAR * self.amplitude
        piso = PISO_LIMIAR * dc
        if limiar < piso:
            limiar = piso
        self.limiar = limiar

        if self.armado:
            # O valor anterior foi um pico? (subiu até ele e agora desceu)
            if self.anterior > limiar and v < self.anterior:
                pico_n = self.n - 1
                refratario = self.refratario
                if FRACAO_REFRATARIO * self.media > refratario:
                    refratario = FRACAO_REFRATARIO * self.media
                if self.ultimo is None or pico_n - self.ultimo >= refratario:
                    batida = True
                    self.armado = False
                    self._atualizar_amplitude(self.anterior)
                    self._registrar(pico_n)
        elif v < FRACAO_REARME * limiar:
            self.armado = True   # a onda voltou para baixo: pode vir outra batida

        self.anterior = v
        return batida

    def _atualizar_amplitude(self, pico):
        if self.amplitude == 0:
            self.amplitude = pico
            return
        # Um pico gigante (dedo mexeu) não pode estragar o limiar:
        # limitamos a contribuição dele a 2x a altura típica.
        if pico > 2 * self.amplitude:
            pico = 2 * self.amplitude
        self.amplitude += PESO_AMPLITUDE * (pico - self.amplitude)

    def _registrar(self, pico_n):
        if self.ultimo is not None:
            intervalo = pico_n - self.ultimo
            if intervalo <= self.max_intervalo:
                self._novo_intervalo(intervalo)
        self.ultimo = pico_n

    def _novo_intervalo(self, intervalo):
        lista = self.intervalos
        if len(lista) >= INTERVALOS_MINIMOS:
            media = sum(lista) / len(lista)
            if abs(intervalo - media) > TOLERANCIA_INTERVALO * media:
                self.rejeicoes += 1
                if self.rejeicoes < MAX_REJEICOES:
                    return          # provavelmente batida perdida ou falsa
                del lista[:]        # várias seguidas: o ritmo mudou de verdade
                self.media = 0
        self.rejeicoes = 0
        lista.append(intervalo)
        if len(lista) > INTERVALOS_MEDIA:
            lista.pop(0)
        media = sum(lista) / len(lista)
        if len(lista) >= 2:
            self.media = media      # só confia na média com 2+ intervalos
        # Com menos de 4 intervalos a média ainda é muito incerta (um único
        # intervalo errado vira um BPM absurdo), então ainda não mostramos.
        if len(lista) >= INTERVALOS_MINIMOS:
            self.bpm = int(60 * self.taxa_hz / media + 0.5)
        else:
            self.bpm = 0
        self.estavel = (len(lista) >= INTERVALOS_MINIMOS and
                        max(lista) - min(lista) <= VARIACAO_ESTAVEL * media)

    def intervalo_ms(self):
        """Último intervalo válido em milissegundos (0 se não houver)."""
        if not self.intervalos:
            return 0
        return int(self.intervalos[-1] * 1000 / self.taxa_hz)


class CalculadoraSpO2:
    """Estima a oxigenação do sangue (SpO2) pela "razão das razões".

    A IDEIA FÍSICA:
      O sangue com oxigênio (oxi-hemoglobina) e sem oxigênio absorvem a
      luz de jeitos diferentes:
        - luz VERMELHA (660 nm): o sangue SEM oxigênio absorve muito mais;
        - luz INFRAVERMELHA (880 nm): o sangue COM oxigênio absorve um pouco mais.
      Então, comparando o "tamanho do pulso" nas duas cores, dá para estimar
      quanto do sangue está oxigenado.

    A CONTA, batida a batida:
      AC = altura do pulso (pico menos vale) naquela batida
      DC = nível médio do sinal
      R  = (AC_vermelho / DC_vermelho) / (AC_IR / DC_IR)
      Dividir pelo DC cancela a cor da pele, a espessura do dedo e a força
      de cada LED; sobra só o efeito do sangue que pulsa.

    DE R PARA SpO2 (duas curvas publicadas, escolha em config.py):
      "linear": SpO2 ≈ A - B x R  (A = 110, B = 25). Aproximação clássica
                de notas de aplicação de oximetria de pulso.
      "maxim":  SpO2 = -45,060·R² + 30,354·R + 94,845. Curva do projeto de
                referência da Maxim Integrated, fabricante do MAX30102
                (MAXREFDES117, arquivo algorithm.cpp), a mesma usada na
                biblioteca oficial da SparkFun para os MAX3010x
                (spo2_algorithm.cpp). Vale para R entre ~0,02 e ~1,84.
      Nosso R é medido do mesmo jeito que no código da Maxim: altura do
      pulso em cada canal, batida a batida, dividida pelo nível DC, e a
      mediana das últimas razões.

    ATENÇÃO: as duas fórmulas são EMPÍRICAS e APROXIMADAS. Os números vêm
    de medições comparando um sensor com aparelhos de referência; cada
    modelo de sensor (e até cada módulo) precisa da sua própria calibração.
    Por isso eles ficam no config.py. Este projeto NÃO é um aparelho médico
    e o valor mostrado serve só para estudar o princípio de funcionamento.
    """

    def __init__(self, a=SPO2_A, b=SPO2_B, modelo=SPO2_MODELO):
        self.a = a
        self.b = b
        self.modelo = modelo
        self.reiniciar()

    def converter(self, r):
        """Converte a razão R em SpO2 (%), sem limitar a faixa."""
        if self.modelo == "maxim":
            return MAXIM_A * r * r + MAXIM_B * r + MAXIM_C
        return self.a - self.b * r

    def reiniciar(self):
        self.razoes = []        # R das últimas batidas
        self.r = 0.0            # R usado no último cálculo (mediana)
        self.r_batida = 0.0     # R da última batida aceita
        self.contagem = 0       # quantas batidas já deram um R válido
        self.spo2 = 0           # 0 = ainda sem valor
        self._novo_ciclo()

    def _novo_ciclo(self):
        # Pico e vale de cada canal desde a última batida.
        self.max_ir = self.max_vm = -1e9
        self.min_ir = self.min_vm = 1e9

    def acumular(self, ac_ir, ac_vm):
        """Chamado a cada amostra: acompanha pico e vale do ciclo atual."""
        if ac_ir > self.max_ir: self.max_ir = ac_ir
        if ac_ir < self.min_ir: self.min_ir = ac_ir
        if ac_vm > self.max_vm: self.max_vm = ac_vm
        if ac_vm < self.min_vm: self.min_vm = ac_vm

    def batida(self, dc_ir, dc_vm):
        """Chamado a cada batida: fecha o ciclo e atualiza o SpO2."""
        ac_ir = self.max_ir - self.min_ir
        ac_vm = self.max_vm - self.min_vm
        self._novo_ciclo()
        if ac_ir <= 0 or ac_vm <= 0 or dc_ir <= 0 or dc_vm <= 0:
            return
        # Pulso muito fraco (índice de perfusão baixo): o ruído pesa mais que
        # o sinal e o R fica sem sentido. Melhor não usar essa batida.
        if ac_ir / dc_ir < PI_MIN_SPO2:
            return
        r = (ac_vm / dc_vm) / (ac_ir / dc_ir)
        if r < R_MIN or r > R_MAX:
            return              # batida com artefato: descarta
        self.r_batida = r
        self.contagem += 1
        self.razoes.append(r)
        if len(self.razoes) > BATIDAS_SPO2:
            self.razoes.pop(0)
        if len(self.razoes) < BATIDAS_SPO2_MIN:
            return
        # Mediana: uma batida estranha (dedo mexeu) não muda o resultado.
        ordenadas = sorted(self.razoes)
        self.r = ordenadas[len(ordenadas) // 2]
        spo2 = int(self.converter(self.r) + 0.5)
        if spo2 > SPO2_MAX:
            spo2 = SPO2_MAX
        elif spo2 < SPO2_MIN:
            spo2 = SPO2_MIN
        self.spo2 = spo2


class ProcessadorSinal:
    """Recebe as amostras (ir, vermelho) e mantém o estado do dedo e as ondas.

    Uso:
        proc = ProcessadorSinal(taxa_hz=104, limiar_dedo=30000)
        for ir, vermelho in sensor.ler_fifo():
            estado = proc.processar(ir, vermelho)
            if estado == PRONTO:
                usar(proc.ir.ac)       # onda PPG do infravermelho
            if proc.batimento:         # True só na amostra da batida
                piscar_coracao()
        print(proc.bpm, proc.estavel, proc.spo2)
    """

    def __init__(self, taxa_hz=TAXA_PADRAO_HZ, limiar_dedo=30000,
                 limiar_saida=None, alfa=ALFA_PASSA_ALTA,
                 corte_hz=CORTE_PASSA_BAIXA_HZ,
                 tempo_estabilizar_ms=TEMPO_ESTABILIZAR_MS,
                 spo2_a=SPO2_A, spo2_b=SPO2_B, spo2_modelo=SPO2_MODELO):
        self.taxa_hz = taxa_hz
        self.limiar_dedo = limiar_dedo
        # Histerese: para "tirar" o dedo, o nível precisa cair abaixo de um
        # limiar MENOR que o de entrada. Assim, se o nível ficar oscilando
        # perto do limiar, o estado não fica piscando entre dedo/sem dedo.
        self.limiar_saida = (limiar_saida if limiar_saida is not None
                             else limiar_dedo * 2 // 3)
        self.amostras_estabilizar = tempo_estabilizar_ms * taxa_hz // 1000
        self.ir = Canal(taxa_hz, alfa, corte_hz)
        self.vermelho = Canal(taxa_hz, alfa, corte_hz)
        self.detector = DetectorBatimentos(taxa_hz)
        self.oximetro = CalculadoraSpO2(spo2_a, spo2_b, spo2_modelo)
        self.batimento = False  # True só na amostra em que houve batida
        self.estado = SEM_DEDO
        self.nivel_dedo = 0.0   # média rápida do IR, só para achar o dedo
        self._contador = 0      # amostras desde que o dedo chegou

    def processar(self, ir, vermelho):
        """Processa UMA amostra e devolve o estado (SEM_DEDO/ESTABILIZANDO/PRONTO)."""
        self.nivel_dedo += BETA_DEDO * (ir - self.nivel_dedo)
        self.batimento = False

        if self.estado == SEM_DEDO:
            if self.nivel_dedo > self.limiar_dedo:
                # Dedo chegou: zera os filtros a partir do nível atual.
                self.ir.reiniciar(ir)
                self.vermelho.reiniciar(vermelho)
                self.detector.reiniciar()
                self.oximetro.reiniciar()
                self._contador = 0
                self.estado = ESTABILIZANDO
            return self.estado

        if self.nivel_dedo < self.limiar_saida:
            self.estado = SEM_DEDO
            self.detector.reiniciar()
            self.oximetro.reiniciar()
            return self.estado

        self.ir.processar(ir)
        self.vermelho.processar(vermelho)

        if self.estado == ESTABILIZANDO:
            # Logo que o dedo encosta, o nível ainda está subindo e os filtros
            # estão "acordando". Esperamos um pouco antes de confiar no sinal.
            self._contador += 1
            if self._contador >= self.amostras_estabilizar:
                self.estado = PRONTO
        else:
            # A onda do IR é a mais forte: é nela que procuramos as batidas.
            self.batimento = self.detector.processar(self.ir.ac, self.ir.dc)
            self.oximetro.acumular(self.ir.ac, self.vermelho.ac)
            if self.batimento:
                if self.detector.bpm:
                    self.oximetro.batida(self.ir.dc, self.vermelho.dc)
                else:
                    self.oximetro._novo_ciclo()   # ritmo ainda desconhecido
            elif self.detector.bpm == 0 and self.oximetro.spo2:
                self.oximetro.reiniciar()         # batidas sumiram
        return self.estado

    @property
    def spo2(self):
        return self.oximetro.spo2

    @property
    def bpm(self):
        return self.detector.bpm

    @property
    def estavel(self):
        return self.detector.estavel

    def progresso_medicao(self):
        """De 0.0 a 1.0, para a barra "Medindo...": os primeiros 25% são a
        estabilização do dedo; o resto enche com os intervalos medidos até
        juntar os 8 usados na média do BPM."""
        if self.estado == SEM_DEDO:
            return 0.0
        if self.estado == ESTABILIZANDO:
            return 0.25 * self.progresso()
        n = len(self.detector.intervalos)
        if n > INTERVALOS_MEDIA:
            n = INTERVALOS_MEDIA
        return 0.25 + 0.75 * n / INTERVALOS_MEDIA

    def progresso(self):
        """De 0.0 a 1.0: quanto falta para o sinal ficar PRONTO."""
        if self.estado == PRONTO:
            return 1.0
        if self.estado == SEM_DEDO:
            return 0.0
        return self._contador / self.amostras_estabilizar
