"""
Sorteia uma amostra aleatória e estratificada de questões para o gabarito manual.

Por que estratificar: sorteio puro poderia trazer pouquíssimas questões de
Criminologia ou Legislação Especial (estratos pequenos). Aqui cada disciplina
recebe uma fatia proporcional ao seu tamanho, com um mínimo garantido.

Por que embaralhar a ordem final: rotular todas as questões de uma disciplina
em sequência cria vício de cansaço e de contexto. A ordem de rotulagem é aleatória.

Por que "às cegas": o CSV de rotulagem NÃO traz assunto_origem, disciplina_origem
nem sugestões de modelos, para não ancorar a sua decisão. Esses dados ficam
em um arquivo separado (amostra_ids.csv), junto com o peso de cada estrato.

Base: as questões JÁ TRATADAS (data/interim/questoes_tratadas.csv, etapa 1a). O texto mostrado
para rotular é o mesmo `texto_completo` que o pipeline classifica, e o estrato é a disciplina
normalizada. Rode `make questoes` antes.

Uso:
    python src/amostra_gold.py --n 80 --seed 42

Texto atualizado sem perder rótulos (ex.: depois de mudar a limpeza das questões):
    python src/amostra_gold.py --n 80 --seed 42 --atualizar-texto
    Refaz o sorteio, confere que saíram as MESMAS questões e reescreve os arquivos copiando
    gold_tema_id, gold_extras, certeza e obs do CSV atual. Se o sorteio mudar, não grava nada.

Onda 2 (sem repetir questões já sorteadas):
    python amostra_gold.py --n 30 --seed 7 --excluir data/gold/amostra_ids.csv \
        --prefixo onda2_
"""

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

FORA_DO_RECORTE = "Outras (fora do recorte)"
ROTULOS = ["gold_tema_id", "gold_extras", "certeza", "obs"]


