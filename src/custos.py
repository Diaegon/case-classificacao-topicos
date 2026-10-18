"""
Relatório de custos: custo de reprodução por etapa (outputs/custos.json) e gasto real (cache inteiro).

- Reprodução: quanto custaria gerar do zero os artefatos ATUAIS (soma do uso das respostas que o
  pipeline usa hoje).
- Gasto real: soma do uso de TODAS as respostas guardadas no cache, inclusive as que deixaram de ser
  usadas porque um prompt mudou. Chamadas que falharam (ex.: rate limit) não cobram e não entram.

Uso:
    python -m src.custos
"""

import json

from src.cliente_api import Cliente
from src.config import RAIZ, SETTINGS, caminho


def main() -> None:
    reg = json.loads((caminho("outputs") / "custos.json").read_text(encoding="utf-8"))
    print(f"{'etapa':28}{'reprodução US$':>16}{'tempo API s':>13}")
    for k, v in reg.items():
        if k != "total":
            print(f"{k:28}{v.get('custo_total_usd', 0):>16.4f}{v.get('tempo_api_s', 0):>13.1f}")
    print(f"{'total':28}{reg['total']['custo_total_usd']:>16.4f}{reg['total']['tempo_api_s']:>13.1f}\n")

    total = 0.0
    for d in sorted((RAIZ / SETTINGS["api"]["dir_cache"]).iterdir()):
        if not d.is_dir():
            continue
        usos = [json.loads(f.read_text(encoding="utf-8")).get("uso") for f in d.glob("*.json")]
        custo = sum(Cliente._custo(d.name, u) for u in usos if u)
        total += custo
        print(f"gasto real {d.name:24}{len(usos):>6} respostas  US$ {custo:.4f}")
    print(f"gasto real total{'':30}US$ {total:.4f}")


if __name__ == "__main__":
    main()
