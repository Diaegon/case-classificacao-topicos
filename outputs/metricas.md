# Métricas

Gerado por `make entregas` a partir de 15 questões rotuladas no gabarito.

## Decisões

| publicar | revisar | fora |
|---|---|---|
| 114 | 243 | 2 |

Precisão prevista 0.83 (0.51–1.00); cobertura 0.32 (0.32–0.68).

## Por nível

| Nível | Questões | Rotuladas | Acertos | Precisão | Wilson (z = 1.96) | Confiança | Decisão |
|---|---|---|---|---|---|---|---|
| A | 114 | 4 | 4 | 100% | 51%–100% | 0.83 | publicar |
| B | 129 | 9 | 8 | 89% | 56%–98% | 0.82 | revisar |
| C | 32 | 0 | 0 | – | 0%–100% | 0.50 | revisar |
| D | 15 | 0 | 0 | – | 0%–100% | 0.50 | revisar |
| E | 67 | 2 | 0 | 0% | 0%–66% | 0.25 | revisar |
| fora | 2 | – | – | – | – | – | fora |

Critério de corte: `pontual` ≥ 95% na precisão acumulada. Pelo limite inferior de Wilson, seria preciso ≥ 73 publicadas rotuladas sem erro.

## Validação cruzada

6 publicadas nas partes de teste, 5 acertos (83%); cortes escolhidos por parte: [1, 1, 2, 1, 1] (níveis publicados a partir de A).

## A regra contra um modelo sozinho

Acerto do tema central em todas as rotuladas (sem abster):

| gpt-5.4-mini (A) | gpt-6-luna (B) | baseline (sem sinais) |
|---|---|---|
| 80% | 93% | 73% |

A regra não tenta acertar mais que um modelo em todas as questões: ela escolhe em quais questões o acerto é alto o bastante para publicar sem revisão.

## Custo

Reprodução completa sem cache: US$ 4.09 (`make custos`).
