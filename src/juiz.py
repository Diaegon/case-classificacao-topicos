"""
Etapa 3: juiz LLM. Uma chamada independente por questão e por variante (nunca várias questões
na mesma conversa, para um voto não contaminar o outro).

Variantes:
    a         llm_model_a, árvore tratada + sugestões (busca e leis)
    b         llm_model_b, idem. Modelo de outra geração, para os erros serem menos correlacionados
    baseline  llm_model_a, árvore CRUA (temas.csv ativo, sem correções nem descrições) e sem sugestões.
              Só para o relatório: mede quanto o tratamento e os sinais ajudam.

O assunto de origem NÃO vai para o juiz (decisão do usuário): fica para a regra de decisão.

Prompt caching: o system prompt (instruções + árvore) é idêntico em todas as chamadas da mesma
variante, então a OpenAI cobra o prefixo como cached_input a partir da 2ª chamada. A 1ª chamada
roda sozinha para "aquecer" o cache antes das paralelas.

Entradas: data/interim/questoes_tratadas.csv, temas_classificacao.csv, sinais.csv, data/raw/temas.csv
Prompts:  prompts/juiz_system.md, juiz_user.md, juiz_sugestoes.md, juiz_correcao.md
Saída:    data/interim/votos_llm.csv (uma linha por questão e variante)

Uso:
    python -m src.juiz --estimar
    python -m src.juiz --variante a --limite 5     # piloto (grava votos_llm_piloto.csv)
    python -m src.juiz                              # as três variantes, 359 questões cada
"""

import argparse
import json
from string import Template

import pandas as pd

from src.cliente_api import Cliente
from src.config import SETTINGS, caminho

PROMPTS = caminho("prompts")
QUESTOES = caminho("interim") / "questoes_tratadas.csv"
TEMAS = caminho("interim") / "temas_classificacao.csv"
SINAIS = caminho("interim") / "sinais.csv"
TEMAS_CRUS = caminho("raw") / "temas.csv"
SAIDA = caminho("interim") / "votos_llm.csv"

VARIANTES = {
    "a": {"modelo": "llm_model_a", "arvore": "tratada", "sugestoes": True},
    "b": {"modelo": "llm_model_b", "arvore": "tratada", "sugestoes": True},
    "baseline": {"modelo": "llm_model_a", "arvore": "crua", "sugestoes": False},
}

# justificativa vem primeiro: com saída estruturada a ordem dos campos é a ordem de geração,
# e o modelo escreve o que a questão cobra antes de escolher o id.
SCHEMA = {
    "type": "object",
    "properties": {
        "justificativa": {"type": "string"},
        "tema_central_id": {"type": "string"},
        "segunda_opcao_id": {"type": "string"},
        "extras_ids": {"type": "array", "items": {"type": "string"}},
        "nenhum_serve": {"type": "boolean"},
    },
    "required": ["justificativa", "tema_central_id", "segunda_opcao_id", "extras_ids", "nenhum_serve"],
    "additionalProperties": False,
}


def ler(nome):
    return pd.read_csv(nome, dtype=str, keep_default_na=False)


