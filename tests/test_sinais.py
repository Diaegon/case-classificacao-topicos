"""Regras de lei: variações de escrita reconhecidas, sem falso positivo em números soltos."""

from src.sinais_busca import tokens
from src.sinais_leis import contar, sinal_leis

DROGAS = {"lei": "Drogas", "numeros": {"11343"}, "nomes": [], "temas": ["4708"]}


def test_variacoes_de_escrita():
    for s in ["Lei nº 11.343/06", "Lei 11343", "L. 11.343", "Lei n. º 11.343/2006", "Lei n°11.343", "art. 33 da 11.343/06"]:
        assert contar(DROGAS, s) == 1, s


def test_sem_falso_positivo():
    assert contar(DROGAS, "pena de 11.343 dias-multa") == 0          # número sem "Lei" e sem ano
    assert contar(DROGAS, "Lei 11.340/06") == 0


def test_onde_aparece():
    r = sinal_leis("Sobre a Lei 11.343/06:", "A) nada", [DROGAS])
    assert r == [{"lei": "Drogas", "temas": ["4708"], "onde": "enunciado", "n": 1}]
    assert sinal_leis("Assinale:", "A) Lei 11.343", [DROGAS])[0]["onde"] == "alternativas"


def test_tokens_bm25():
    assert tokens("Assinale a alternativa correta sobre a prisão preventiva") == ["prisao", "preven"]
