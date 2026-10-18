"""
Etapa 4: regra de decisão determinística. A LLM classificou; aqui se decide o que fazer com o voto.

Entradas: data/interim/votos_llm.csv (variantes a e b; o baseline é só para o relatório),
          sinais.csv, questoes_tratadas.csv, temas_classificacao.csv
Saída:    data/interim/decisoes.csv

Para cada questão:

1. Duplicatas viram o canônico antes de comparar (o juiz só vê publicáveis, mas a regra não depende disso).

2. Nó de consenso entre os votos de A e B:
     exata       A == B                                   → o próprio tema
     pai_filho   um é pai do outro                        → o pai (acerta se o gabarito for qualquer um dos dois)
     irmaos      filhos do mesmo pai                      → o pai (idem: publicar no pai de um irmão é acerto)
     sobreposicao temas de ramos diferentes marcados como o mesmo assunto (ex.: Ação Penal 5063 × 5466)
                                                            → sem consenso: o gabarito usa só um dos dois
     diverge     qualquer outra combinação                → sem consenso
   O consenso nunca é a raiz da disciplina (nível 0, não publicável pela suposição atual).
   A árvore tem 3 níveis, então dois votos no mesmo ramo nunca distam mais de 1 nível do consenso.

3. Evidências independentes do voto, todas pela regra de acerto (tema, pai ou filho):
     lei      a lei citada aponta para o ramo do consenso (ou para um tema sobreposto a ele)
     assunto  o assunto de origem aponta para o ramo do consenso
     busca    o ramo do consenso está entre os 3 primeiros da busca

4. Nível (bucket), do mais ao menos confiável:
     A  modelos concordam (exata ou pai_filho) + 2 ou 3 evidências
     B  modelos concordam + 1 evidência
     C  modelos concordam, sem evidência
     D  modelos só concordam no pai (irmaos)
     E  sem consenso (diverge, sobreposicao, ou um dos modelos disse nenhum_serve)
   Penalidades: cada uma desce um nível (A→B, ..., D→E):
     generico       antilixeira: tema genérico só com evidência extra
     lei_contra     o enunciado cita uma lei com tema próprio que não é o do consenso
     ocr_suspeito   texto com ruído de OCR
     fora_recorte   disciplina de origem fora do recorte ou vazia

5. fora: os dois modelos dizem nenhum_serve E a busca não acha nada parecido (cosseno < cos_fora).

O limiar de PUBLICAR não é escolhido aqui: a etapa 5 mede a precisão de cada nível no gabarito e
escolhe quais publicam. Aqui sai só `decisao_previa`: "fora", "revisar" (nível E) ou "candidata".

Uso:
    python -m src.decisao
"""

import json

import pandas as pd

from src.config import SETTINGS, caminho

VOTOS = caminho("interim") / "votos_llm.csv"
SINAIS = caminho("interim") / "sinais.csv"
QUESTOES = caminho("interim") / "questoes_tratadas.csv"
TEMAS = caminho("interim") / "temas_classificacao.csv"
SAIDA = caminho("interim") / "decisoes.csv"

CFG = SETTINGS["decisao"]
NIVEIS = ["A", "B", "C", "D", "E"]


def ler(nome):
    return pd.read_csv(nome, dtype=str, keep_default_na=False)


def ids(s: str) -> list[str]:
    return [x for x in s.split(";") if x]


