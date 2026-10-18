"""
Etapa 6: entregas do case. Junta a regra (etapa 4) e a calibração (etapa 5) e escreve os arquivos pedidos.

Entradas: data/interim/decisoes.csv, data/interim/calibracao.json, data/interim/temas_classificacao.csv
Saídas:   outputs/publicacao.csv  (uma linha por questão: id, decisao, tema_central_id, extras_ids, confianca, motivo)
          outputs/previsao.txt    (precisão e cobertura previstas, com intervalo e explicação)
          outputs/metricas.md     (tabela por nível, validação cruzada, comparação com um modelo só, custo)

Decisão final:
  nível em niveis_publicaveis (calibração)  → publicar
  candidata de nível não publicável e E     → revisar, com a sugestão como tema central e o motivo
  fora (etapa 4)                            → fora, sem tema central

Confiança = (acertos + 1) / (n + 2) do nível da questão no gabarito (prior Beta(1, 1), calculado na etapa 5).
"fora" não tem nível medido (nenhuma rotulada): recebe o prior sem dados, 0,5. É a mesma conta com n = 0.

Previsão:
  precisão  ponto = média da confiança das publicadas (a mesma estimativa da coluna confianca);
            intervalo = Wilson das publicadas rotuladas (z de settings.yaml)
  cobertura ponto = publicadas / 359 (é uma escolha nossa, não uma estimativa);
            intervalo = cobertura dos cortes que a validação cruzada escolheu em cada parte: mostra quanto o
            corte mudaria com outra amostra de rótulos

O validador roda antes de gravar e faz o script parar se alguma regra do formato falhar.

Uso:
    python -m src.entregas
"""

import json
import sys

import pandas as pd

from src.config import SETTINGS, caminho
from src.decisao import NIVEIS, TEMAS, Arvore, ids, ler

DECISOES = caminho("interim") / "decisoes.csv"
CALIBRACAO = caminho("interim") / "calibracao.json"
CUSTOS = caminho("outputs") / "custos.json"
SAIDA_PUB = caminho("outputs") / "publicacao.csv"
SAIDA_PREV = caminho("outputs") / "previsao.txt"
SAIDA_MET = caminho("outputs") / "metricas.md"

N_QUESTOES = 359
COLUNAS = ["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"]
CANDIDATOS = NIVEIS[:-1]


def motivo_revisar(r, cal: dict) -> str:
    """Candidata que não publica: diz por quê (nível abaixo do corte) e mantém o motivo da regra, se houver."""
    if r.nivel == "E":
        return r.motivo
    t = next(x for x in cal["por_nivel"] if x["nivel"] == r.nivel)
    medido = f"{t['acertos']}/{t['n']} no gabarito" if t["n"] else "sem questões no gabarito"
    base = f"nível {r.nivel} não publica ({medido}; alvo {cal['precisao_alvo']:.0%})"
    return f"{base}; {r.motivo}" if r.motivo else base


def montar(dec: pd.DataFrame, cal: dict) -> pd.DataFrame:
    conf = cal["confianca_por_nivel"]
    prior = SETTINGS["calibracao"]["prior"]
    sem_dados = prior[0] / sum(prior)
    linhas = []
    for r in dec.itertuples():
        if r.decisao_previa == "fora":
            linhas.append([r.id, "fora", "", "", sem_dados, r.motivo])
        elif r.nivel in cal["niveis_publicaveis"]:
            linhas.append([r.id, "publicar", r.tema_central_id, r.extras_ids, conf[r.nivel], ""])
        else:
            linhas.append([r.id, "revisar", r.tema_central_id, r.extras_ids, conf[r.nivel], motivo_revisar(r, cal)])
    pub = pd.DataFrame(linhas, columns=COLUNAS)
    pub["confianca"] = pub.confianca.round(2)
    return pub


def validar(pub: pd.DataFrame, arv: Arvore) -> list[str]:
    """Regras do formato de publicacao.csv (LEIA-ME do case) e da árvore. Lista vazia = ok."""
    erros = []
    if list(pub.columns) != COLUNAS:
        erros.append(f"colunas {list(pub.columns)} ≠ {COLUNAS}")
    if len(pub) != N_QUESTOES:
        erros.append(f"{len(pub)} linhas, esperado {N_QUESTOES}")
    if pub.id.duplicated().any():
        erros.append(f"ids repetidos: {sorted(pub.id[pub.id.duplicated()])}")
    for r in pub.itertuples():
        if r.decisao not in ("publicar", "revisar", "fora"):
            erros.append(f"{r.id}: decisão inválida {r.decisao!r}")
            continue
        if not 0 <= float(r.confianca) <= 1:
            erros.append(f"{r.id}: confiança {r.confianca} fora de [0, 1]")
        if r.decisao in ("revisar", "fora") and not r.motivo:
            erros.append(f"{r.id}: {r.decisao} sem motivo")
        if r.decisao == "fora":
            if r.tema_central_id:
                erros.append(f"{r.id}: fora com tema central")
            continue
        if r.tema_central_id not in arv.publicavel:
            erros.append(f"{r.id}: tema central {r.tema_central_id!r} não publicável")
            continue
        for e in ids(r.extras_ids):
            if e not in arv.publicavel:
                erros.append(f"{r.id}: extra {e} não publicável")
            elif e in arv.ramo(r.tema_central_id):
                erros.append(f"{r.id}: extra {e} no ramo do central {r.tema_central_id}")
    return erros


