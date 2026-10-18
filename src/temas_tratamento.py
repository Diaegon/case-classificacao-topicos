"""
Etapa 1b: tratamento da árvore de temas (determinístico, sem API).

Entrada (nunca modificada): data/raw/temas.csv
Configs revisadas à mão:    config/correcoes_grafia.yaml, duplicatas.yaml,
                            sobreposicoes.yaml, genericos.yaml
Saída:                      data/interim/temas_tratados.csv

A saída é uma tabela NOVA, só com dados tratados e com o que a classificação usa.
O texto cru (títulos com erro, descrições com contagens da classificação antiga) não
é copiado, para nenhum módulo posterior usá-lo por engano; a auditoria fica no
data/raw/temas.csv. As 377 linhas são mantidas (inclusive duplicatas e raízes),
porque a função de acerto precisa da árvore completa. A saída do pipeline sempre usa
o tema_id original.

Colunas:
    tema_id, parent_id, disciplina, nivel   estrutura, idêntica ao original
    titulo, caminho                         com a grafia corrigida
    descricao_oficial                       só as 20 descrições reais; vazio nas demais
    publicavel, motivo_nao_publicavel       inativo, raiz (nível 0) ou duplicata
    canonico_id                             o próprio id, ou o original se for duplicata
    generico, motivo_generico               candidatos a lixeira (antilixeira na decisão)
    sobrepoe_ids                            temas legítimos que cobrem o mesmo assunto (;)
    filhos_ids, irmaos_ids                  vizinhança entre publicáveis (;)

Uso:
    python -m src.temas_tratamento --propor-duplicatas   # gera config/duplicatas.yaml (não sobrescreve)
    python -m src.temas_tratamento                       # gera temas_tratados.csv e valida
"""

import argparse
import re
import sys
import unicodedata

import pandas as pd
import yaml
from rapidfuzz import fuzz

from src.config import RAIZ, SETTINGS, caminho

ENTRADA = caminho("raw") / "temas.csv"
SAIDA = caminho("interim") / "temas_tratados.csv"
CFG = RAIZ / "config"

COLUNAS_RAW = ["tema_id", "parent_id", "disciplina", "nivel", "titulo", "caminho", "descricao", "status"]
COLUNAS_ESTRUTURA = ["tema_id", "parent_id", "disciplina", "nivel"]
COLUNAS_SAIDA = COLUNAS_ESTRUTURA + [
    "titulo", "caminho", "descricao_oficial", "publicavel", "motivo_nao_publicavel", "canonico_id",
    "generico", "motivo_generico", "sobrepoe_ids", "filhos_ids", "irmaos_ids"]

# As descrições que não são reais seguem só dois moldes, ambos com a contagem
# "N questões" da classificação antiga. Essa contagem não pode virar prior, então
# o texto inteiro é descartado.
MOLDES_PADRAO = [
    re.compile(r"^Subtema de '.*' \(.*\)\. \d+ questões no source\. Path: .*\.$"),
    re.compile(r"^Disciplina \(root\)\. \d+ questões\. Inclui \d+ temas/topics\.$"),
]
# Qualquer letra fora do alfabeto latino (árabe, cirílico, CJK...) é ruído nesta árvore.
NAO_LATINO = re.compile(r"[^\u0000-ɏḀ-ỿ -⁯]")
PARTE_N = re.compile(r"\(\s*parte\s*\d+\s*\)", re.I)


