"""
Gera data/gold/arvore_para_consulta.md: a árvore de temas ativos, para consultar
os tema_id durante a rotulagem manual.

Por que só id, nível e título: as descrições de temas.csv trazem contagens
"N questões no source" vindas da classificação antiga (ruim). Mostrá-las ancoraria
o rotulador nas lixeiras. As 20 descrições reais são mantidas, porque informam o escopo.
Os títulos saem como estão no arquivo original (com erros de grafia), porque o
gabarito usa o tema_id original.

Uso:
    python src/arvore_consulta.py
"""

import csv
import re
from pathlib import Path

ENTRADA = Path("data/raw/temas.csv")
SAIDA = Path("data/gold/arvore_para_consulta.md")
TEXTO_PADRAO = re.compile(r"^(Subtema de |Disciplina \(root\))")


def main() -> None:
    with open(ENTRADA, encoding="utf-8") as f:
        temas = [t for t in csv.DictReader(f) if t["status"] == "active"]
    filhos: dict[str, list[dict]] = {}
    for t in temas:
        filhos.setdefault(t["parent_id"], []).append(t)
    for lista in filhos.values():
        lista.sort(key=lambda t: t["titulo"].lower())

    linhas = [
        "# Árvore de temas (ativos) para consulta durante a rotulagem\n",
        "Formato: `tema_id` título. Nível 0 = disciplina (não usar como rótulo, salvo se nada mais servir).",
        "Títulos como estão no arquivo original. Inativos omitidos.\n",
    ]

    def escrever(t: dict, nivel: int) -> None:
        desc = (t["descricao"] or "").strip()
        extra = f" — _{desc}_" if desc and not TEXTO_PADRAO.match(desc) else ""
        if nivel == 0:
            linhas.append(f"\n## `{t['tema_id']}` {t['titulo']}\n")
        else:
            linhas.append(f"{'  ' * (nivel - 1)}- `{t['tema_id']}` {t['titulo']}{extra}")
        for f_ in filhos.get(t["tema_id"], []):
            escrever(f_, nivel + 1)

    for raiz in filhos.get("", []):
        escrever(raiz, 0)

    SAIDA.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"{len(temas)} temas ativos → {SAIDA}")


if __name__ == "__main__":
    main()