class Arvore:
    """Relações da árvore usadas pela regra (e pela função de acerto da etapa 5)."""

    def __init__(self, t: pd.DataFrame):
        self.pai = dict(zip(t.tema_id, t.parent_id))
        self.nivel = dict(zip(t.tema_id, t.nivel.astype(int)))
        self.canonico = dict(zip(t.tema_id, t.canonico_id))
        self.publicavel = set(t.tema_id[t.publicavel == "True"])
        self.generico = set(t.tema_id[t.generico == "True"])
        self.sobrepoe = {r.tema_id: set(ids(r.sobrepoe_ids)) for r in t.itertuples()}
        self.titulo = dict(zip(t.tema_id, t.titulo))
        self.filhos: dict[str, set[str]] = {}
        for f, p in self.pai.items():
            self.filhos.setdefault(p, set()).add(f)

    def ramo(self, x: str) -> set[str]:
        """O próprio tema, o pai e os filhos: tudo que conta como acerto se o gabarito for x."""
        return ({x, self.pai.get(x, "")} | self.filhos.get(x, set())) - {""} if x else set()

    def consenso(self, a: str, b: str) -> tuple[str, str]:
        """→ (tipo de concordância, nó de consenso ou "")."""
        a, b = self.canonico.get(a, a), self.canonico.get(b, b)
        if a == b:
            return "exata", a
        if self.pai.get(b) == a:
            return "pai_filho", a
        if self.pai.get(a) == b:
            return "pai_filho", b
        p = self.pai.get(a)
        if p and p == self.pai.get(b) and p in self.publicavel:  # pai de nível 0 não é publicável
            return "irmaos", p
        if b in self.sobrepoe.get(a, set()):
            return "sobreposicao", ""
        return "diverge", ""


def evidencias(no: str, arv: Arvore, s, q) -> dict:
    """Quais sinais independentes apoiam o nó (pela regra de acerto) e quais o contradizem."""
    ramo = arv.ramo(no)
    ramo_ou_sobreposto = ramo | set().union(*(arv.sobrepoe.get(x, set()) for x in ramo))
    leis = json.loads(s.lei_json) if s.lei_json else []
    lei_ok = any(set(l["temas"]) & ramo_ou_sobreposto for l in leis)
    # Lei citada no ENUNCIADO apontando para outro tema: sinal de que o consenso pode estar errado.
    # Citação só nas alternativas não conta (pode ser o distrator).
    lei_contra = any(l["onde"] != "alternativas" and not set(l["temas"]) & ramo_ou_sobreposto for l in leis)
    return {
        "ev_lei": lei_ok,
        "ev_assunto": s.assunto_tema_id in ramo,
        "ev_busca": bool(set(ids(s.busca_top_ids)[:CFG["busca_top_n"]]) & ramo),
        "lei_contra": lei_contra and not lei_ok,
    }


def escolher_sugestao(a: str, b: str, arv: Arvore, s, q) -> str:
    """Sem consenso: o voto com mais evidências; empate → o mais bem colocado na busca; depois A."""
    def pontos(x):
        e = evidencias(x, arv, s, q)
        top = ids(s.busca_top_ids)
        pos = min((top.index(y) for y in arv.ramo(x) if y in top), default=99)
        return (e["ev_lei"] + e["ev_assunto"] + e["ev_busca"], -pos)
    cands = [x for x in (a, b) if x]
    return max(cands, key=pontos) if cands else ""


