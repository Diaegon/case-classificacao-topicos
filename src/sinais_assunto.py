"""
Etapa 2, sinal III: assunto de origem → tema (config/mapa_assunto_origem.csv).

O assunto vem do site de origem e é sujo (Maria da Penha rotulada como "Inquérito Policial";
"Concurso de Crimes" usado como lixeira). Vale só como voto fraco, e só na regra de decisão:
NÃO vai para o juiz (decisão do usuário), para não ancorar o voto no erro.

A proposta do mapa é automática e revisável:
  1. similaridade do assunto com o título dos temas publicáveis (rapidfuzz token_set_ratio, sem
     pontuação: "Procedimento do Júri" ~ "Procedimento do Tribunal do Júri"). Empates em 100 são
     comuns (um título curto contido em vários), e o desempate é a semelhança do texto inteiro
     (token_sort_ratio) e depois a mesma disciplina. Assunto composto ("Crimes contra o
     patrimônio, Furto") é quebrado nas vírgulas e vale a melhor parte;
  2. concordância com a busca: em que fração das questões daquele assunto o tema sugerido, o pai
     ou um filho dele (a mesma regra de acerto do case) aparece no top-10 da busca. Assunto usado
     como lixeira tem concordância baixa.
  O tema só é aceito (`tema_id`) com similaridade ≥ 90 e, nos assuntos com ≥ 5 questões,
  concordância ≥ 30%; o resto fica vazio, com o motivo, para revisão.
  Por que o filtro de concordância só vale com ≥ 5 questões: com 1 ou 2, a "concordância" é
  decidida pela própria questão, e o voto do assunto passaria a concordar com a busca por
  construção, perdendo a independência que é o motivo de existir deste sinal.
"""

import csv
import re
import sys

import pandas as pd
from rapidfuzz import fuzz, utils

from src.config import RAIZ
from src.sinais_busca import dobrar

MAPA = RAIZ / "config" / "mapa_assunto_origem.csv"
COLUNAS = ["disciplina", "assunto_origem", "n_questoes", "tema_sugerido", "titulo_sugerido",
           "similaridade", "concordancia_busca", "tema_id", "motivo"]
MIN_SIM, MIN_CONC, MIN_N_CONC = 90, 0.30, 5
# Assuntos sabidamente usados como lixeira no site de origem (diagnóstico prévio do usuário).
LIXEIRAS = {("Direito Penal - Legislação Especial", "Concurso de Crimes")}


def _limpo(s: str) -> str:
    return dobrar(re.sub(r"\(?\s*parte\s*\d+\s*\)?", " ", s, flags=re.I)).strip()


def _melhor(partes: list[str], temas: pd.DataFrame) -> tuple[str, tuple[int, int]]:
    """→ (tema, (token_set, token_sort)) do melhor título."""
    melhor, chave_melhor = "", (-1, -1)
    for _, t in temas.iterrows():
        tit = _limpo(t.titulo)
        chave = max((round(fuzz.token_set_ratio(p, tit, processor=utils.default_process)),
                     round(fuzz.token_sort_ratio(p, tit, processor=utils.default_process))) for p in partes)
        if chave > chave_melhor:
            melhor, chave_melhor = t.tema_id, chave
    return melhor, chave_melhor


def sugerir(assunto: str, temas: pd.DataFrame, disciplina: str) -> tuple[str, int]:
    """Melhor tema publicável para o assunto. Primeiro na mesma disciplina; se lá nada passar de
    MIN_SIM, na árvore toda (ex.: "Teoria da Pena" vindo de Legislação Especial é tema de Penal).
    Fora da disciplina a similaridade é a do texto inteiro (token_sort): token_set dá 100 quando um
    título está contido no outro, e "Princípios fundamentais do direito processual penal" iria para
    "Princípios do Direito Penal"."""
    partes = [p for p in (_limpo(x) for x in assunto.split(",")) if p]
    tid, (sim, _) = _melhor(partes, temas[temas.disciplina == disciplina])
    if sim >= MIN_SIM:
        return tid, sim
    tid, (_, sim_inteiro) = _melhor(partes, temas)
    return tid, sim_inteiro


def propor_mapa(questoes: pd.DataFrame, temas: pd.DataFrame, top10: dict[str, set[str]]) -> None:
    """Gera config/mapa_assunto_origem.csv. Não sobrescreve: o arquivo pode ter revisão sua."""
    if MAPA.exists():
        sys.exit(f"{MAPA} já existe (pode estar revisado). Apague-o para gerar uma nova proposta.")
    pub = temas[temas.publicavel == "True"]
    titulo = dict(zip(temas.tema_id, temas.titulo))
    pai = dict(zip(temas.tema_id, temas.parent_id))
    parentes = lambda tid: {tid, pai.get(tid, "")} | {f for f, p in pai.items() if p == tid}
    linhas = []
    for (disc, assunto), grupo in questoes.groupby(["disciplina", "assunto_origem"]):
        if not assunto:
            continue
        tid, sim = sugerir(assunto, pub, disc)
        conc = sum(bool(parentes(tid) & top10[q]) for q in grupo.id) / len(grupo)
        if (disc, assunto) in LIXEIRAS:
            final, motivo = "", "lixeira conhecida do site de origem"
        elif sim < MIN_SIM:
            final, motivo = "", f"similaridade {sim} < {MIN_SIM}"
        elif len(grupo) >= MIN_N_CONC and conc < MIN_CONC:
            final, motivo = "", f"tema sugerido no top-10 da busca em só {conc:.0%} das questões (lixeira?)"
        else:
            final, motivo = tid, ""
        linhas.append([disc, assunto, len(grupo), tid, titulo[tid], sim, f"{conc:.2f}", final, motivo])
    with open(MAPA, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUNAS)
        w.writerows(sorted(linhas, key=lambda r: -r[2]))
    print(f"Proposta gravada em {MAPA}: {len(linhas)} pares, {sum(1 for r in linhas if r[7])} com tema aceito.")


def carregar_mapa(publicaveis: set[str]) -> dict[tuple[str, str], str]:
    if not MAPA.exists():
        sys.exit(f"{MAPA} não existe. Rode `python -m src.sinais --propor-mapa-assunto`.")
    df = pd.read_csv(MAPA, dtype=str, keep_default_na=False)
    ruins = set(df.tema_id[df.tema_id != ""]) - publicaveis
    if ruins:
        sys.exit(f"{MAPA.name} cita temas inexistentes ou não publicáveis: {sorted(ruins)}")
    return {(r.disciplina, r.assunto_origem): r.tema_id for r in df.itertuples() if r.tema_id}