def previsao(pub: pd.DataFrame, cal: dict, dec: pd.DataFrame) -> tuple[dict, str]:
    publicadas = pub[pub.decisao == "publicar"]
    n_pub = len(publicadas)
    prec = float(publicadas.confianca.mean()) if n_pub else 0.0
    w = cal["wilson"] if n_pub else [0.0, 0.0]
    cob = n_pub / N_QUESTOES
    # Cobertura de cada corte escolhido na validação cruzada, aplicada às 359.
    por_nivel = dec.nivel.value_counts()
    cobs = [sum(por_nivel.get(nv, 0) for nv in CANDIDATOS[:c]) / N_QUESTOES
            for c in cal["validacao_cruzada"]["cortes"]] + [cob]
    num = {"precisao": prec, "precisao_inf": w[0], "precisao_sup": w[1],
           "cobertura": cob, "cobertura_inf": min(cobs), "cobertura_sup": max(cobs)}

    vc = cal["validacao_cruzada"]
    vc_txt = (f"{vc['acertos']}/{vc['publicadas']} = {vc['precisao']:.0%}" if vc["publicadas"]
              else "nenhuma questão publicada nas partes de teste")
    niveis = ", ".join(cal["niveis_publicaveis"]) or "nenhum"
    t = (
        f"precisao_prevista: {prec:.2f}   # fração das publicadas que estará certa\n"
        f"precisao_intervalo: {w[0]:.2f}-{w[1]:.2f}\n"
        f"cobertura_prevista: {cob:.2f}  # fração das questões que você publicou\n"
        f"cobertura_intervalo: {num['cobertura_inf']:.2f}-{num['cobertura_sup']:.2f}\n"
        "\n"
        "Como cheguei nos números\n"
        "\n"
        "Cada questão recebe um nível (A a E) por uma regra determinística: os dois modelos (gpt-5.4-mini e\n"
        "gpt-6-luna) concordam? E quantas evidências independentes apontam para o mesmo ramo (lei citada,\n"
        "assunto de origem, top-3 da busca híbrida)? Penalidades descem um nível. O gabarito manual\n"
        f"({cal['rotuladas']} questões rotuladas, de uma amostra estratificada de 80 sorteada às cegas) mede a\n"
        "precisão de cada nível; um acerto é o tema do gabarito, o pai ou um filho.\n"
        "\n"
        f"Publicam os níveis cuja precisão acumulada no gabarito é ≥ {cal['precisao_alvo']:.0%}: {niveis}\n"
        f"({cal['acertos_na_amostra']}/{cal['publicadas_na_amostra']} acertos entre as publicadas rotuladas).\n"
        f"Critério: {cal['criterio']}. O critério mais rigoroso (limite inferior de Wilson ≥ 95%) não é\n"
        "alcançável com este gabarito: mesmo sem erro, certificar 95% com z = 1,96 exige ≥ 73 publicadas\n"
        "rotuladas, e com um erro, ≥ 110. Por isso o corte usa a precisão observada e o Wilson vira a incerteza.\n"
        "\n"
        "Precisão prevista: média da confiança das publicadas, (acertos + 1) / (n + 2) do nível de cada uma\n"
        "(prior Beta(1, 1)). É menor que a precisão observada de propósito: com poucos rótulos, 100% observado\n"
        f"não é uma previsão crível. Intervalo: Wilson (z = {cal['z']}) das publicadas rotuladas.\n"
        f"Validação cruzada ({len(vc['cortes'])} partes; cada questão julgada por um corte escolhido sem ela):\n"
        f"{vc_txt}.\n"
        "\n"
        f"Cobertura prevista: {n_pub} publicadas de {N_QUESTOES}. É exata (decidimos quem publica); o intervalo\n"
        "mostra a cobertura dos cortes que a validação cruzada escolheu em cada parte, isto é, quanto o\n"
        "corte mudaria com outra amostra de rótulos.\n"
        "\n"
        "Limites: o intervalo de precisão é largo porque o gabarito é pequeno; cada questão a mais rotulada\n"
        "estreita o intervalo e pode liberar o nível seguinte (rodar make avaliacao e make entregas).\n"
    )
    return num, t


