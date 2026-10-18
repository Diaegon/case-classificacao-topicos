"""
Etapa 5: calibração com o gabarito manual. Mede a precisão de cada nível da regra (etapa 4) e escolhe
quais níveis publicam.

Entradas: data/gold/gold_para_rotular.csv (rótulos do usuário; só as linhas com gold_tema_id contam),
          data/gold/amostra_ids.csv (peso de cada estrato), data/interim/decisoes.csv, votos_llm.csv
Saídas:   data/interim/calibracao.json        (níveis publicáveis e confiança de cada nível, para a etapa 6)
          data/interim/avaliacao_questoes.csv (uma linha por questão rotulada: previsto × gabarito)

Regra de acerto (do case): o previsto é o tema do gabarito, o pai ou um filho. Irmão é erro. Duplicatas
viram o canônico antes de comparar; os acertos que só existem por causa desse mapa são contados à parte,
porque dependem da suposição "nas duplicatas, o gabarito usa o nó original".

Escolha dos níveis: os níveis são ordenados (A melhor que B...), então só há 4 cortes possíveis:
{A}, {A,B}, {A,B,C}, {A,B,C,D}. Publica o maior corte cuja precisão acumulada passa no critério:
  limite_inferior  limite inferior do intervalo de Wilson ≥ alvo (conservador)
  pontual          precisão observada ≥ alvo (em uso desde 2026-10-18; o Wilson vira a incerteza reportada)
Por que o Wilson seria melhor: com poucas questões, 20/20 acertos não garantem 95%. Por que não deu: com
80 rótulos e um erro, nenhum corte chega lá (ver DECISOES.md).

Por que validação cruzada em vez de separar calibração e teste: com 80 rótulos, metade para cada lado
deixa os dois pequenos demais. Na validação cruzada, cada questão é testada por um corte escolhido
SEM ela, e a precisão medida assim estima o que o procedimento entrega fora da amostra.

Confiança de cada questão = média a posteriori da precisão do nível dela, com prior Beta(1, 1):
(acertos + 1) / (n + 2). Suaviza níveis com poucos rótulos.

Uso:
    python -m src.avaliacao
"""

import csv
import json
import math
import random
import sys

import pandas as pd

from src.config import SETTINGS, caminho
from src.decisao import NIVEIS, TEMAS, Arvore, ler

GOLD = caminho("gold") / "gold_para_rotular.csv"
AMOSTRA = caminho("gold") / "amostra_ids.csv"
DECISOES = caminho("interim") / "decisoes.csv"
VOTOS = caminho("interim") / "votos_llm.csv"
SAIDA_JSON = caminho("interim") / "calibracao.json"
SAIDA_CSV = caminho("interim") / "avaliacao_questoes.csv"

CFG = SETTINGS["calibracao"]
CANDIDATOS = NIVEIS[:-1]  # E é sempre revisar


