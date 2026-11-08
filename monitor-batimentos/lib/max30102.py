# lib/max30102.py
# ---------------------------------------------------------------------------
# Driver do sensor MAX30102 (oxímetro de pulso e batimentos) para MicroPython.
# Escrito do zero, sem bibliotecas externas, para fins didáticos.
#
# COMO O SENSOR FUNCIONA (resumo para os alunos):
#   O sensor tem dois LEDs (vermelho e infravermelho, IR) e um fotodiodo.
#   Os LEDs piscam muito rápido e o fotodiodo mede quanta luz volta do dedo.
#   A cada batida do coração entra mais sangue no dedo, que absorve mais luz:
#   o sinal medido oscila um pouco. Essa oscilação é o "PPG"
#   (fotopletismograma), e é dela que tiramos o BPM e o SpO2.
#
#   As medidas ficam numa fila interna (FIFO) de 32 posições. A 100
#   amostras/s ela enche em 320 ms: basta ler com mais frequência que isso
#   para não perder nenhuma amostra.
#
# Este projeto é EDUCACIONAL e NÃO é um aparelho médico.
# ---------------------------------------------------------------------------

from micropython import const
import time

ENDERECO = const(0x57)           # endereço I2C fixo do MAX30102
PART_ID_ESPERADO = const(0x15)   # MAX30102 (também MAX30101/MAX30105)

# ---- Mapa de registradores (datasheet do MAX30102) ------------------------
_INT_STATUS_1 = const(0x00)      # avisos (ler limpa)
_INT_STATUS_2 = const(0x01)      # aviso "temperatura pronta"
_INT_ENABLE_1 = const(0x02)
_INT_ENABLE_2 = const(0x03)
_FIFO_WR_PTR = const(0x04)       # onde o sensor vai ESCREVER a próxima amostra
_OVF_COUNTER = const(0x05)       # amostras perdidas com a fila cheia
_FIFO_RD_PTR = const(0x06)       # de onde nós vamos LER a próxima amostra
_FIFO_DATA = const(0x07)         # "porta" de leitura da FIFO
_FIFO_CONFIG = const(0x08)
_MODE_CONFIG = const(0x09)
_SPO2_CONFIG = const(0x0A)
_LED1_PA = const(0x0C)           # corrente do LED 1 = vermelho
_LED2_PA = const(0x0D)           # corrente do LED 2 = infravermelho
_TEMP_INTEGER = const(0x1F)
_TEMP_FRACTION = const(0x20)
_TEMP_CONFIG = const(0x21)
_REV_ID = const(0xFE)
_PART_ID = const(0xFF)

# ---- Valores de configuração ---------------------------------------------
_MODO_SHDN = const(0x80)         # desliga o sensor (economia de energia)
_MODO_RESET = const(0x40)        # reinicia todos os registradores
_MODO_SPO2 = const(0x03)         # LED vermelho + IR (os dois servem p/ SpO2)
_TEMP_EN = const(0x01)           # dispara UMA leitura de temperatura
_TEMP_RDY = const(0x02)          # bit "temperatura pronta"

# FIFO_CONFIG = 0x10:
#   bits 7..5 = 000 -> sem média interna (queremos as amostras cruas)
#   bit 4     = 1   -> "rollover": se a fila encher, continua gravando
_FIFO_CONFIG_VALOR = const(0x10)

# SPO2_CONFIG = 0x27:
#   bits 6..5 = 01  -> faixa do ADC de 4096 nA
#   bits 4..2 = 001 -> 100 amostras por segundo
#   bits 1..0 = 11  -> pulso do LED de 411 µs (resolução de 18 bits)
_SPO2_CONFIG_VALOR = const(0x27)

# Corrente de cada LED: 0,2 mA por passo (0x00 a 0xFF = 0 a 51 mA).
# 0x24 = 7,2 mA é um bom ponto de partida; ajuste em config.py.
LED_PADRAO = const(0x24)

PROFUNDIDADE = const(32)         # a FIFO guarda 32 amostras
_BYTES_AMOSTRA = const(6)        # vermelho (3 bytes) + IR (3 bytes)
_MASCARA_PTR = const(0x1F)       # ponteiros de 5 bits (0 a 31)
VALOR_MAXIMO = const(0x3FFFF)    # 18 bits = 262143

_TIMEOUT_RESET_MS = const(100)
_TIMEOUT_TEMP_MS = const(50)     # a conversão de temperatura leva ~30 ms


class SensorNaoEncontrado(Exception):
    """O sensor não respondeu no I2C ou o PART_ID não é 0x15."""
    pass


