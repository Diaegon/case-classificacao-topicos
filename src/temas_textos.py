"""
Etapa 1b, passo 7: tabela final de temas para a classificação.

Entradas: data/interim/temas_tratados.csv      (árvore tratada, determinística)
          data/interim/temas_descricoes.jsonl  (descrições da LLM, intocadas)
          config/descricoes_overrides.yaml     (correções manuais de conteúdo)
Saída:    data/interim/temas_classificacao.csv

A tabela final é a única que as etapas seguintes leem. Ela traz as colunas da árvore
tratada mais os campos enriquecidos e três textos derivados, um para cada consumidor:

    texto_embedding  caminho + "entra" + termos típicos. SEM fronteiras ("não entra"):
                     embedding não entende negação, e "não confundir com Roubo" puxaria
                     o vetor de Furto na direção de Roubo.
    texto_bm25       título + títulos dos ancestrais + termos típicos (curto e discriminativo).
    texto_prompt     descrição curta, para a lista de temas no system prompt do juiz.

Base legal fica FORA de todos os textos (decisão do usuário, 2026-10-17): a amostragem achou
artigos errados entre 814 citações, e revisar todas não compensa. As citações que a LLM
escreveu no meio do texto livre também são removidas. Citações de lei nas QUESTÕES são
tratadas pelas regras revisadas de config/regras_leis.yaml (etapa 2).

A descrição oficial (20 temas) não entra direto no embedding: ela já foi a fonte prioritária
do "entra" gerado pela LLM, e várias trazem frases negativas ("Não trata de inquérito...").

Uso:
    python -m src.temas_textos
"""

import json
import re
import sys

import pandas as pd
import yaml

from src.config import RAIZ, caminho

TRATADOS = caminho("interim") / "temas_tratados.csv"
DESCRICOES = caminho("interim") / "temas_descricoes.jsonl"
OVERRIDES = RAIZ / "config" / "descricoes_overrides.yaml"
SAIDA = caminho("interim") / "temas_classificacao.csv"

CAMPOS_EDITAVEIS = {"entra", "descricao_curta", "termos_tipicos", "nao_entra"}

# Citações numeradas. Artigo: removido junto com a preposição que o introduz
# ("a tipificação do art. 147-B do CP:" → "a tipificação:"). Lei numerada: vira só "lei",
# porque apagar quebra a frase ("sobre a Lei 12.850/2013 que" → "sobre a lei que").
# Nomes de lei sem número ("Lei Maria da Penha") ficam: são termos típicos legítimos.
_PREP = r"(?:\b(?:d[oa]s?|n[oa]s?|pel[oa]s?|em|ao|à)\s+)?"
LEI_NUM = re.compile(r"\b(Decreto-)?[Ll]ei\s+(?:n[º°.]*\s*)?\d{1,2}\.?\d{3}(?:/\d{2,4})?")
_NUM = r"\d+[º°]?(?:-[A-Z])?"
_ART = (rf"(?:§\s*{_NUM}\s+d[oa]\s+)?[Aa]rt(?:igo)?s?\.?\s*{_NUM}"
        rf"(?:\s*(?:,|e|a)\s*(?:§\s*)?{_NUM})*(?:\s*,?\s*§\s*{_NUM})*(?:\s*,\s*[IVXL]+\b)*"
        rf"(?:\s+d[oa]\s+(?:CPP|CP|CF|ECA|LEP|CTB|Código de Processo Penal|Código Penal|Constituição Federal)\b)?")
ARTIGO = re.compile(rf"\s*\(?\s*{_PREP}{_ART}\)?")
# Detector independente, mais largo, usado só para validar que nada sobrou.
SOBROU = re.compile(r"\bart(s|igo)?s?\.?\s*\d|\b\d{1,2}\.\d{3}/\d{2,4}|\blei\s+(n[º°o]\.?\s*)?\d", re.I)


def tirar_citacoes(s: str) -> str:
    s = ARTIGO.sub("", s)
    s = LEI_NUM.sub(lambda m: "decreto-lei" if m.group(1) else "lei", s)
    s = re.sub(r"\(\s*\)", "", s)                 # parênteses que ficaram vazios
    s = re.sub(r"\s+([,.;:])", r"\1", s)           # espaço antes de pontuação
    return re.sub(r"\s{2,}", " ", s).strip()


