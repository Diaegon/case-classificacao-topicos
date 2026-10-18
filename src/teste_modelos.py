"""
Confere se os modelos de settings.yaml estão liberados na conta: uma chamada mínima
por modelo, com structured outputs (custo total < US$ 0,001).

Uso:
    python -m src.teste_modelos
"""

from src.cliente_api import Cliente
from src.config import SETTINGS

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}


def main() -> None:
    m = SETTINGS["modelos"]
    cli = Cliente(etapa="etapa0_teste_modelos")
    for modelo in sorted({m["llm_model_a"], m["llm_model_b"], m["llm_model_descricoes"]}):
        try:
            r = cli.chat(modelo, [{"role": "user", "content": 'Responda {"ok": true}.'}], schema=SCHEMA)
            print(f"OK    {modelo}: {r}")
        except Exception as e:  # noqa: BLE001 — aqui o objetivo é justamente listar o erro
            print(f"FALHA {modelo}: {type(e).__name__}: {e}")
    try:
        v = cli.embeddings(m["embedding_model"], ["teste de embedding"])
        print(f"OK    {m['embedding_model']}: dimensão {len(v[0])}")
    except Exception as e:  # noqa: BLE001
        print(f"FALHA {m['embedding_model']}: {type(e).__name__}: {e}")
    print(cli.salvar_custos())


if __name__ == "__main__":
    main()