class MAX30102:
    """Controla o MAX30102 por I2C.

    Uso:
        sensor = MAX30102(i2c)
        amostras = sensor.ler_fifo()   # [(ir, vermelho), ...]

    Nenhum método de leitura lança exceção de I2C: em caso de falha
    (fio solto, mau contato) ele conta o erro em `erros_i2c` e devolve um
    valor vazio, para que o programa principal continue rodando.
    """

    def __init__(self, i2c, led_vermelho=LED_PADRAO, led_ir=LED_PADRAO):
        self.i2c = i2c
        self.erros_i2c = 0           # quantas leituras falharam
        self.amostras_perdidas = 0   # quantas amostras o sensor descartou

        # Buffers alocados UMA vez só. Em MicroPython, criar objetos novos a
        # cada leitura gera lixo e força o coletor (gc) a rodar mais vezes,
        # o que pode causar pequenas pausas.
        self._buf_1 = bytearray(1)
        self._buf_ptrs = bytearray(3)              # WR_PTR, OVF, RD_PTR
        self._buf_fifo = bytearray(PROFUNDIDADE * _BYTES_AMOSTRA)
        self._mv_fifo = memoryview(self._buf_fifo)

        try:
            self.part_id = self._ler(_PART_ID)
            self.rev_id = self._ler(_REV_ID)
        except OSError:
            raise SensorNaoEncontrado("sensor não respondeu no endereço 0x57")
        if self.part_id != PART_ID_ESPERADO:
            raise SensorNaoEncontrado(
                "PART_ID = 0x{:02X} (esperado 0x15)".format(self.part_id))

        self.configurar(led_vermelho, led_ir)

    # ------------------------------------------------------------------ I2C
    def _ler(self, reg):
        self.i2c.readfrom_mem_into(ENDERECO, reg, self._buf_1)
        return self._buf_1[0]

    def _escrever(self, reg, valor):
        self._buf_1[0] = valor & 0xFF
        self.i2c.writeto_mem(ENDERECO, reg, self._buf_1)

    # ------------------------------------------------------- configuração
    def configurar(self, led_vermelho=LED_PADRAO, led_ir=LED_PADRAO):
        """Reinicia o sensor e o deixa medindo em modo SpO2 a 100 Hz."""
        # 1. Reset: o bit volta sozinho para 0 quando o chip termina.
        self._escrever(_MODE_CONFIG, _MODO_RESET)
        inicio = time.ticks_ms()
        while self._ler(_MODE_CONFIG) & _MODO_RESET:
            if time.ticks_diff(time.ticks_ms(), inicio) > _TIMEOUT_RESET_MS:
                break   # segue mesmo assim; o resto da configuração reescreve tudo
            time.sleep_ms(1)  # só na inicialização, não atrapalha a amostragem

        # Ler os status limpa o aviso "PWR_RDY" que aparece após o reset.
        self._ler(_INT_STATUS_1)
        self._ler(_INT_STATUS_2)
        # Vamos consultar a FIFO por "polling" (perguntando de tempos em
        # tempos), então as interrupções ficam desligadas.
        self._escrever(_INT_ENABLE_1, 0x00)
        self._escrever(_INT_ENABLE_2, 0x00)

        # 2. Fila sem média e com rollover, 3. modo SpO2,
        # 4. 100 amostras/s com 18 bits, 5. correntes dos LEDs.
        self._escrever(_FIFO_CONFIG, _FIFO_CONFIG_VALOR)
        self._escrever(_MODE_CONFIG, _MODO_SPO2)
        self._escrever(_SPO2_CONFIG, _SPO2_CONFIG_VALOR)
        self.definir_correntes(led_vermelho, led_ir)
        # 6. FIFO vazia para começar do zero.
        self.limpar_fifo()

    def definir_correntes(self, vermelho, ir):
        """Ajusta as correntes dos LEDs (0 a 255, 0,2 mA por passo)."""
        try:
            self._escrever(_LED1_PA, vermelho)
            self._escrever(_LED2_PA, ir)
            return True
        except OSError:
            self.erros_i2c += 1
            return False

    def limpar_fifo(self):
        """Zera os ponteiros da FIFO e o contador de amostras perdidas."""
        try:
            self._escrever(_FIFO_WR_PTR, 0)
            self._escrever(_OVF_COUNTER, 0)
            self._escrever(_FIFO_RD_PTR, 0)
            return True
        except OSError:
            self.erros_i2c += 1
            return False

    # ------------------------------------------------------------- leitura
    def _ler_ponteiros(self):
        """Lê WR_PTR, OVF_COUNTER e RD_PTR de uma vez e devolve (n, ovf).

        O endereço do registrador avança sozinho a cada byte lido, então uma
        única leitura de 3 bytes traz os três registradores vizinhos.
        """
        self.i2c.readfrom_mem_into(ENDERECO, _FIFO_WR_PTR, self._buf_ptrs)
        wr, ovf, rd = self._buf_ptrs[0], self._buf_ptrs[1], self._buf_ptrs[2]
        # A FIFO é circular: os ponteiros dão a volta de 31 para 0.
        # O "& 0x1F" faz a conta "módulo 32" e resolve a volta.
        # Ex.: WR = 2, RD = 30  ->  (2 - 30) & 31 = 4 amostras.
        return (wr - rd) & _MASCARA_PTR, ovf

    def amostras_disponiveis(self):
        """Quantas amostras estão esperando na FIFO (0 a 32), ou -1 em erro."""
        try:
            n, ovf = self._ler_ponteiros()
            if n == 0 and ovf:
                # WR == RD pode significar "vazia" OU "cheia"; o contador de
                # estouro (OVF) desempata. Mas cuidado: se uma amostra nova
                # chegar NO MEIO da leitura dos 3 bytes, podemos ver um WR
                # velho com um OVF novo e achar que a fila encheu. Por isso
                # conferimos uma segunda vez antes de concluir.
                n, ovf = self._ler_ponteiros()
                if n == 0 and ovf:
                    self.amostras_perdidas += ovf
                    return PROFUNDIDADE
            return n
        except OSError:
            self.erros_i2c += 1
            return -1

    def ler_fifo(self):
        """Lê todas as amostras disponíveis.

        Retorna uma lista de tuplas (ir, vermelho), da mais antiga para a
        mais nova. Retorna [] se não houver nada novo ou se o I2C falhar.
        """
        n = self.amostras_disponiveis()
        if n <= 0:
            return []
        total = n * _BYTES_AMOSTRA
        try:
            # Leitura em rajada: no FIFO_DATA o endereço NÃO avança, então
            # ler N bytes seguidos entrega N bytes da fila, em ordem.
            self.i2c.readfrom_mem_into(ENDERECO, _FIFO_DATA,
                                       self._mv_fifo[:total])
        except OSError:
            self.erros_i2c += 1
            return []

        # Cada amostra: [VERMELHO 3 bytes][IR 3 bytes], 18 bits úteis.
        # "(b0 << 16) | (b1 << 8) | b2" junta 3 bytes num número só, e
        # "& 0x3FFFF" descarta os bits que sobram acima dos 18.
        b = self._buf_fifo
        amostras = []
        for i in range(0, total, _BYTES_AMOSTRA):
            vermelho = ((b[i] << 16) | (b[i + 1] << 8) | b[i + 2]) & VALOR_MAXIMO
            ir = ((b[i + 3] << 16) | (b[i + 4] << 8) | b[i + 5]) & VALOR_MAXIMO
            amostras.append((ir, vermelho))
        return amostras

    def ler_temperatura(self):
        """Mede a temperatura interna do chip em °C (ou None em erro).

        Não é a temperatura do corpo! É a do próprio sensor, útil para
        conferir se o chip está funcionando. A conversão leva ~30 ms; como a
        FIFO guarda 320 ms de amostras, essa espera não perde dados.
        """
        try:
            # O chip só marca "temperatura pronta" se esse aviso estiver
            # habilitado. Habilitamos só durante a medida.
            self._escrever(_INT_ENABLE_2, _TEMP_RDY)
            self._ler(_INT_STATUS_2)               # limpa avisos antigos
            self._escrever(_TEMP_CONFIG, _TEMP_EN)
            inicio = time.ticks_ms()
            # Não dá para confiar no bit TEMP_EN (ele é lido como 0 desde o
            # início). Esperamos o aviso "pronta".
            while not (self._ler(_INT_STATUS_2) & _TEMP_RDY):
                if time.ticks_diff(time.ticks_ms(), inicio) > _TIMEOUT_TEMP_MS:
                    break   # sem aviso: após 50 ms a medida já terminou
                time.sleep_ms(2)
            self._escrever(_INT_ENABLE_2, 0x00)
            inteiro = self._ler(_TEMP_INTEGER)
            if inteiro > 127:          # número com sinal (complemento de 2)
                inteiro -= 256
            return inteiro + (self._ler(_TEMP_FRACTION) & 0x0F) * 0.0625
        except OSError:
            self.erros_i2c += 1
            return None

    # ------------------------------------------------------------- energia
    def desligar(self):
        """Apaga os LEDs e coloca o sensor em modo de economia."""
        try:
            self._escrever(_MODE_CONFIG, self._ler(_MODE_CONFIG) | _MODO_SHDN)
            return True
        except OSError:
            self.erros_i2c += 1
            return False

    def ligar(self):
        """Sai do modo de economia e volta a medir."""
        try:
            self._escrever(_MODE_CONFIG, self._ler(_MODE_CONFIG) & ~_MODO_SHDN)
            self.limpar_fifo()
            return True
        except OSError:
            self.erros_i2c += 1
            return False