def carregar_descricoes() -> dict[str, dict]:
    desc = {}
    with open(DESCRICOES, encoding="utf-8") as f:
        for linha in f:
            x = json.loads(linha)
            desc[x["tema_id"]] = x
    overrides = yaml.safe_load(OVERRIDES.read_text(encoding="utf-8")) or {}
    for tid, campos in overrides.items():
        tid = str(tid)
        if tid not in desc:
            sys.exit(f"Override para tema sem descrição: {tid}")
        if set(campos) - CAMPOS_EDITAVEIS:
            sys.exit(f"Override de {tid} com campo não editável: {set(campos) - CAMPOS_EDITAVEIS}")
        desc[tid] = {**desc[tid], **campos, "override": sorted(campos)}
    return desc


def main() -> None:
    df = pd.read_csv(TRATADOS, dtype=str, keep_default_na=False)
    desc = carregar_descricoes()
    titulo = dict(zip(df.tema_id, df.titulo))
    pub = df.publicavel == "True"
    faltando = set(df.tema_id[pub]) - set(desc)
    if faltando:
        sys.exit(f"Temas publicáveis sem descrição: {sorted(faltando)}. Rode src.temas_descricoes.")

    linhas = []
    for _, r in df.iterrows():
        d = desc.get(r.tema_id) if r.publicavel == "True" else None
        if d is None:  # não publicável: fica na tabela (a função de acerto precisa), sem textos
            linhas.append({"entra": "", "nao_entra": "", "termos_tipicos": "", "descricao_curta": "",
                           "override": "", "texto_embedding": "", "texto_bm25": "", "texto_prompt": ""})
            continue
        entra = tirar_citacoes(d["entra"])
        curta = tirar_citacoes(d["descricao_curta"])
        # Termo que é uma citação ("art. 403, caput") sai inteiro; nos demais, só a citação.
        termos = [tirar_citacoes(t) for t in d["termos_tipicos"] if not SOBROU.search(t)]
        fronteiras = [f"{n['tema_id']}: {tirar_citacoes(n['fronteira'])}" for n in d["nao_entra"]]
        ancestrais = r.caminho.split(" > ")[1:-1]  # sem a disciplina e sem o próprio título
        linhas.append({
            "entra": entra,
            "nao_entra": " | ".join(fronteiras),
            "termos_tipicos": ";".join(termos),
            "descricao_curta": curta,
            "override": ";".join(d.get("override", [])),
            "texto_embedding": f"{r.caminho}. {entra} Termos: {', '.join(termos)}.",
            "texto_bm25": " ".join([titulo[r.tema_id], *ancestrais, *termos]),
            "texto_prompt": curta,
        })
    out = pd.concat([df, pd.DataFrame(linhas)], axis=1)

    # Validação: nenhum texto de classificação pode conter citação numerada.
    cols_texto = ["entra", "nao_entra", "termos_tipicos", "descricao_curta",
                  "texto_embedding", "texto_bm25", "texto_prompt"]
    sobras = [(r.tema_id, c, SOBROU.search(r[c]).group(0)) for _, r in out.iterrows()
              for c in cols_texto if SOBROU.search(r[c])]
    if sobras:
        sys.exit("Sobraram citações:\n  " + "\n  ".join(map(str, sobras)))
    vazios = out.tema_id[pub & (out.texto_embedding == "")]
    if len(vazios):
        sys.exit(f"Publicáveis sem texto: {list(vazios)}")

    out.to_csv(SAIDA, index=False, encoding="utf-8")
    n_cit = sum(len(ARTIGO.findall(d[c] if isinstance(d[c], str) else json.dumps(d[c], ensure_ascii=False)))
                + len(LEI_NUM.findall(d[c] if isinstance(d[c], str) else json.dumps(d[c], ensure_ascii=False)))
                for d in desc.values() for c in ["entra", "descricao_curta", "termos_tipicos", "nao_entra"])
    tok = lambda col: out.loc[pub, col].str.len().sum() / 3.5  # ~3,5 caracteres por token em português
    print(f"{len(out)} temas, {pub.sum()} com textos → {SAIDA}")
    print(f"Citações removidas do texto livre: {n_cit} | overrides aplicados: {(out.override != '').sum()}")
    print(f"Tokens estimados: embedding {tok('texto_embedding'):,.0f} | prompt do juiz {tok('texto_prompt'):,.0f}")


if __name__ == "__main__":
    main()