def template(nome: str) -> Template:
    return Template((PROMPTS / nome).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- árvore no system prompt

def arvore_tratada(t: pd.DataFrame) -> tuple[str, set[str]]:
    """Só publicáveis, na ordem da árvore (o caminho ordena pai antes dos filhos)."""
    pub = t[t.publicavel == "True"].sort_values("caminho")
    linhas = []
    for r in pub.itertuples():
        marcas = (" [GENÉRICO]" if r.generico == "True" else "") + \
                 "".join(f" ≈ {s}" for s in r.sobrepoe_ids.split(";") if s)
        linhas.append(f"{r.tema_id} | {r.caminho}{marcas} — {r.texto_prompt}")
    return "\n".join(linhas), set(pub.tema_id)


def arvore_crua() -> tuple[str, set[str]]:
    """temas.csv como veio (só sem os inativos, que o enunciado do case manda não usar)."""
    raw = ler(TEMAS_CRUS)
    ativos = raw[raw.status != "inactive"].sort_values("caminho")
    linhas = [f"{r.tema_id} | {r.caminho} — {r.descricao}" for r in ativos.itertuples()]
    return "\n".join(linhas), set(ativos.tema_id)


# ---------------------------------------------------------------- mensagem da questão

def bloco_sugestoes(s, temas: dict) -> str:
    cand = []
    for i, tid in enumerate(s.busca_top_ids.split(";"), 1):
        t = temas[tid]
        fronteira = f"\n   Não confundir: {t.nao_entra}" if t.nao_entra else ""
        cand.append(f"{i}. {tid} | {t.caminho} — {t.texto_prompt}{fronteira}")
    pais = ", ".join(f"{p} {temas[p].titulo}" for p in s.busca_pais_ids.split(";") if p) or "(nenhum)"
    leis = [f"- {l['lei']} → tema {', '.join(l['temas'])} (no(s) {l['onde']}, {l['n']}x)"
            for l in (json.loads(s.lei_json) if s.lei_json else [])]
    return template("juiz_sugestoes.md").substitute(
        candidatos="\n".join(cand), pais=pais, leis="\n".join(leis) or "- nenhuma lei com tema próprio")


def mensagens(system: str, q, s, temas: dict, com_sugestoes: bool) -> list[dict]:
    sug = bloco_sugestoes(s, temas) if com_sugestoes else ""
    user = template("juiz_user.md").substitute(questao=q.texto_completo, sugestoes=sug).strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---------------------------------------------------------------- validação

def validar(resp: dict, validos: set[str]) -> tuple[dict, list[str]]:
    """Limpa ids inválidos dos campos secundários. Central inválido é tratado por quem chama."""
    probs = []
    seg = resp["segunda_opcao_id"].strip()
    if seg and (seg not in validos or seg == resp["tema_central_id"]):
        probs.append(f"segunda_opcao inválida: {seg}")
        seg = ""
    extras = []
    for e in resp["extras_ids"]:
        e = e.strip()
        if e in validos and e != resp["tema_central_id"] and e not in extras:
            extras.append(e)
        elif e:
            probs.append(f"extra descartado: {e}")
    return {**resp, "tema_central_id": resp["tema_central_id"].strip(), "segunda_opcao_id": seg,
            "extras_ids": extras[:3]}, probs


def votar(cli: Cliente, modelo: str, msgs: list[dict], validos: set[str]) -> dict:
    """Uma chamada; se o central for inválido, uma nova tentativa com a correção na conversa."""
    resp = cli.chat(modelo, msgs, schema=SCHEMA)
    tentativas, probs = 1, []
    central = resp["tema_central_id"].strip()
    if not resp["nenhum_serve"] and central not in validos:
        probs.append(f"central inválido na 1ª tentativa: {central!r}")
        correcao = template("juiz_correcao.md").substitute(id_invalido=central)
        msgs = msgs + [{"role": "assistant", "content": str(resp)}, {"role": "user", "content": correcao}]
        resp = cli.chat(modelo, msgs, schema=SCHEMA)
        tentativas = 2
    resp, p = validar(resp, validos)
    probs += p
    valido = resp["nenhum_serve"] or resp["tema_central_id"] in validos
    if resp["nenhum_serve"] and resp["tema_central_id"] not in validos:
        resp["tema_central_id"] = ""
    return {**resp, "valido": valido, "tentativas": tentativas, "problemas": "; ".join(probs)}


# ---------------------------------------------------------------- execução

def preparar(variante: str):
    cfg = VARIANTES[variante]
    t = ler(TEMAS)
    arvore, validos = arvore_tratada(t) if cfg["arvore"] == "tratada" else arvore_crua()
    system = template("juiz_system.md").substitute(arvore=arvore)
    return SETTINGS["modelos"][cfg["modelo"]], system, validos, cfg["sugestoes"], {r.tema_id: r for r in t.itertuples()}


def estimar(q: pd.DataFrame, s: pd.DataFrame) -> None:
    saida_tok = 400  # justificativa + ids; medido no piloto (inclui raciocínio, se houver)
    total = 0
    for v in VARIANTES:
        modelo, system, _, sug, temas = preparar(v)
        p = SETTINGS["precos"][modelo]
        sys_tok = len(system) / 3.5
        user_tok = sum(len(mensagens("", qq, ss, temas, sug)[1]["content"]) for qq, ss in
                       zip(q.itertuples(), s.itertuples())) / 3.5
        n = len(q)
        custo = (sys_tok * p["input"] + (n - 1) * sys_tok * p["cached_input"]
                 + user_tok * p["input"] + n * saida_tok * p["output"]) / 1e6
        total += custo
        print(f"{v:9} {modelo:13} system {sys_tok:,.0f} tok | user médio {user_tok / n:,.0f} tok | US$ {custo:.2f}")
    print(f"total estimado: US$ {total:.2f} (saída suposta {saida_tok} tok/chamada)")


def rodar(variante: str, q: pd.DataFrame, s: pd.DataFrame) -> list[dict]:
    modelo, system, validos, sug, temas = preparar(variante)
    cli = Cliente(etapa=f"etapa3_juiz_{variante}")
    itens = list(zip(q.itertuples(), s.itertuples()))

    def um(par):
        qq, ss = par
        voto = votar(cli, modelo, mensagens(system, qq, ss, temas, sug), validos)
        return {"id": qq.id, "variante": variante, "modelo": modelo, **voto,
                "extras_ids": ";".join(voto["extras_ids"])}

    # 1ª sozinha: aquece o cache do prefixo antes das paralelas.
    votos = [um(itens[0])] + cli.mapear(um, itens[1:], concorrencia=SETTINGS["api"]["max_concorrencia_juiz"])
    reg = cli.salvar_custos()
    inval = sum(not v["valido"] for v in votos)
    nenhum = sum(v["nenhum_serve"] for v in votos)
    cache_frac = reg["tokens_cached"] / reg["tokens_input"] if reg["tokens_input"] else 0
    print(f"{variante}: {len(votos)} votos | inválidos {inval} | nenhum_serve {nenhum} | "
          f"US$ {reg['custo_usd']:.4f} agora, {reg['custo_total_usd']:.4f} reprodução | "
          f"cache {cache_frac:.0%} da entrada | saída média {reg['tokens_output'] / max(reg['chamadas_api'], 1):.0f} tok")
    return votos


def resumo() -> None:
    """Concordância entre variantes e com os sinais. Sem gabarito: isto NÃO é precisão."""
    v = ler(SAIDA)
    t = ler(TEMAS)
    s = ler(SINAIS).set_index("id")
    pai = dict(zip(t.tema_id, t.parent_id))
    filhos = {}
    for f, p in pai.items():
        filhos.setdefault(p, set()).add(f)
    ramo = lambda x: ({x, pai.get(x, "")} | filhos.get(x, set())) if x else set()
    generico = set(t.tema_id[t.generico == "True"])
    titulo = dict(zip(t.tema_id, t.titulo))
    w = v.pivot(index="id", columns="variante", values="tema_central_id")
    n = len(w)

    def par(x, y):
        exato = (w[x] == w[y]) & (w[x] != "")
        mesmo_ramo = pd.Series([bool(a) and b in ramo(a) for a, b in zip(w[x], w[y])], index=w.index)
        return f"exato {exato.sum()} ({exato.mean():.0%}) | ramo {mesmo_ramo.sum()} ({mesmo_ramo.mean():.0%})"

    print(f"\nConcordância entre variantes ({n} questões)")
    print(f"  A × B:         {par('a', 'b')}")
    print(f"  A × baseline:  {par('a', 'baseline')}")
    print(f"  B × baseline:  {par('b', 'baseline')}")
    for var in VARIANTES:
        x = v[v.variante == var]
        top1 = x.id.map(s.busca_top_ids.str.split(";").str[0])
        top10 = x.id.map(s.busca_top_ids.str.split(";"))
        fora_busca = sum(bool(c) and not (ramo(c) & set(tt)) for c, tt in zip(x.tema_central_id, top10))
        print(f"\n{var}: nenhum_serve {(x.nenhum_serve == 'True').sum()} | inválidos {(x.valido != 'True').sum()} | "
              f"2ª tentativa {(x.tentativas == '2').sum()} | genérico como central {x.tema_central_id.isin(generico).sum()} | "
              f"= top-1 da busca {(x.tema_central_id == top1).sum()} | fora do top-10 (nem ramo) {fora_busca}")
        mais = x.tema_central_id.value_counts().head(5)
        print("   mais escolhidos: " + "; ".join(f"{k} {titulo.get(k, '(cru)')[:28]} ({c})" for k, c in mais.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variante", choices=[*VARIANTES, "todas"], default="todas")
    ap.add_argument("--limite", type=int, help="só as N primeiras questões (piloto)")
    ap.add_argument("--estimar", action="store_true")
    ap.add_argument("--resumo", action="store_true", help="só imprime o resumo de votos_llm.csv")
    args = ap.parse_args()
    if args.resumo:
        resumo()
        return

    q, s = ler(QUESTOES), ler(SINAIS)
    assert list(q.id) == list(s.id), "questões e sinais fora de ordem"
    if args.estimar:
        estimar(q, s)
        return
    if args.limite:
        q, s = q.head(args.limite), s.head(args.limite)
    variantes = list(VARIANTES) if args.variante == "todas" else [args.variante]
    votos = [v for var in variantes for v in rodar(var, q, s)]
    destino = SAIDA if not args.limite and args.variante == "todas" else SAIDA.with_name("votos_llm_piloto.csv")
    pd.DataFrame(votos).to_csv(destino, index=False, encoding="utf-8")
    print(f"→ {destino}")
    if destino == SAIDA:
        resumo()


if __name__ == "__main__":
    main()
