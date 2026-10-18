"""
Etapa 1b, passo 6: descrições enriquecidas dos temas publicáveis (LLM, uma chamada por tema).

Entrada:  data/interim/temas_tratados.csv
Prompts:  prompts/descricao_tema_system.md, prompts/descricao_tema_user.md
Saída:    data/interim/temas_descricoes.jsonl     (resposta do modelo, validada; nunca editada à mão)

O campo base_legal é pedido ao modelo e guardado aqui, mas NÃO entra nos textos de classificação
(decisão do usuário, 2026-10-17): a amostragem achou artigos errados entre 814 citações. Ver
src/temas_textos.py. Correções de conteúdo vão para config/descricoes_overrides.yaml.

Uso:
    python -m src.temas_descricoes --estimar   # só estima tokens e custo, sem API
    python -m src.temas_descricoes             # chama a API (respostas em cache)
"""

import argparse
import json
from string import Template

import pandas as pd

from src.cliente_api import Cliente
from src.config import SETTINGS, caminho

ENTRADA = caminho("interim") / "temas_tratados.csv"
SAIDA = caminho("interim") / "temas_descricoes.jsonl"
PROMPTS = caminho("prompts")

SCHEMA = {
    "type": "object",
    "properties": {
        "entra": {"type": "string"},
        "nao_entra": {"type": "array", "items": {
            "type": "object",
            "properties": {"tema_id": {"type": "string"}, "fronteira": {"type": "string"}},
            "required": ["tema_id", "fronteira"], "additionalProperties": False}},
        "base_legal": {"type": "array", "items": {"type": "string"}},
        "termos_tipicos": {"type": "array", "items": {"type": "string"}},
        "descricao_curta": {"type": "string"},
    },
    "required": ["entra", "nao_entra", "base_legal", "termos_tipicos", "descricao_curta"],
    "additionalProperties": False,
}


def ler_temas() -> pd.DataFrame:
    return pd.read_csv(ENTRADA, dtype=str, keep_default_na=False)


def ids(s: str) -> list[str]:
    return [x for x in s.split(";") if x]


def montar_mensagens(r, temas: dict) -> list[dict]:
    def lista(id_list: list[str]) -> str:
        return "\n".join(f"- {t}: {temas[t].caminho}" for t in id_list) or "(nenhum)"

    pai = temas.get(r.parent_id)
    user = Template((PROMPTS / "descricao_tema_user.md").read_text(encoding="utf-8")).substitute(
        tema_id=r.tema_id, caminho=r.caminho, nivel=r.nivel,
        tipo_nivel="tema" if r.nivel == "1" else "subtema",
        descricao_oficial=r.descricao_oficial or "(vazia)",
        pai=f"{pai.tema_id}: {pai.caminho}" if pai is not None else "(nenhum)",
        filhos=lista(ids(r.filhos_ids)), irmaos=lista(ids(r.irmaos_ids)),
        sobreposicoes=lista(ids(r.sobrepoe_ids)),
    )
    system = (PROMPTS / "descricao_tema_system.md").read_text(encoding="utf-8")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validar_resposta(r, resp: dict) -> list[str]:
    """Problemas que o schema não pega. Ids fora da vizinhança são descartados, não corrigidos."""
    problemas = []
    permitidos = set(ids(r.irmaos_ids)) | set(ids(r.sobrepoe_ids))
    fora = [n["tema_id"] for n in resp["nao_entra"] if n["tema_id"] not in permitidos]
    if fora:
        problemas.append(f"nao_entra com ids fora de irmãos/sobreposições (descartados): {fora}")
        resp["nao_entra"] = [n for n in resp["nao_entra"] if n["tema_id"] in permitidos]
    if len(resp["descricao_curta"].split()) > 35:
        problemas.append("descricao_curta longa demais")
    if not 3 <= len(resp["termos_tipicos"]) <= 15:
        problemas.append(f"{len(resp['termos_tipicos'])} termos típicos")
    return problemas


def estimar(df: pd.DataFrame, temas: dict) -> None:
    # Aproximação para português: ~3,5 caracteres por token. A saída inclui folga para raciocínio.
    modelo = SETTINGS["modelos"]["llm_model_descricoes"]
    preco = SETTINGS["precos"][modelo]
    entrada = sum(len(m["content"]) for _, r in df.iterrows() for m in montar_mensagens(r, temas)) / 3.5
    for saida_por_chamada, rotulo in [(400, "sem raciocínio"), (1400, "com ~1.000 tokens de raciocínio")]:
        saida = saida_por_chamada * len(df)
        custo = (entrada * preco["input"] + saida * preco["output"]) / 1e6
        print(f"{modelo}, {len(df)} chamadas, {entrada:,.0f} tokens de entrada, {saida:,} de saída"
              f" ({rotulo}): US$ {custo:.2f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--estimar", action="store_true")
    args = p.parse_args()

    todos = ler_temas()
    temas = {r.tema_id: r for r in todos.itertuples()}
    df = todos[todos.publicavel == "True"]
    if args.estimar:
        estimar(df, temas)
        return

    modelo = SETTINGS["modelos"]["llm_model_descricoes"]
    cli = Cliente(etapa="etapa1b_descricoes")

    def descrever(r) -> dict:
        resp = cli.chat(modelo, montar_mensagens(r, temas), schema=SCHEMA)
        problemas = validar_resposta(r, resp)
        return {"tema_id": r.tema_id, "caminho": r.caminho, "modelo": modelo, **resp, "problemas": problemas}

    linhas = cli.mapear(descrever, list(df.itertuples()))
    with open(SAIDA, "w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")

    print(cli.salvar_custos())
    n_prob = sum(bool(x["problemas"]) for x in linhas)
    print(f"{len(linhas)} descrições → {SAIDA} ({n_prob} com ids descartados em nao_entra)")


if __name__ == "__main__":
    main()
