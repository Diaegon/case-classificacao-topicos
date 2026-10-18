# Módulo 3: juiz LLM

Classifica cada questão com dois modelos e um baseline. **O juiz não decide** publicar, revisar ou fora: ele vota,
e a regra determinística da etapa 4 decide, com a precisão de cada caso medida no gabarito (etapa 5).

```bash
python -m src.juiz --estimar            # tokens e custo, sem API
python -m src.juiz --variante a --limite 5   # piloto → votos_llm_piloto.csv
make juiz                               # três variantes, 359 questões (cache)
python -m src.juiz --resumo             # só o resumo
```

## Variantes

| Variante | Modelo | Árvore no system prompt | Sugestões na mensagem |
|---|---|---|---|
| A | gpt-5.4-mini | tratada: 351 publicáveis, descrição curta, [GENÉRICO], "≈ id" | busca top-10 (com fronteiras) + pais + leis |
| B | gpt-6-luna | idem | idem |
| baseline | gpt-5.4-mini | crua: `temas.csv` ativo, como veio | nenhuma |

A e B são de gerações diferentes, para os erros serem menos correlacionados. O baseline existe só para o
relatório: mostra quanto o tratamento da árvore e os sinais ajudam. As instruções são as mesmas nas três.

## Prompts (`prompts/`)

- `juiz_system.md`: instruções + `$arvore`. Regras principais: o central é o que o aluno precisa saber para
  acertar, não o contexto; com várias assertivas, o tema comum ou predominante, e os outros em extras; dúvida entre
  irmãos → pai; genérico só se cobra o conceito geral; ramo certo nas sobreposições; nunca inventar id;
  `nenhum_serve` quando nada couber; sugestões são pista, não resposta.
- `juiz_user.md`: a questão + o bloco de sugestões.
- `juiz_sugestoes.md`: candidatos da busca (com o "não confundir" de cada um), pais e leis citadas.
- `juiz_correcao.md`: mensagem da 2ª tentativa quando o central não existe na lista.

## Saída estruturada

`justificativa` (primeiro, para o modelo explicar o que a questão cobra antes de escolher), `tema_central_id`,
`segunda_opcao_id`, `extras_ids` (até 3), `nenhum_serve`. Validação: ids fora da lista são descartados nos campos
secundários; central inválido gera uma 2ª tentativa, e se falhar de novo o voto fica `valido = False`.

## Resultados (sem gabarito: concordância não é precisão)

| | A | B | baseline |
|---|---|---|---|
| votos inválidos | 0 | 0 | 0 |
| 2ª tentativa | 0 | 0 | 0 |
| nenhum serve | 3 | 4 | 4 |
| genérico como central | 15 | 18 | 23 |
| igual ao top-1 da busca | 194 | 176 | 154 |
| fora do top-10 da busca (nem pai/filho) | 6 | 19 | 33 |
| nó não publicável (raiz, duplicata) | – | – | 6 |

| Concordância | exata | ramo (tema, pai ou filho) |
|---|---|---|
| A × B | 69% | 77% |
| A × baseline | 64% | 74% |
| B × baseline | 63% | 73% |

Leitura:
- A e B concordam no ramo em 77% das questões: é o candidato natural a publicar, se o gabarito confirmar. Os 23%
  restantes devem ir para revisão.
- O baseline escolhe mais temas genéricos (23 contra 15) e 6 vezes um nó que não pode ser publicado (raiz de
  disciplina ou duplicata 67xx): efeito da árvore crua. Quanto isso custa em precisão sai do gabarito.
- A concorda mais com a busca que B (194 contra 176 no top-1); parte disso é ancoragem nas sugestões.

## Custo

| Variante | Custo de reprodução |
|---|---|
| A | US$ 1,88 |
| B | US$ 0,24 |
| baseline | US$ 1,00 |
| **Total** | **US$ 3,12** |

Cache do prefixo: 78% (A), 88% (B) e 98% (baseline) dos tokens de entrada. A primeira rodada bateu no limite de 2
milhões de tokens por minuto da conta com 8 chamadas simultâneas; o juiz agora usa 4 (`max_concorrencia_juiz`).

## Colunas de `votos_llm.csv`

`id`, `variante`, `modelo`, `justificativa`, `tema_central_id`, `segunda_opcao_id`, `extras_ids` (`;`),
`nenhum_serve`, `valido`, `tentativas`, `problemas`. Uma linha por questão e variante (1.077 linhas).