def metricas(pub: pd.DataFrame, cal: dict, num: dict, dec: pd.DataFrame) -> str:
    por_nivel = dec.nivel.replace("", "fora").value_counts()
    linhas = ["| Nível | Questões | Rotuladas | Acertos | Precisão | Wilson (z = {z}) | Confiança | Decisão |".format(z=cal["z"]),
              "|---|---|---|---|---|---|---|---|"]
    for t in cal["por_nivel"]:
        nv = t["nivel"]
        prec = f"{t['precisao']:.0%}" if t["n"] else "–"
        dec_nv = "publicar" if nv in cal["niveis_publicaveis"] else "revisar"
        linhas.append(f"| {nv} | {por_nivel.get(nv, 0)} | {t['n']} | {t['acertos']} | {prec} | "
                      f"{t['wilson_inf']:.0%}–{t['wilson_sup']:.0%} | {cal['confianca_por_nivel'][nv]:.2f} | {dec_nv} |")
    linhas.append(f"| fora | {por_nivel.get('fora', 0)} | – | – | – | – | – | fora |")

    vc = cal["validacao_cruzada"]
    contagem = pub.decisao.value_counts()
    iso = cal["acerto_isolado"]
    custo = ""
    if CUSTOS.exists():
        c = json.loads(CUSTOS.read_text(encoding="utf-8"))["total"]
        custo = f"\n## Custo\n\nReprodução completa sem cache: US$ {c['custo_total_usd']:.2f} (`make custos`).\n"
    return (
        "# Métricas\n\n"
        f"Gerado por `make entregas` a partir de {cal['rotuladas']} questões rotuladas no gabarito.\n\n"
        "## Decisões\n\n"
        f"| publicar | revisar | fora |\n|---|---|---|\n"
        f"| {contagem.get('publicar', 0)} | {contagem.get('revisar', 0)} | {contagem.get('fora', 0)} |\n\n"
        f"Precisão prevista {num['precisao']:.2f} ({num['precisao_inf']:.2f}–{num['precisao_sup']:.2f}); "
        f"cobertura {num['cobertura']:.2f} ({num['cobertura_inf']:.2f}–{num['cobertura_sup']:.2f}).\n\n"
        "## Por nível\n\n" + "\n".join(linhas) + "\n\n"
        f"Critério de corte: `{cal['criterio']}` ≥ {cal['precisao_alvo']:.0%} na precisão acumulada. "
        f"Pelo limite inferior de Wilson, seria preciso ≥ {cal['n_minimo_para_certificar']} publicadas "
        "rotuladas sem erro.\n\n"
        "## Validação cruzada\n\n"
        f"{vc['publicadas']} publicadas nas partes de teste, {vc['acertos']} acertos"
        + (f" ({vc['precisao']:.0%})" if vc["publicadas"] else "")
        + f"; cortes escolhidos por parte: {vc['cortes']} (níveis publicados a partir de A).\n\n"
        "## A regra contra um modelo sozinho\n\n"
        "Acerto do tema central em todas as rotuladas (sem abster):\n\n"
        f"| gpt-5.4-mini (A) | gpt-6-luna (B) | baseline (sem sinais) |\n|---|---|---|\n"
        f"| {iso['a']:.0%} | {iso['b']:.0%} | {iso['baseline']:.0%} |\n\n"
        "A regra não tenta acertar mais que um modelo em todas as questões: ela escolhe em quais questões o "
        "acerto é alto o bastante para publicar sem revisão.\n"
        + custo
    )


def main() -> None:
    arv = Arvore(ler(TEMAS))
    dec = ler(DECISOES)
    cal = json.loads(CALIBRACAO.read_text(encoding="utf-8"))
    if "cortes" not in cal["validacao_cruzada"]:
        sys.exit("calibracao.json antigo: rode make avaliacao antes.")

    pub = montar(dec, cal)
    erros = validar(pub, arv)
    if erros:
        sys.exit("Validação falhou:\n  " + "\n  ".join(erros))

    num, txt = previsao(pub, cal, dec)
    pub.to_csv(SAIDA_PUB, index=False, encoding="utf-8", float_format="%.2f")
    SAIDA_PREV.write_text(txt, encoding="utf-8")
    SAIDA_MET.write_text(metricas(pub, cal, num, dec), encoding="utf-8")

    print(pub.decisao.value_counts().to_string(), "\n")
    print(txt.split("\n\n")[0])
    print(f"\n→ {SAIDA_PUB}\n→ {SAIDA_PREV}\n→ {SAIDA_MET}")


if __name__ == "__main__":
    main()
