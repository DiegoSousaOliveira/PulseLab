# lib/painel_ble.py
# ---------------------------------------------------------------------------
# Painel por BLUETOOTH LOW ENERGY (BLE): a placa envia as leituras para a
# página web/index.html, aberta no Chrome ou Edge de um computador/telão.
#
# A Pico W tem Bluetooth embutido (chip CYW43439). Aqui ela é um
# "periférico" BLE, como uma pulseira fitness: anuncia o nome
# "Batimentos-XXXX" e quem se conecta recebe NOTIFICAÇÕES com os dados.
# Não precisa de Wi-Fi nem de internet.
#
# POR QUE MANDAR NÚMEROS E NÃO A IMAGEM DO OLED?
#   imagem do OLED: 1024 bytes por quadro;  estado: 16 bytes.
#   Menos dados no rádio = menos atraso e quase nenhum tempo de CPU.
#   Quem desenha o painel é o computador, que tem processamento de sobra.
#
# DUAS "CARACTERÍSTICAS" (canais de dados) no mesmo serviço:
#
#   ESTADO (ler + notificar), 16 bytes, struct "<BBBBBBBBBBBHHB":
#     versão, estado, flags, bpm, spo2, progresso(0-255), batidas(0-255,
#     contador que dá a volta), fase do desafio, repouso, pico, alvo,
#     tempo (décimos de s), recuperação (décimos de s; 0xFFFF = não voltou),
#     sequência(0-255)
#       estado: 0 sem sensor, 1 sem dedo, 2 estabilizando, 3 pronto
#       flags:  bit0 leitura estável, bit1 SpO2 presumido, bit2 som ligado
#       fase:   0 sem desafio, 1 repouso (esperando), 2 repouso (medindo),
#               3 exercício, 4 volta (esperando dedo), 5 recuperação, 6 resultado
#       tempo:  fases 2-3 = tempo que FALTA; fases 4-5 = tempo desde o exercício
#
#   ONDA (notificar), até 18 bytes, struct "<BB" + n x "h":
#     sequência, n (quantos pontos), n pontos da onda PPG (inteiros de 16 bits)
#     A placa junta 8 pontos (~0,3 s) e manda de uma vez.
#
#   Os dois pacotes cabem no tamanho padrão do BLE (20 bytes por notificação),
#   então funcionam com qualquer computador, sem negociar nada.
#
# Tudo aqui é NÃO BLOQUEANTE: gatts_notify() só coloca o pacote na fila do
# rádio e retorna na hora.
#
# PRIVACIDADE: só vão números (sem nome nem identificação). O BLE alcança
# ~10 m e estas notificações não são criptografadas: qualquer aparelho por
# perto que conheça o formato poderia ler o BPM - por isso nada pessoal é
# enviado.
# ---------------------------------------------------------------------------

import struct
import time
import bluetooth
from micropython import const

# Identificadores (UUIDs) aleatórios de 128 bits. A página usa os MESMOS.
UUID_SERVICO = bluetooth.UUID("448e804d-b3e1-4c80-89f5-91c53751f51a")
UUID_ESTADO = bluetooth.UUID("114b64c2-3004-4c6f-8311-1dbaa117286e")
UUID_ONDA = bluetooth.UUID("ab2cad3c-87af-494c-9f9f-62b21297da07")

VERSAO_PACOTE = 1
FORMATO_ESTADO = "<BBBBBBBBBBBHHB"
PONTOS_POR_PACOTE = 8
SEM_VALOR = 0xFFFF

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)
_ADV_FLAGS = const(0x01)
_ADV_NOME = const(0x09)
_ADV_UUID128 = const(0x07)


def _campo_anuncio(tipo, valor):
    return struct.pack("BB", len(valor) + 1, tipo) + valor


def _byte(v):
    v = int(v)
    return 0 if v < 0 else (255 if v > 255 else v)


def _decimos(segundos):
    if segundos is None:
        return SEM_VALOR
    v = int(segundos * 10)
    return 0 if v < 0 else (SEM_VALOR - 1 if v >= SEM_VALOR else v)


