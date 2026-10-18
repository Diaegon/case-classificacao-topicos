"""
Etapa 2, sinal II: regras de lei (config/regras_leis.yaml).

Para cada questão: quais leis com tema próprio ela cita, onde (enunciado, alternativas ou ambos)
e quantas vezes. A citação no enunciado pesa mais: numa alternativa ela pode ser só o distrator.
"""

import re
import sys

import yaml

from src.config import RAIZ

REGRAS = RAIZ / "config" / "regras_leis.yaml"

# "Lei nº 11.343/06", "Lei 11343", "L. 11.343", "Lei n. º 10.826", "Decreto-Lei 3.688", "Lei n°9.609".
NUM_COM_LEI = re.compile(r"\b(?:Lei|L\.|Decreto-Lei|DL)\s*(?:n[\s.º°o]*)?(\d{1,2}\.?\d{3})\b", re.I)
# Número sozinho só com ponto e ano ("11.343/06"): sem o ano, "1.521" pode ser qualquer coisa.
NUM_SOLTO = re.compile(r"\b(\d{1,2}\.\d{3})/\d{2,4}\b")


def carregar_regras(temas_publicaveis: set[str]) -> list[dict]:
    cfg = yaml.safe_load(REGRAS.read_text(encoding="utf-8"))
    regras = []
    for r in cfg["leis"]:
        regras.append({"lei": r["lei"], "numeros": {str(n) for n in r["numeros"]},
                       "nomes": [re.compile(p, re.I) for p in r["nomes"]], "temas": [str(t) for t in r["temas"]]})
    for r in cfg["artigos"]:
        regras.append({"lei": r["lei"], "numeros": set(), "nomes": [re.compile(r["regex"], re.I)],
                       "temas": [str(t) for t in r["temas"]]})
    ruins = {t for r in regras for t in r["temas"]} - temas_publicaveis
    if ruins:
        sys.exit(f"{REGRAS.name} cita temas inexistentes ou não publicáveis: {sorted(ruins)}")
    return regras


def contar(regra: dict, texto: str) -> int:
    """Quantas citações da lei no texto (número com 'Lei', número com ano, ou nome)."""
    nums = [m.group(1).replace(".", "") for m in NUM_COM_LEI.finditer(texto)]
    # Um "11.343/06" já contado com "Lei" na frente não conta duas vezes.
    soltos = [m for m in NUM_SOLTO.finditer(texto)
              if not NUM_COM_LEI.search(texto[max(0, m.start() - 15):m.end()])]
    nums += [m.group(1).replace(".", "") for m in soltos]
    n = sum(1 for x in nums if x in regra["numeros"])
    return n + sum(len(p.findall(texto)) for p in regra["nomes"])


def sinal_leis(enunciado: str, alternativas: str, regras: list[dict]) -> list[dict]:
    """→ [{lei, temas, onde, n}], uma entrada por lei citada."""
    achados = []
    for r in regras:
        n_enun, n_alt = contar(r, enunciado), contar(r, alternativas)
        if n_enun or n_alt:
            onde = "ambos" if n_enun and n_alt else ("enunciado" if n_enun else "alternativas")
            achados.append({"lei": r["lei"], "temas": r["temas"], "onde": onde, "n": n_enun + n_alt})
    return achados
