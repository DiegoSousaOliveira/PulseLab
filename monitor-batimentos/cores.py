# cores.py
# ---------------------------------------------------------------------------
# Todas as cores da matriz 5x5 e do LED RGB, num lugar só.
#
# Os valores vão de 0 a 255 por canal (vermelho, verde, azul), mas já estão
# com BRILHO REDUZIDO: os LEDs WS2812 em 255 ofuscam e esquentam, e cada LED
# aceso nestas cores usa menos de 10% da potência máxima.
# Ex.: CORACAO = (50, 0, 8) -> (50 + 0 + 8) / (3 x 255) ≈ 7,6%.
#
# As cores foram harmonizadas para ficarem parecidas em intensidade
# (o olho humano vê o verde mais forte que o azul, por isso o verde é menor).
# ---------------------------------------------------------------------------

CORACAO = (50, 0, 8)        # coração da matriz, no pico da batida
AZUL = (0, 12, 45)          # LED RGB: BPM abaixo de 60
VERDE = (0, 40, 12)         # LED RGB: BPM de 60 a 100
LARANJA = (45, 15, 0)       # LED RGB: BPM de 100 a 140
VERMELHO = (50, 0, 4)       # LED RGB: BPM acima de 140 (e o "X" de erro)
APAGADO = (0, 0, 0)

# Faixas de BPM para o LED RGB. São só FAIXAS de valor, para visualizar a
# mudança (repouso x depois do exercício). Não têm interpretação médica.
FAIXAS_BPM = (
    (60, AZUL),       # bpm < 60
    (100, VERDE),     # 60 <= bpm <= 100
    (140, LARANJA),   # 100 < bpm <= 140
)
COR_ACIMA_DAS_FAIXAS = VERMELHO   # bpm > 140


def cor_da_faixa(bpm):
    """Devolve a cor do LED RGB para um BPM (APAGADO se ainda não há BPM)."""
    if not bpm:
        return APAGADO
    if bpm < FAIXAS_BPM[0][0]:
        return FAIXAS_BPM[0][1]
    for limite, cor in FAIXAS_BPM[1:]:
        if bpm <= limite:
            return cor
    return COR_ACIMA_DAS_FAIXAS


def escalar(cor, fator):
    """Multiplica o brilho de uma cor (fator de 0.0 a 1.0)."""
    return (int(cor[0] * fator), int(cor[1] * fator), int(cor[2] * fator))
