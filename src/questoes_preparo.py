"""
Etapa 1a: preparo das questões.

Entrada: data/raw/questoes.jsonl            (359 questões, intocado)
         config/disciplinas_origem.yaml     (mapa de disciplina de origem)
Saída:   data/interim/questoes_tratadas.csv

Como na árvore, a saída é uma tabela nova só com dados tratados e com o que a classificação usa.
O campo `comando` é descartado: parece gerado automaticamente ("Complete a frase...") e não diz
nada sobre o conteúdo.

O texto de trabalho é sempre enunciado + alternativas (`texto_completo`), porque há enunciados
quase vazios ("A prisão preventiva", "Assinale a alternativa correta.") cujo conteúdo está todo
nas alternativas. Em certo/errado as alternativas são só "Certo"/"Errado" e ficam de fora.

Flags (nenhuma decide sozinha; a decisão é da etapa 4):
    enunciado_vazio          o enunciado é só uma instrução ("Assinale a alternativa correta.")
    enunciado_curto          até 5 palavras (o tema pode estar no enunciado, mas o resto está nas alternativas)
    ocr_suspeito             palavras que não existem em português (sequência de 5 consoantes, letra triplicada)
    disciplina_fora_recorte  disciplina de origem fora das 4 da árvore
    sem_disciplina           disciplina de origem vazia

Uso:
    python -m src.questoes_preparo
"""

import html
import json
import re
import sys

import pandas as pd
import yaml

from src.config import RAIZ, caminho

ENTRADA = caminho("raw") / "questoes.jsonl"
SAIDA = caminho("interim") / "questoes_tratadas.csv"
DISCIPLINAS = RAIZ / "config" / "disciplinas_origem.yaml"
CAMPOS = ["id", "enunciado_html", "comando", "alternativas", "disciplina_origem", "assunto_origem"]

# ---------------------------------------------------------------- limpeza de HTML

# Lixo do Word colado no banco (Q0099): comentários condicionais com <xml> e <style> dentro.
# O conteúdo desses blocos não é texto; precisa sair inteiro, não só as tags.
BLOCOS_LIXO = re.compile(r"<!--.*?-->|<(style|xml|script)\b.*?</\1\s*>", re.S | re.I)
QUEBRA = re.compile(r"<\s*br\s*/?\s*>|</\s*(p|div|li)\s*>", re.I)
TAG = re.compile(r"<[^>]+>")


def limpar_html(s: str) -> str:
    """HTML cru → texto. Mantém as quebras de linha, para as assertivas I, II, III não se fundirem."""
    s = BLOCOS_LIXO.sub(" ", s)
    s = re.sub(r"<sup>\s*[oº°]\s*</sup>", "º", s, flags=re.I)  # "Lei n. <sup>o</sup> 10.826" → "n.º"
    s = s.replace("\\n", " ")       # "\n" literal (barra + n) no meio de frases das alternativas
    s = re.sub(r"[\r\n\t]+", " ", s)  # quebras reais no HTML não são quebras de texto; <br> é
    s = QUEBRA.sub("\n", s)
    s = html.unescape(TAG.sub(" ", s)).replace("\xa0", " ")
    linhas = [re.sub(r"\s{2,}", " ", l).strip() for l in s.split("\n")]
    linhas = [re.sub(r"\s+([,.;:!?)])", r"\1", l) for l in linhas if l]
    return "\n".join(linhas)


# ---------------------------------------------------------------- flags

INSTRUCAO = re.compile(
    r"^(assinale|marque|analise|indique|julgue|escolha)\b.*\b(alternativa|op[cç][aã]o|afirmativa|assertiva|item)s?\b"
    r"(\s+(in)?corretas?|\s+verdadeiras?|\s+falsas?)?\s*[:.]?$", re.I)
# Palavra impossível em português: 5 consoantes seguidas ou a mesma letra 3 vezes ("oossstomnio").
# Números romanos (XVIII, LXIII) são ignorados.
PALAVRA_RUIM = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}|([a-z])\1\1", re.I)
ROMANO = re.compile(r"^[IVXLCDM]+$")


def palavras_suspeitas(texto: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", texto)
            if not ROMANO.match(w) and PALAVRA_RUIM.search(w)]


# ---------------------------------------------------------------- leitura

