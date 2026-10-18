"""Nó de consenso e ramo: a regra só pode juntar votos de um jeito que a regra de acerto aceite."""

import pandas as pd

from src.decisao import TEMAS, Arvore

ARV = Arvore(pd.read_csv(TEMAS, dtype=str, keep_default_na=False))


def test_consenso():
    assert ARV.consenso("5159", "5159") == ("exata", "5159")
    assert ARV.consenso("5159", "5157") == ("pai_filho", "5157")       # Furto × Crimes contra o Patrimônio
    assert ARV.consenso("5150", "5151") == ("irmaos", "5149")          # Homicídio × Feminicídio → Crimes contra a Vida
    assert ARV.consenso("4704", "4708") == ("diverge", "")             # irmãos sob a raiz: raiz não é publicável
    assert ARV.consenso("5063", "5466") == ("sobreposicao", "")        # Ação Penal em Penal × Processo Penal
    assert ARV.consenso("6726", "5199") == ("exata", "5199")           # duplicata vira o canônico


def test_ramo_e_a_regra_de_acerto():
    assert ARV.ramo("5157") >= {"5157", "5159", "5158"} and "5062" in ARV.ramo("5157")
    assert "5158" not in ARV.ramo("5159")                               # irmão não é acerto
