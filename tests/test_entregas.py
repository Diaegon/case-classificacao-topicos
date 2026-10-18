"""Validador de publicacao.csv: cada regra do formato do case derruba uma linha errada."""

import pandas as pd

from src.decisao import TEMAS, Arvore
from src.entregas import COLUNAS, N_QUESTOES, validar

ARV = Arvore(pd.read_csv(TEMAS, dtype=str, keep_default_na=False))


def base() -> pd.DataFrame:
    linhas = [[f"Q{i:04d}", "publicar", "5159", "", 0.9, ""] for i in range(1, N_QUESTOES + 1)]
    return pd.DataFrame(linhas, columns=COLUNAS)


def test_valido():
    assert validar(base(), ARV) == []


def test_contagem_e_ids():
    assert validar(base().iloc[:-1], ARV)
    df = base()
    df.loc[1, "id"] = "Q0001"
    assert any("repetidos" in e for e in validar(df, ARV))


def test_regras_por_linha():
    casos = [
        ({"decisao": "talvez"}, "decisão inválida"),
        ({"decisao": "revisar"}, "sem motivo"),
        ({"decisao": "fora", "motivo": "x"}, "fora com tema central"),
        ({"tema_central_id": "9999999"}, "não publicável"),
        ({"extras_ids": "5157"}, "no ramo"),       # pai do central
        ({"confianca": 1.5}, "fora de [0, 1]"),
    ]
    for muda, esperado in casos:
        df = base()
        for k, v in muda.items():
            df.loc[0, k] = v
        erros = validar(df, ARV)
        assert any(esperado in e for e in erros), (muda, erros)
