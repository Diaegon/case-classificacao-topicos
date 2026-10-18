"""
Etapa 2: sinais independentes para cada questão.

Entradas: data/interim/questoes_tratadas.csv, data/interim/temas_classificacao.csv,
          config/regras_leis.yaml, config/mapa_assunto_origem.csv
Saída:    data/interim/sinais.csv

    (I)   busca híbrida   → src/sinais_busca.py   (vai para o juiz)
    (II)  regras de lei   → src/sinais_leis.py    (vai para o juiz)
    (III) assunto origem  → src/sinais_assunto.py (só para a regra de decisão)

Listas em colunas de texto: ids separados por ";" e detalhes em JSON, para o CSV continuar legível.

Uso:
    python -m src.sinais                        # requer o mapa de assunto
    python -m src.sinais --propor-mapa-assunto  # gera a proposta do mapa (não sobrescreve)
"""

import argparse
import json

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from src.cliente_api import Cliente
from src.config import SETTINGS, caminho
from src.sinais_assunto import carregar_mapa, propor_mapa
from src.sinais_busca import buscar, tokens
from src.sinais_leis import carregar_regras, sinal_leis

QUESTOES = caminho("interim") / "questoes_tratadas.csv"
TEMAS = caminho("interim") / "temas_classificacao.csv"
SAIDA = caminho("interim") / "sinais.csv"


def ler():
    q = pd.read_csv(QUESTOES, dtype=str, keep_default_na=False)
    t = pd.read_csv(TEMAS, dtype=str, keep_default_na=False)
    return q, t


def rodar_busca(q: pd.DataFrame, t: pd.DataFrame) -> list[dict]:
    pub = t[t.publicavel == "True"].reset_index(drop=True)
    modelo = SETTINGS["modelos"]["embedding_model"]
    chars = pub.texto_embedding.str.len().sum() + q.texto_completo.str.len().sum()
    preco = SETTINGS["precos"][modelo]["input"]
    print(f"Embeddings: {len(pub)} temas + {len(q)} questões, ~{chars / 3.5:,.0f} tokens, "
          f"custo estimado ≤ US$ {chars / 3.5 * preco / 1e6:.4f} (zero se estiver em cache)")
    cli = Cliente(etapa="etapa2_sinais")
    vet_t = np.array(cli.embeddings(modelo, pub.texto_embedding.tolist()))
    vet_q = np.array(cli.embeddings(modelo, q.texto_completo.tolist()))
    cli.salvar_custos()
    bm25 = BM25Okapi([tokens(s) for s in pub.texto_bm25])
    pai = dict(zip(t.tema_id, t.parent_id))
    return buscar(vet_q, vet_t, [tokens(s) for s in q.texto_completo], bm25,
                  pub.tema_id.tolist(), pai, set(pub.tema_id))


def resumo(df: pd.DataFrame, t: pd.DataFrame) -> None:
    """Cobertura de cada sinal e concordância entre eles (exata e no top-10)."""
    n = len(df)
    top = df.busca_top_ids.str.split(";")
    top1 = top.str[0]
    lei = df.lei_temas.str.split(";").where(df.lei_temas != "", None)
    tem_lei, tem_ass = lei.notna(), df.assunto_tema_id != ""
    print(f"\nCobertura ({n} questões)")
    print(f"  busca híbrida:   {n} (100%) | cos máx mediano {df.cos_max.median():.3f}")
    print(f"  regra de lei:    {tem_lei.sum()} ({tem_lei.mean():.0%}); com citação no enunciado: {df.lei_no_enunciado.sum()}")
    print(f"  assunto origem:  {tem_ass.sum()} ({tem_ass.mean():.0%})")

    def taxa(mask, cond):
        return f"{cond[mask].sum()}/{mask.sum()} ({cond[mask].mean():.0%})" if mask.sum() else "–"

    # "Ramo" = mesmo tema, pai ou filho: a regra de acerto do case. A comparação exata subestima a
    # concordância quando um sinal aponta o tema e o outro um subtema dele.
    pai = dict(zip(t.tema_id, t.parent_id))
    filhos = {}
    for f, p in pai.items():
        filhos.setdefault(p, set()).add(f)
    ramo = lambda tid: {tid, pai.get(tid, "")} | filhos.get(tid, set()) if tid else set()
    def conc(a_ids, b_ids, por_ramo):
        if por_ramo:
            return pd.Series([bool(set().union(*map(ramo, a)) & set(b)) if a else False for a, b in zip(a_ids, b_ids)])
        return pd.Series([bool(set(a) & set(b)) if a else False for a, b in zip(a_ids, b_ids)])

    tudo = pd.Series(True, index=df.index)
    lei_l = [l or [] for l in lei]
    ass_l = [[a] if a else [] for a in df.assunto_tema_id]
    t1 = [[x] for x in top1]
    print(f"\nConcordância{'':32}exata           ramo (tema, pai ou filho)")
    linhas = [
        ("embedding × BM25 (top-1)", tudo, [[x] for x in df.top1_emb], [[x] for x in df.top1_bm25]),
        ("lei × busca top-1", tem_lei, lei_l, t1),
        ("lei × busca top-10", tem_lei, lei_l, list(top)),
        ("assunto × busca top-1", tem_ass, ass_l, t1),
        ("assunto × busca top-10", tem_ass, ass_l, list(top)),
        ("lei × assunto", tem_lei & tem_ass, lei_l, ass_l),
    ]
    for nome, mask, a, b in linhas:
        print(f"  {nome:42}{taxa(mask, conc(a, b, False)):16}{taxa(mask, conc(a, b, True))}")
    titulo = dict(zip(t.tema_id, t.titulo))
    print("\nTemas mais frequentes no top-1 da busca:")
    for tid, c in top1.value_counts().head(8).items():
        print(f"  {c:3}  {tid} {titulo[tid]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--propor-mapa-assunto", action="store_true")
    args = ap.parse_args()

    q, t = ler()
    publicaveis = set(t.tema_id[t.publicavel == "True"])
    busca = rodar_busca(q, t)
    if args.propor_mapa_assunto:
        top10 = {qid: {x["tema_id"] for x in b["top"]} for qid, b in zip(q.id, busca)}
        propor_mapa(q, t, top10)
        return

    regras = carregar_regras(publicaveis)
    mapa = carregar_mapa(publicaveis)
    linhas = []
    for r, b in zip(q.itertuples(), busca):
        leis = sinal_leis(r.enunciado, r.alternativas, regras)
        linhas.append({
            "id": r.id,
            "busca_top_ids": ";".join(x["tema_id"] for x in b["top"]),
            "busca_pais_ids": ";".join(b["pais"]),
            "busca_json": json.dumps(b["top"], ensure_ascii=False),
            "cos_max": b["cos_max"],
            "top1_emb": b["top1_emb"],
            "top1_bm25": b["top1_bm25"],
            "lei_temas": ";".join(sorted({tid for l in leis for tid in l["temas"]})),
            "lei_no_enunciado": any(l["onde"] != "alternativas" for l in leis),
            "lei_json": json.dumps(leis, ensure_ascii=False) if leis else "",
            "assunto_tema_id": mapa.get((r.disciplina, r.assunto_origem), ""),
        })
    df = pd.DataFrame(linhas)
    df.to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"{len(df)} questões → {SAIDA}")
    resumo(df, t)


if __name__ == "__main__":
    main()