def ler_gold(arq=GOLD) -> tuple[pd.DataFrame, list[str]]:
    """Linhas rotuladas do gabarito. Aceita linha com vírgula sem aspas na obs (último campo), com aviso:
    o que sobra é parte da obs, e os campos do rótulo vêm antes dela, então não mudam."""
    avisos, linhas = [], []
    with open(arq, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get(None):
                avisos.append(f"{r['id']}: obs com vírgula sem aspas (linha com campos a mais); juntei na obs")
                r["obs"] = ",".join([r["obs"], *r.pop(None)])
            if r["gold_tema_id"].strip():
                linhas.append({k: (r[k] or "").strip() for k in ["id", "gold_tema_id", "gold_extras", "certeza", "obs"]})
    return pd.DataFrame(linhas, columns=["id", "gold_tema_id", "gold_extras", "certeza", "obs"]), avisos


def acerto(pred: str, gold: str, arv: Arvore) -> tuple[bool, bool]:
    """→ (acertou, só acertou por causa do mapa de duplicatas)."""
    if not pred or not gold:
        return False, False
    cru = pred in arv.ramo(gold)
    p, g = arv.canonico.get(pred, pred), arv.canonico.get(gold, gold)
    ok = p in arv.ramo(g)
    return ok, ok and not cru


def wilson(k: int, n: int, z: float) -> tuple[float, float]:
    """Intervalo de Wilson para k acertos em n. Com n = 0, não há informação: (0, 1)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - meia), min(1.0, centro + meia)


def escolher_corte(df: pd.DataFrame, criterio: str) -> int:
    """Quantos níveis publicam (0 a 4), pela precisão acumulada das candidatas rotuladas."""
    melhor = 0
    for i in range(1, len(CANDIDATOS) + 1):
        # Nível sem nenhuma rotulada não tem precisão medida: não entra de carona no acumulado dos de cima.
        # Os níveis abaixo dele também não, porque o corte é contíguo.
        if not (df.nivel == CANDIDATOS[i - 1]).any():
            break
        sub = df[df.nivel.isin(CANDIDATOS[:i])]
        k, n = int(sub.acerto.sum()), len(sub)
        nota = wilson(k, n, CFG["z"])[0] if criterio == "limite_inferior" else k / n
        if nota >= CFG["precisao_alvo"]:
            melhor = i
    return melhor


def validacao_cruzada(df: pd.DataFrame, criterio: str) -> dict:
    """Cada questão é avaliada por um corte escolhido sem ela (k partes, seed fixa)."""
    ids = sorted(df.id)
    random.Random(SETTINGS["seed"]).shuffle(ids)
    k = min(CFG["folds"], len(ids))
    parte = {q: i % k for i, q in enumerate(ids)}
    pub = acertos = 0
    cortes = []  # corte escolhido em cada parte: mostra quanto o corte depende da amostra (etapa 6 usa)
    for f in range(k):
        treino, teste = df[df.id.map(parte) != f], df[df.id.map(parte) == f]
        c = escolher_corte(treino, criterio)
        cortes.append(c)
        sel = teste[teste.nivel.isin(CANDIDATOS[:c])]
        pub += len(sel)
        acertos += int(sel.acerto.sum())
    return {"publicadas": pub, "acertos": acertos, "rotuladas": len(df),
            "precisao": acertos / pub if pub else None, "cobertura": pub / len(df) if len(df) else None,
            "cortes": cortes}


def por_nivel(df: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for nv in NIVEIS:
        sub = df[df.nivel == nv]
        k, n = int(sub.acerto.sum()), len(sub)
        li, ls = wilson(k, n, CFG["z"])
        linhas.append({"nivel": nv, "n": n, "acertos": k, "precisao": k / n if n else None,
                       "wilson_inf": li, "wilson_sup": ls, "so_por_duplicata": int(sub.so_duplicata.sum())})
    return pd.DataFrame(linhas)


def main() -> None:
    arv = Arvore(ler(TEMAS))
    gold, avisos = ler_gold()
    for a in avisos:
        print("AVISO:", a)
    if gold.empty:
        sys.exit("Nenhuma questão rotulada em gold_para_rotular.csv.")

    # Rótulo precisa ser um id da árvore; nó não publicável (raiz) é aceito mas avisado.
    desconhecidos = gold[~gold.gold_tema_id.isin(arv.pai.keys())]
    if not desconhecidos.empty:
        sys.exit(f"gold_tema_id fora da árvore: {desconhecidos[['id', 'gold_tema_id']].to_dict('records')}")
    for r in gold[~gold.gold_tema_id.map(lambda x: arv.canonico.get(x, x)).isin(arv.publicavel)].itertuples():
        print(f"AVISO: {r.id}: gabarito {r.gold_tema_id} não é publicável (raiz de disciplina?)")

    dec = ler(DECISOES).set_index("id")
    peso = ler(AMOSTRA).set_index("id").peso_estrato.astype(float)
    df = gold.join(dec[["nivel", "decisao_previa", "tema_central_id", "concordancia", "penalidades"]], on="id")
    df["nivel"] = df.nivel.replace("", "fora")
    res = [acerto(p, g, arv) for p, g in zip(df.tema_central_id, df.gold_tema_id)]
    df["acerto"] = [a for a, _ in res]
    df["so_duplicata"] = [d for _, d in res]
    df["peso"] = df.id.map(peso)

    # Votos isolados (A, B, baseline), para o relatório: mostra o que a regra acrescenta a um modelo só.
    v = ler(VOTOS)
    for var in ["a", "b", "baseline"]:
        vv = v[v.variante == var].set_index("id")
        central = vv.tema_central_id.where(vv.nenhum_serve != "True", "")
        df[f"acerto_{var}"] = [acerto(central.get(q, ""), g, arv)[0] for q, g in zip(df.id, df.gold_tema_id)]

    tab = por_nivel(df)
    corte = escolher_corte(df, CFG["criterio"])
    corte_pontual = escolher_corte(df, "pontual")
    publicaveis = CANDIDATOS[:corte]
    sel = df[df.nivel.isin(publicaveis)]
    k, n = int(sel.acerto.sum()), len(sel)
    # Precisão ponderada pelo peso do estrato: estima a precisão nas 359, não só na amostra.
    pond = (sel.acerto * sel.peso).sum() / sel.peso.sum() if n else None

    # Teto do limite inferior: mesmo acertando tudo, n rótulos só certificam 1 / (1 + z²/n).
    z = CFG["z"]
    n_min = math.ceil(z * z * CFG["precisao_alvo"] / (1 - CFG["precisao_alvo"]))

    confianca = {nv: (int(r.acertos) + CFG["prior"][0]) / (int(r.n) + sum(CFG["prior"]))
                 for nv, r in tab.set_index("nivel").iterrows()}
    saida = {
        "rotuladas": len(df), "criterio": CFG["criterio"], "precisao_alvo": CFG["precisao_alvo"], "z": z,
        "niveis_publicaveis": publicaveis, "niveis_publicaveis_pontual": CANDIDATOS[:corte_pontual],
        "publicadas_na_amostra": n, "acertos_na_amostra": k,
        "precisao": k / n if n else None, "wilson": wilson(k, n, z), "precisao_ponderada": pond,
        "validacao_cruzada": validacao_cruzada(df, CFG["criterio"]),
        "n_minimo_para_certificar": n_min,
        "confianca_por_nivel": confianca,
        "por_nivel": tab.to_dict("records"),
        "acerto_isolado": {var: float(df[f"acerto_{var}"].mean()) for var in ["a", "b", "baseline"]},
        "avisos": avisos,
    }
    SAIDA_JSON.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    df.to_csv(SAIDA_CSV, index=False, encoding="utf-8")

    print(f"{len(df)} questões rotuladas (de {len(peso)} sorteadas)\n")
    print(tab.to_string(index=False, float_format=lambda x: f"{x:.2f}"), "\n")
    print(f"Critério: {CFG['criterio']} ≥ {CFG['precisao_alvo']:.0%} (z = {z})")
    print(f"Níveis publicáveis: {publicaveis or 'nenhum'}   (pela precisão pontual: {CANDIDATOS[:corte_pontual] or 'nenhum'})")
    if n:
        print(f"Na amostra: {k}/{n} = {k / n:.1%}, Wilson [{saida['wilson'][0]:.1%}, {saida['wilson'][1]:.1%}], "
              f"ponderada {pond:.1%}")
    print(f"Para certificar {CFG['precisao_alvo']:.0%} pelo limite inferior são precisas ≥ {n_min} publicadas "
          f"rotuladas sem erro.")
    print("Validação cruzada:", saida["validacao_cruzada"])
    print("Acerto de um modelo sozinho (todas as rotuladas):",
          {k_: f"{v_:.0%}" for k_, v_ in saida["acerto_isolado"].items()})
    if df.so_duplicata.any():
        print("Acertos que dependem do mapa de duplicatas:", list(df.id[df.so_duplicata]))
    erros = df[~df.acerto & df.nivel.isin(CANDIDATOS)]
    if not erros.empty:
        print("\nErros em candidatas:")
        for r in erros.itertuples():
            print(f"  {r.id} nível {r.nivel}: previsto {r.tema_central_id} ({arv.titulo.get(r.tema_central_id, '?')})"
                  f" × gabarito {r.gold_tema_id} ({arv.titulo.get(r.gold_tema_id, '?')})")
    print(f"\n→ {SAIDA_JSON}\n→ {SAIDA_CSV}")


if __name__ == "__main__":
    main()