def ler_yaml(nome: str) -> dict:
    with open(CFG / nome, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dobrar(s: str) -> str:
    """Minúsculas, sem acento, sem pontuação: só para comparar títulos."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def ler_entrada() -> pd.DataFrame:
    # keep_default_na=False: parent_id vazio continua "" (e não NaN), igual ao arquivo.
    df = pd.read_csv(ENTRADA, dtype=str, keep_default_na=False)
    if list(df.columns) != COLUNAS_RAW:
        sys.exit(f"Colunas inesperadas em {ENTRADA}: {list(df.columns)}")
    return df


# ---------------------------------------------------------------- passos 1 e 2: texto

def descricao_real(d: str) -> str:
    """A descrição só é mantida se não for vazia nem um dos moldes com contagem."""
    d = d.strip()
    return "" if not d or any(m.match(d) for m in MOLDES_PADRAO) else d


def aplicar_correcoes(df: pd.DataFrame, correcoes: list[dict], col: str) -> list[str]:
    """Substitui trechos exatos por tema_id. Falha se o trecho não existir (nada é ignorado em silêncio)."""
    log = []
    for c in correcoes:
        idx = df.index[df.tema_id == str(c["tema_id"])]
        if len(idx) != 1:
            sys.exit(f"Correção para tema_id inexistente: {c}")
        i = idx[0]
        if c["de"] not in df.at[i, col]:
            sys.exit(f"Trecho '{c['de']}' não encontrado em {col} de {c['tema_id']}: {df.at[i, col]!r}")
        df.at[i, col] = df.at[i, col].replace(c["de"], c["para"])
        log.append(f"{c['tema_id']}: {col} '{c['de']}' → '{c['para']}'")
    return log


def montar_caminho(df: pd.DataFrame) -> pd.Series:
    """Recalcula o caminho a partir dos títulos corrigidos, para a correção do pai valer nos filhos."""
    titulo = dict(zip(df.tema_id, df.titulo))
    pai = dict(zip(df.tema_id, df.parent_id))

    def caminho_de(tid: str) -> str:
        partes = []
        while tid:
            partes.append(titulo[tid])
            tid = pai[tid]
        return " > ".join(reversed(partes))

    return df.tema_id.map(caminho_de)


def tratar_texto(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Monta a tabela nova com estrutura + textos limpos. O df_raw não é alterado."""
    df = df_raw[COLUNAS_ESTRUTURA].copy()
    df["titulo"] = df_raw.titulo.str.strip()
    df["descricao_oficial"] = df_raw.descricao.map(descricao_real)

    corr = ler_yaml("correcoes_grafia.yaml")
    log = aplicar_correcoes(df, corr.get("titulos", []), "titulo")
    log += aplicar_correcoes(df, corr.get("descricoes", []), "descricao_oficial")
    for col in ["titulo", "descricao_oficial"]:
        df[col] = df[col].str.replace(r"\s+", " ", regex=True).str.strip()
    df["caminho"] = montar_caminho(df)
    return df, log


# ---------------------------------------------------------------- passo 3: duplicatas

def nos_vazios(df: pd.DataFrame, df_raw: pd.DataFrame) -> pd.Series:
    """
    Nó sem conteúdo próprio: descrição vazia JÁ NO ORIGINAL e sem filhos (todos os 67xx).
    Olha o df_raw porque, na tabela tratada, as descrições padrão também viram vazio.
    """
    vazia = df.tema_id.map(dict(zip(df_raw.tema_id, df_raw.descricao.str.strip() == "")))
    return vazia & ~df.tema_id.isin(set(df.parent_id))


def propor_duplicatas(df: pd.DataFrame, df_raw: pd.DataFrame) -> None:
    """
    Para cada nó vazio, procura o tema com título mais parecido (ignorando "(Parte N)",
    acentos e caixa). Nó vazio + título quase igual = duplicata. Se os dois nós têm
    conteúdo, não é duplicata: é sobreposição (ver listar_sobreposicoes_candidatas).
    """
    destino = CFG / "duplicatas.yaml"
    if destino.exists():
        sys.exit(f"{destino} já existe (pode ter revisões suas). Apague-o para propor de novo.")

    ativos = df.tema_id.map(dict(zip(df_raw.tema_id, df_raw.status == "active")))
    vazio = nos_vazios(df, df_raw)
    alvos = df[ativos & (df.nivel != "0") & ~vazio]
    linhas = ["# id_duplicado → id_canônico. Proposto por similaridade de título (rapidfuzz.ratio,",
              "# sem acento/caixa/\"(Parte N)\"). Regra: o canônico é o nó original (id antigo, com",
              "# descrição ou filhos). Duplicatas ficam publicavel=False.",
              "# Revisado por: (pendente)", "", "duplicatas:"]
    for _, r in df[vazio & ativos].iterrows():
        chave = dobrar(PARTE_N.sub(" ", r.titulo))
        notas = sorted(((fuzz.ratio(chave, dobrar(a.titulo)), a.tema_id, a.caminho)
                        for _, a in alvos.iterrows()), reverse=True)
        (s1, id1, cam1), (s2, id2, _) = notas[0], notas[1]
        aviso = "  # REVISAR: score baixo" if s1 < 85 else ""
        linhas.append(f"  {r.tema_id}: {id1}   # {r.caminho} → {cam1} (score {s1:.0f};"
                      f" 2º: {id2} {s2:.0f}){aviso}")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Proposta gravada em {destino}. Revise antes de rodar o tratamento.")


def listar_sobreposicoes_candidatas(df: pd.DataFrame, conhecidas: set[frozenset]) -> list[str]:
    """Pares de publicáveis com títulos parecidos e sem relação pai/filho. Só para revisão humana."""
    pub = df[df.publicavel].reset_index(drop=True)
    pai = dict(zip(df.tema_id, df.parent_id))
    saida = []
    for i in range(len(pub)):
        for j in range(i + 1, len(pub)):
            a, b = pub.iloc[i], pub.iloc[j]
            if pai[a.tema_id] == b.tema_id or pai[b.tema_id] == a.tema_id:
                continue
            ta, tb = dobrar(a.titulo), dobrar(b.titulo)
            s = fuzz.ratio(ta, tb)
            contido = len(ta) > 6 and len(tb) > 6 and (ta in tb or tb in ta)
            if s >= 85 or contido:
                ja = any({a.tema_id, b.tema_id} <= g for g in conhecidas)
                saida.append(f"{'  ' if ja else '* '}{a.tema_id} {a.caminho}  ×  {b.tema_id} {b.caminho}"
                             f"  (score {s:.0f}{', contido' if contido else ''})")
    return saida


# ---------------------------------------------------------------- tratamento completo

def tratar(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df, log = tratar_texto(df_raw)

    # Passo 3: publicável e duplicatas.
    dups = {str(k): str(v) for k, v in (ler_yaml("duplicatas.yaml").get("duplicatas") or {}).items()}
    df["canonico_id"] = df.tema_id.map(lambda t: dups.get(t, t))
    status = dict(zip(df_raw.tema_id, df_raw.status))
    motivos = []
    for _, r in df.iterrows():
        if status[r.tema_id] != "active":
            motivos.append("inativo")
        elif r.nivel == "0" and not SETTINGS["suposicoes"]["nivel0_publicavel"]:
            motivos.append("raiz de disciplina (nível 0)")
        elif r.tema_id in dups:
            motivos.append(f"duplicata de {dups[r.tema_id]}")
        else:
            motivos.append("")
    df["motivo_nao_publicavel"] = motivos
    df["publicavel"] = df.motivo_nao_publicavel == ""

    # Passo 4: sobreposições (os dois lados seguem publicáveis; só anotamos).
    grupos = [set(map(str, g["ids"])) for g in ler_yaml("sobreposicoes.yaml").get("grupos", [])]
    df["sobrepoe_ids"] = df.tema_id.map(
        lambda t: ";".join(sorted(set().union(*[g - {t} for g in grupos if t in g]))) if grupos else "")

    # Passo 5: genéricos.
    gen = ler_yaml("genericos.yaml")
    padroes = [re.compile(p, re.I) for p in gen.get("padroes", [])]
    lixeiras = {str(k) for k in (gen.get("lixeiras_conhecidas") or {})}
    excecoes = {str(k) for k in (gen.get("excecoes") or {})}

    def motivo_generico(r) -> str:
        if not r.publicavel or r.tema_id in excecoes:
            return ""
        if r.tema_id in lixeiras:
            return "lixeira conhecida"
        achados = [p.pattern for p in padroes if p.search(r.titulo)]
        return f"título genérico ({', '.join(achados)})" if achados else ""

    df["motivo_generico"] = df.apply(motivo_generico, axis=1)
    df["generico"] = df.motivo_generico != ""

    # Vizinhança (só publicáveis): usada nos prompts de descrição e na regra de decisão.
    filhos = df.groupby("parent_id").tema_id.apply(list).to_dict()
    pub = set(df.tema_id[df.publicavel])
    df["filhos_ids"] = df.tema_id.map(lambda t: ";".join(f for f in filhos.get(t, []) if f in pub))
    df["irmaos_ids"] = df.apply(
        lambda r: ";".join(f for f in filhos.get(r.parent_id, []) if f in pub and f != r.tema_id), axis=1)

    return df[COLUNAS_SAIDA], log


# ---------------------------------------------------------------- passo 8: validação

def validar(df: pd.DataFrame, df_raw: pd.DataFrame) -> list[str]:
    erros = []
    if list(df.columns) != COLUNAS_SAIDA:
        erros.append(f"colunas inesperadas: {list(df.columns)}")
    if not df[COLUNAS_ESTRUTURA].reset_index(drop=True).equals(df_raw[COLUNAS_ESTRUTURA]):
        erros.append("a estrutura (tema_id, parent_id, disciplina, nivel) difere do original")
    if df.tema_id.duplicated().any():
        erros.append("tema_id duplicado")
    ids = set(df.tema_id)
    if not set(df.parent_id[df.parent_id != ""]) <= ids:
        erros.append("parent_id inexistente")

    for col in ["titulo", "caminho", "descricao_oficial"]:
        if df[col].str.contains("questões no source|questões\\. Inclui", regex=True).any():
            erros.append(f"{col}: sobrou texto padrão com contagem")
        sujos = df.tema_id[df[col].map(lambda s: bool(NAO_LATINO.search(s)))]
        if len(sujos):
            erros.append(f"{col}: caractere não latino em {list(sujos)}")

    status = dict(zip(df_raw.tema_id, df_raw.status))
    pub = set(df.tema_id[df.publicavel])
    for t in pub:
        if status[t] != "active" or df.loc[df.tema_id == t, "nivel"].item() == "0":
            erros.append(f"{t}: publicável mas inativo ou nível 0")
    for _, r in df[df.canonico_id != df.tema_id].iterrows():
        if r.canonico_id not in pub:
            erros.append(f"duplicata {r.tema_id} aponta para {r.canonico_id}, que não é publicável")
    for t in set(";".join(df.sobrepoe_ids).split(";")) - {""}:
        if t not in pub:
            erros.append(f"sobreposição cita {t}, que não é publicável")
    gen = ler_yaml("genericos.yaml")
    for chave in ["lixeiras_conhecidas", "excecoes"]:
        for t in map(str, gen.get(chave) or {}):
            if t not in pub:
                erros.append(f"genericos.yaml/{chave} cita {t}, que não é publicável")
    vazios_pub = df.tema_id[nos_vazios(df, df_raw) & df.publicavel]
    if len(vazios_pub):
        erros.append(f"nós vazios (sem descrição e sem filhos) ainda publicáveis: {list(vazios_pub)}")
    return erros


def resumo(df: pd.DataFrame, log: list[str]) -> None:
    print(f"{len(df)} temas | publicáveis: {df.publicavel.sum()} | genéricos: {df.generico.sum()}"
          f" | com sobreposição: {(df.sobrepoe_ids != '').sum()}"
          f" | com descrição oficial: {(df.descricao_oficial != '').sum()}")
    print("\nNão publicáveis:", df.motivo_nao_publicavel[~df.publicavel]
          .str.replace(r"\d+", "N", regex=True).value_counts().to_dict())
    print("\nPublicáveis por disciplina e nível:")
    print(df[df.publicavel].groupby(["disciplina", "nivel"]).size().to_string())
    print("\nCorreções aplicadas:"); print("\n".join("  " + linha for linha in log))
    print("\nGenéricos:")
    for _, r in df[df.generico].iterrows():
        print(f"  {r.tema_id} {r.caminho}  [{r.motivo_generico}]")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--propor-duplicatas", action="store_true")
    args = p.parse_args()

    df_raw = ler_entrada()
    if args.propor_duplicatas:
        # Para propor, basta o texto tratado; duplicatas.yaml ainda não existe.
        df, _ = tratar_texto(df_raw)
        propor_duplicatas(df, df_raw)
        return

    if not (CFG / "duplicatas.yaml").exists():
        sys.exit("config/duplicatas.yaml não existe. Rode com --propor-duplicatas e revise.")
    df, log = tratar(df_raw)
    erros = validar(df, df_raw)
    if erros:
        sys.exit("Validação falhou:\n  " + "\n  ".join(erros))

    df.to_csv(SAIDA, index=False, encoding="utf-8")
    resumo(df, log)

    grupos = [frozenset(map(str, g["ids"])) for g in ler_yaml("sobreposicoes.yaml").get("grupos", [])]
    cand = listar_sobreposicoes_candidatas(df, set(grupos))
    print(f"\nPares de títulos parecidos entre publicáveis ({len(cand)}; * = ainda fora de sobreposicoes.yaml)."
          " Revisados em 2026-10-17: os * restantes são falsos positivos de texto ou irmãos comuns.")
    print(f"\nValidação OK → {SAIDA}")


if __name__ == "__main__":
    main()