def decidir(va, vb, s, q, arv: Arvore) -> dict:
    a = va.tema_central_id if va.nenhum_serve != "True" else ""
    b = vb.tema_central_id if vb.nenhum_serve != "True" else ""
    base = {"id": q.id, "voto_a": a, "voto_b": b, "segunda_a": va.segunda_opcao_id, "segunda_b": vb.segunda_opcao_id}

    # fora: os dois dizem que nenhum tema serve e a busca não acha nada parecido.
    if not a and not b:
        if float(s.cos_max) < CFG["cos_fora"]:
            return {**base, "decisao_previa": "fora", "nivel": "", "concordancia": "nenhum_serve",
                    "tema_central_id": "", "motivo": f"os dois modelos: nenhum tema serve; busca fraca (cos {s.cos_max})"}
        sug = ids(s.busca_top_ids)[0]
        return {**base, "decisao_previa": "revisar", "nivel": "E", "concordancia": "nenhum_serve",
                "tema_central_id": sug, "motivo": f"os dois modelos: nenhum tema serve, mas a busca acha {sug} (cos {s.cos_max})"}

    if not a or not b:
        tipo, no = "um_nenhum", ""
    else:
        tipo, no = arv.consenso(a, b)

    if no:
        ev = evidencias(no, arv, s, q)
        n_ev = ev["ev_lei"] + ev["ev_assunto"] + ev["ev_busca"]
        if tipo in ("exata", "pai_filho"):
            nivel = "A" if n_ev >= 2 else ("B" if n_ev == 1 else "C")
        else:  # irmaos: consenso no pai
            nivel = "D"
        central = no
    else:
        central = escolher_sugestao(a, b, arv, s, q)
        ev = evidencias(central, arv, s, q)
        nivel = "E"

    penal = [p for p, cond in [
        ("generico", central in arv.generico),
        ("lei_contra", ev["lei_contra"]),
        ("ocr_suspeito", q.ocr_suspeito == "True"),
        ("fora_recorte", q.disciplina_fora_recorte == "True" or q.sem_disciplina == "True"),
    ] if cond]
    nivel_base = nivel
    nivel = NIVEIS[min(NIVEIS.index(nivel) + len(penal), len(NIVEIS) - 1)]

    # Extras: o que os modelos citaram como extra, fora do ramo do central (o ramo já está coberto).
    extras = []
    for e in ids(va.extras_ids) + ids(vb.extras_ids) + [x for x in (a, b) if x and not no]:
        e = arv.canonico.get(e, e)
        if e in arv.publicavel and e not in arv.ramo(central) and e not in extras:
            extras.append(e)

    t = lambda x: f"{x} ({arv.titulo.get(x, '?')})"
    motivos = {
        "diverge": f"modelos divergem: {t(a)} vs {t(b)}",
        "sobreposicao": f"modelos em ramos sobrepostos: {t(a)} vs {t(b)}",
        "um_nenhum": f"um modelo diz que nenhum tema serve; o outro, {t(a or b)}",
    }
    motivo = motivos.get(tipo, "")
    if penal:
        motivo = "; ".join(filter(None, [motivo, "penalidades: " + ", ".join(penal)]))
    return {**base, "decisao_previa": "revisar" if nivel == "E" else "candidata", "nivel": nivel,
            "nivel_sem_penalidade": nivel_base, "concordancia": tipo, "tema_central_id": central,
            "extras_ids": ";".join(extras[:CFG["max_extras"]]), **ev, "penalidades": ";".join(penal),
            "motivo": motivo}


def main() -> None:
    v, s, q, t = ler(VOTOS), ler(SINAIS), ler(QUESTOES), ler(TEMAS)
    arv = Arvore(t)
    va = v[v.variante == "a"].set_index("id")
    vb = v[v.variante == "b"].set_index("id")
    s = s.set_index("id")
    linhas = [decidir(va.loc[r.id].rename(r.id), vb.loc[r.id], s.loc[r.id], r, arv) for r in q.itertuples()]
    df = pd.DataFrame(linhas)

    # Checagens: todo central é publicável; "fora" sem central; revisar e fora com motivo.
    assert df.tema_central_id[df.decisao_previa != "fora"].isin(arv.publicavel).all(), "central não publicável"
    assert (df.tema_central_id[df.decisao_previa == "fora"] == "").all()
    assert (df.motivo[df.decisao_previa != "candidata"] != "").all(), "revisar/fora sem motivo"
    df.to_csv(SAIDA, index=False, encoding="utf-8")

    print(f"{len(df)} questões → {SAIDA}\n")
    print(df.decisao_previa.value_counts().to_string(), "\n")
    print(pd.crosstab(df.concordancia, df.nivel.replace("", "(fora)"), margins=True).to_string(), "\n")
    print("Penalidades:", df.penalidades.str.split(";").explode().replace("", pd.NA).dropna().value_counts().to_dict())
    print("Evidências nas candidatas:",
          {c: int(df.loc[df.decisao_previa == "candidata", c].sum()) for c in ["ev_lei", "ev_assunto", "ev_busca"]})
    disc = q.set_index("id").disciplina.replace("", "(fora/sem)")
    print("\nNível por disciplina:")
    print(pd.crosstab(df.id.map(disc), df.nivel.replace("", "(fora)")).to_string())


if __name__ == "__main__":
    main()