def ler_questoes(caminho: Path) -> list[dict]:
    """Lê a tabela tratada (uma linha por questão)."""
    if not caminho.exists():
        sys.exit(f"{caminho} não existe. Rode `make questoes` (etapa 1a) antes.")
    with open(caminho, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def texto_completo(q: dict) -> str:
    return q["texto_completo"]


def estrato(q: dict) -> str:
    # Disciplina já normalizada na etapa 1a; vazia = fora do recorte ou sem disciplina.
    return q["disciplina"] or FORA_DO_RECORTE


def ler_rotulos(arq: Path) -> dict[str, dict]:
    rotulos = {}
    with open(arq, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            # Campo a mais (vírgula sem aspas num rótulo) não pode ser cortado em silêncio:
            # não dá para saber a qual coluna ele pertence.
            if r.get(None):
                sys.exit(f"{arq}: a linha de {r['id']} tem mais campos que o cabeçalho "
                         "(vírgula sem aspas?). Corrija à mão e rode de novo. Nada foi gravado.")
            rotulos[r["id"]] = {c: r.get(c, "") for c in ROTULOS}
    return rotulos


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--questoes", default="data/interim/questoes_tratadas.csv")
    p.add_argument("--n", type=int, default=80)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--minimo", type=int, default=8, help="mínimo de questões por disciplina do recorte")
    p.add_argument("--minimo-fora", type=int, default=2, help="mínimo para disciplinas fora do recorte")
    p.add_argument("--saida", default="data/gold")
    p.add_argument("--prefixo", default="", help="prefixo dos arquivos (ex.: onda2_)")
    p.add_argument("--excluir", help="CSV com coluna 'id' de questões já sorteadas")
    p.add_argument("--force", action="store_true", help="sobrescrever arquivos existentes (APAGA rótulos)")
    p.add_argument("--atualizar-texto", action="store_true",
                   help="reescrever os textos mantendo os rótulos; exige o mesmo sorteio")
    args = p.parse_args()

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    arq_rotular = saida / f"{args.prefixo}gold_para_rotular.csv"
    arq_ler = saida / f"{args.prefixo}gold_para_ler.md"
    arq_ids = saida / f"{args.prefixo}amostra_ids.csv"
    rotulos = {}
    if arq_rotular.exists() and args.atualizar_texto:
        rotulos = ler_rotulos(arq_rotular)
    elif arq_rotular.exists() and not args.force:
        sys.exit(f"{arq_rotular} já existe (pode conter rótulos seus). "
                 "Use --atualizar-texto para manter os rótulos ou --force para sobrescrever.")

    questoes = ler_questoes(Path(args.questoes))
    excluidos = set()
    if args.excluir:
        with open(args.excluir, encoding="utf-8") as f:
            excluidos = {linha["id"] for linha in csv.DictReader(f)}

    por_estrato = defaultdict(list)
    for q in questoes:
        if q["id"] not in excluidos:
            por_estrato[estrato(q)].append(q)
    for lista in por_estrato.values():
        lista.sort(key=lambda q: q["id"])

    tamanhos = {e: len(v) for e, v in por_estrato.items()}
    minimos_ok = {e: (args.minimo_fora if e == FORA_DO_RECORTE else args.minimo) for e in tamanhos}
    aloc = alocar_com_minimos(tamanhos, args.n, minimos_ok)

    rng = random.Random(args.seed)
    amostra = []
    for e in sorted(por_estrato):
        escolhidas = rng.sample(por_estrato[e], aloc[e])
        peso = tamanhos[e] / aloc[e] if aloc[e] else 0
        amostra += [(q, e, peso) for q in escolhidas]
    rng.shuffle(amostra)

    if rotulos:
        # Os rótulos só podem ser copiados se o sorteio for o mesmo: outra questão no lugar
        # receberia um rótulo que não é dela.
        novas, antigas = {q["id"] for q, _, _ in amostra}, set(rotulos)
        if novas != antigas:
            sys.exit(f"O sorteio mudou (saíram {sorted(antigas - novas)}, entraram {sorted(novas - antigas)}). "
                     "Nada foi gravado. Rotule a amostra atual ou use --force para uma amostra nova.")

    with open(arq_rotular, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "id", "texto", "gold_tema_id", "gold_extras", "certeza", "obs"])
        for i, (q, _, _) in enumerate(amostra, 1):
            r = rotulos.get(q["id"], {})
            w.writerow([i, q["id"], texto_completo(q), *(r.get(c, "") for c in ROTULOS)])

    with open(arq_ler, "w", encoding="utf-8") as f:
        f.write("# Questões para rotular\n\n")
        f.write("Preencha os rótulos no CSV. certeza = alta | media | baixa.\n\n")
        for i, (q, _, _) in enumerate(amostra, 1):
            f.write(f"## {i}. {q['id']}\n\n{texto_completo(q)}\n\n---\n\n")

    with open(arq_ids, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ordem", "id", "estrato", "peso_estrato", "disciplina", "assunto_origem", "seed"])
        for i, (q, e, peso) in enumerate(amostra, 1):
            w.writerow([i, q["id"], e, f"{peso:.4f}", q["disciplina"], q["assunto_origem"], args.seed])

    if rotulos:
        n_rot = sum(1 for r in rotulos.values() if any(r.values()))
        print(f"Mesmo sorteio: textos atualizados, {n_rot} questões com rótulo preservadas.\n")
    print(f"{len(questoes)} questões lidas, {len(excluidos)} excluídas, {len(amostra)} sorteadas (seed={args.seed})\n")
    print(f"{'estrato':38}{'total':>7}{'amostra':>9}{'fração':>9}")
    for e in sorted(tamanhos, key=lambda e: -tamanhos[e]):
        print(f"{e:38}{tamanhos[e]:>7}{aloc[e]:>9}{aloc[e] / tamanhos[e]:>9.0%}")
    print(f"\nArquivos:\n  {arq_rotular}  (rotule aqui, às cegas)\n  {arq_ler}  (leitura confortável)\n  {arq_ids}  (metadados e pesos; não abra antes de rotular)")


def alocar_com_minimos(tamanhos: dict[str, int], n: int, minimos: dict[str, int]) -> dict[str, int]:
    """Alocação proporcional, com mínimo por estrato e maiores restos para fechar n."""
    total = sum(tamanhos.values())
    if n > total:
        sys.exit(f"Erro: n={n} é maior que o total disponível ({total}).")
    aloc = {e: min(minimos[e], t) for e, t in tamanhos.items()}
    if sum(aloc.values()) > n:
        teto = n // len(tamanhos)
        print(f"Aviso: a soma dos mínimos excede n={n}; usando mínimo de {teto} por estrato.\n")
        aloc = {e: min(teto, minimos[e], t) for e, t in tamanhos.items()}
    restante = n - sum(aloc.values())
    folga = {e: tamanhos[e] - aloc[e] for e in tamanhos}
    total_folga = sum(folga.values())
    cotas = {e: restante * folga[e] / total_folga if total_folga else 0 for e in folga}
    for e in aloc:
        aloc[e] += int(cotas[e])
    sobra = n - sum(aloc.values())
    for e in sorted(cotas, key=lambda e: cotas[e] - int(cotas[e]), reverse=True):
        if sobra == 0:
            break
        if aloc[e] < tamanhos[e]:
            aloc[e] += 1
            sobra -= 1
    return aloc


if __name__ == "__main__":
    main()