class PainelBLE:
    def __init__(self, prefixo_nome="Batimentos", intervalo_min_ms=100, reenvio_ms=1000):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        # Nome com o final do endereço MAC: numa sala com várias placas,
        # cada uma aparece com um nome diferente.
        mac = self._ble.config("mac")[1]
        self.nome = "%s-%02X%02X" % (prefixo_nome, mac[4], mac[5])
        self._ble.config(gap_name=self.nome)
        self._ble.irq(self._irq)
        ((self._h_estado, self._h_onda),) = self._ble.gatts_register_services((
            (UUID_SERVICO, (
                (UUID_ESTADO, _FLAG_READ | _FLAG_NOTIFY),
                (UUID_ONDA, _FLAG_NOTIFY),
            )),
        ))
        self._intervalo_min_ms = intervalo_min_ms
        self._reenvio_ms = reenvio_ms
        self._conexoes = set()
        self._ativo = True
        self._ultimo_estado = None
        self._ultimo_envio = None
        self._seq = 0
        self._seq_onda = 0
        self._pontos = []
        self.pacotes_enviados = 0
        # Anúncio (até 31 bytes): flags + nome. O UUID de 128 bits não cabe
        # junto, então vai na "resposta de scan".
        self._anuncio = (_campo_anuncio(_ADV_FLAGS, b"\x06") +
                         _campo_anuncio(_ADV_NOME, self.nome.encode()))
        self._resposta = _campo_anuncio(_ADV_UUID128, bytes(UUID_SERVICO))
        self._anunciar()

    # ------------------------------------------------------- conexão
    def _irq(self, evento, dados):
        # Chamada pelo sistema BLE (interrupção): faça pouco aqui!
        if evento == _IRQ_CENTRAL_CONNECT:
            self._conexoes.add(dados[0])
            self._ultimo_estado = None        # manda o estado já na próxima volta
        elif evento == _IRQ_CENTRAL_DISCONNECT:
            self._conexoes.discard(dados[0])
            if self._ativo:                   # (ao desligar, não re-anuncia)
                self._anunciar()              # volta a ficar visível

    def _anunciar(self):
        # Anuncia a cada 100 ms: o computador acha a placa rapidinho.
        self._ble.gap_advertise(100_000, adv_data=self._anuncio, resp_data=self._resposta)

    @property
    def conectado(self):
        return bool(self._conexoes)

    def _notificar(self, handle, pacote):
        for conexao in self._conexoes:
            try:
                self._ble.gatts_notify(conexao, handle, pacote)
            except OSError:
                pass        # fila do rádio cheia: o próximo pacote traz dados novos

    # --------------------------------------------------------- envio
    def publicar(self, agora, estado, estavel, presumido, som, bpm, spo2, progresso,
                 batidas, fase=0, repouso=0, pico=0, alvo=0, tempo_s=0,
                 recuperacao_s=None):
        """Envia o estado se ele mudou (no máximo a cada intervalo_min_ms) ou,
        mesmo sem mudança, a cada reenvio_ms (para a página saber que a
        conexão continua viva). Retorna na hora."""
        if not self._conexoes:
            return
        campos = (_byte(estado),
                  (1 if estavel else 0) | (2 if presumido else 0) | (4 if som else 0),
                  _byte(bpm), _byte(spo2), _byte(progresso * 255 + 0.5),
                  batidas & 0xFF, _byte(fase), _byte(repouso), _byte(pico), _byte(alvo),
                  _decimos(tempo_s), _decimos(recuperacao_s))
        if self._ultimo_envio is not None:
            passou = time.ticks_diff(agora, self._ultimo_envio)
            if passou < self._intervalo_min_ms:
                return
            if campos == self._ultimo_estado and passou < self._reenvio_ms:
                return
        self._seq = (self._seq + 1) & 0xFF
        pacote = struct.pack(FORMATO_ESTADO, VERSAO_PACOTE, *campos, self._seq)
        # gatts_write guarda o valor (para quem LER a característica);
        # a notificação avisa quem está conectado.
        self._ble.gatts_write(self._h_estado, pacote)
        self._notificar(self._h_estado, pacote)
        self._ultimo_estado = campos
        self._ultimo_envio = agora
        self.pacotes_enviados += 1

    def adicionar_onda(self, valor):
        """Guarda um ponto da onda; a cada 8 pontos envia um pacote."""
        if not self._conexoes:
            self._pontos = []
            return
        v = int(valor)
        self._pontos.append(-32767 if v < -32767 else (32767 if v > 32767 else v))
        if len(self._pontos) >= PONTOS_POR_PACOTE:
            n = len(self._pontos)
            self._seq_onda = (self._seq_onda + 1) & 0xFF
            pacote = struct.pack("<BB%dh" % n, self._seq_onda, n, *self._pontos)
            self._notificar(self._h_onda, pacote)
            self._pontos = []

    def desligar(self):
        # Marca como inativo ANTES: desligar o rádio derruba a conexão e
        # dispara o evento "desconectou", que não deve tentar re-anunciar
        # com o rádio já desligado.
        self._ativo = False
        self._conexoes = set()
        self._ble.gap_advertise(None)
        self._ble.active(False)