def ler_entrada() -> list[dict]:
    """Lê linha a linha para apontar exatamente qual linha estiver quebrada."""
    questoes = []
    with open(ENTRADA, encoding="utf-8") as f:
        for n, linha in enumerate(f, 1):
            if not linha.strip():
                continue
            try:
                q = json.loads(linha)
            except json.JSONDecodeError as e:
                sys.exit(f"{ENTRADA.name}, linha {n}: JSON inválido ({e.msg}, coluna {e.colno}).")
            faltam = set(CAMPOS) - set(q)
            if faltam:
                sys.exit(f"{ENTRADA.name}, linha {n}: faltam os campos {sorted(faltam)}.")
            questoes.append(q)
    return questoes


def normalizar_disciplina(origem: str, mapa: dict) -> tuple[str, bool, bool]:
    """→ (disciplina, fora_recorte, sem_disciplina). Disciplina desconhecida faz o preparo falhar."""
    origem = origem.strip()
    if not origem:
        return "", False, True
    if origem in mapa["recorte"]:
        return mapa["recorte"][origem], False, False
    if origem in mapa["fora_recorte"]:
        return "", True, False
    sys.exit(f"Disciplina de origem desconhecida: '{origem}'. Inclua em {DISCIPLINAS.name}.")


# ---------------------------------------------------------------- tratamento

def tratar(questoes: list[dict], mapa: dict) -> pd.DataFrame:
    linhas = []
    for q in questoes:
        enunciado = limpar_html(q["enunciado_html"])
        alts = {k: limpar_html(v) for k, v in q["alternativas"].items()}
        certo_errado = sorted(alts.values()) == ["Certo", "Errado"]
        alts_txt = "" if certo_errado else "\n".join(f"{k}) {v}" for k, v in alts.items())
        texto = "\n".join(p for p in [enunciado, alts_txt] if p)
        disciplina, fora, sem = normalizar_disciplina(q["disciplina_origem"], mapa)
        suspeitas = palavras_suspeitas(texto)
        linhas.append({
            "id": q["id"],
            "enunciado": enunciado,
            "alternativas": alts_txt,
            "texto_completo": texto,
            "tipo": "certo_errado" if certo_errado else "multipla_escolha",
            "n_alternativas": len(alts),
            "disciplina": disciplina,
            "assunto_origem": re.sub(r"\s+", " ", q["assunto_origem"]).strip(),
            "enunciado_vazio": bool(INSTRUCAO.match(enunciado)) or not enunciado,
            "enunciado_curto": len(enunciado.split()) <= 5,
            "ocr_suspeito": bool(suspeitas),
            "ocr_palavras": ";".join(suspeitas),
            "disciplina_fora_recorte": fora,
            "sem_disciplina": sem,
            "n_palavras": len(texto.split()),
        })
    return pd.DataFrame(linhas)


def validar(df: pd.DataFrame, n_entrada: int) -> list[str]:
    erros = []
    if len(df) != n_entrada:
        erros.append(f"{len(df)} linhas na saída, {n_entrada} na entrada")
    if df.id.duplicated().any():
        erros.append(f"ids repetidos: {df.id[df.id.duplicated()].tolist()}")
    if (df.texto_completo == "").any():
        erros.append(f"sem texto: {df.id[df.texto_completo == ''].tolist()}")
    resto = df.texto_completo.str.contains(r"<[a-zA-Z/!]|&[a-z]+;|mso-", regex=True)
    if resto.any():
        erros.append(f"sobrou HTML: {df.id[resto].tolist()}")
    if (df.tipo == "multipla_escolha").sum() and (df.n_alternativas[df.tipo == "multipla_escolha"] < 4).any():
        erros.append("múltipla escolha com menos de 4 alternativas")
    return erros


def main() -> None:
    questoes = ler_entrada()
    mapa = yaml.safe_load(DISCIPLINAS.read_text(encoding="utf-8"))
    df = tratar(questoes, mapa)
    erros = validar(df, len(questoes))
    if erros:
        sys.exit("Validação falhou:\n  " + "\n  ".join(erros))
    df.to_csv(SAIDA, index=False, encoding="utf-8")

    print(f"{len(df)} questões → {SAIDA}")
    print(df.tipo.value_counts().to_string(), "\n")
    print((df.disciplina.replace("", "(vazia / fora)")).value_counts().to_string(), "\n")
    for f in ["enunciado_vazio", "enunciado_curto", "ocr_suspeito", "disciplina_fora_recorte", "sem_disciplina"]:
        ids = df.id[df[f]].tolist()
        print(f"{f}: {len(ids)}  {ids if len(ids) <= 12 else ids[:12] + ['...']}")
    print(f"\npalavras por questão: mediana {df.n_palavras.median():.0f}, "
          f"mín {df.n_palavras.min()}, máx {df.n_palavras.max()}")


if __name__ == "__main__":
    main()
