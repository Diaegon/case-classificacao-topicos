"""Regra de acerto do case e intervalo de Wilson."""

import pandas as pd

from src.avaliacao import acerto, escolher_corte, wilson
from src.decisao import TEMAS, Arvore

ARV = Arvore(pd.read_csv(TEMAS, dtype=str, keep_default_na=False))


def test_acerto_tema_pai_filho_e_irmao():
    assert acerto("5159", "5159", ARV) == (True, False)    # o próprio tema
    assert acerto("5157", "5159", ARV) == (True, False)    # previsto é o pai do gabarito
    assert acerto("5159", "5157", ARV) == (True, False)    # previsto é filho do gabarito
    assert acerto("5158", "5159", ARV) == (False, False)   # irmão é erro
    assert acerto("", "5159", ARV) == (False, False)       # sem previsão


def test_acerto_por_duplicata_e_contado_a_parte():
    assert acerto("6726", "5199", ARV) == (True, True)     # duplicata: só acerta pelo mapa


def test_wilson():
    li, ls = wilson(20, 20, 1.96)
    assert 0.83 < li < 0.84 and ls == 1.0                  # 20/20 não certifica 95%
    assert wilson(0, 0, 1.96) == (0.0, 1.0)


def test_corte_para_no_primeiro_nivel_que_falha_o_acumulado():
    df = pd.DataFrame({"nivel": ["A"] * 100 + ["B"] * 10, "acerto": [True] * 100 + [False] * 10})
    assert escolher_corte(df, "limite_inferior") == 1       # {A} passa; {A, B} cai para 91%


def test_corte_nao_inclui_nivel_sem_rotulo():
    df = pd.DataFrame({"nivel": ["A"] * 100 + ["D"] * 5, "acerto": [True] * 105})
    assert escolher_corte(df, "pontual") == 1               # C sem rótulo: nem C nem D publicam
