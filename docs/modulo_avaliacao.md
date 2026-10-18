# Módulo 5: calibração com o gabarito

`src/avaliacao.py` mede a precisão de cada nível da regra (etapa 4) no gabarito manual e escolhe quais níveis
publicam. Não chama API. Roda com o que estiver rotulado.

```bash
make avaliacao   # → data/interim/calibracao.json e avaliacao_questoes.csv
```

## Passo a passo

1. **Lê o gabarito** (`data/gold/gold_para_rotular.csv`): só linhas com `gold_tema_id`. Id fora da árvore faz o
   script parar; raiz de disciplina é aceita com aviso. Linha com vírgula sem aspas na obs: o excesso é juntado na
   obs, com aviso.
2. **Acerto** (`acerto(pred, gold, arv)`): o previsto está no ramo do gabarito (tema, pai ou filho). Irmão é erro.
   Duplicatas viram o canônico; acertos que só existem por isso são contados à parte.
3. **Precisão por nível** (A a E) com intervalo de Wilson.
4. **Corte**: os níveis são ordenados, então só há 4 opções ({A}, {A,B}, {A,B,C}, {A,B,C,D}). Publica o maior corte
   cuja precisão **acumulada** passa no critério (`pontual`, em uso desde 2026-10-18, ou `limite_inferior` de Wilson
   ≥ 95%). Um nível sem nenhuma rotulada encerra o corte: não entra de carona no acumulado dos de cima.
5. **Validação cruzada** (5 partes): cada questão é testada por um corte escolhido sem ela. Estima a precisão fora
   da amostra sem gastar metade dos rótulos num conjunto de teste.
6. **Confiança** de cada nível: (acertos + 1) / (n + 2), prior Beta(1, 1). Vai para a coluna `confianca` da etapa 6.
7. **Para o relatório**: precisão ponderada pelo peso do estrato; acerto de A, B e baseline sozinhos.

## O limite da amostra

Mesmo sem nenhum erro, n publicadas rotuladas certificam no máximo `1 / (1 + z²/n)`. Para 95% com z = 1,96,
n ≥ 73. Na amostra de 80, as candidatas A+B devem ficar em torno de 55, então o critério estrito não publica nada
por construção. Com um erro, seriam ≥ 110 (≥ 87 com z = 1,645). Por isso o critério
em uso é o `pontual`, com o Wilson reportado como incerteza (DECISOES.md, 2026-10-18).

## Configuração

`config/settings.yaml` → `calibracao`: `precisao_alvo` (0,95), `criterio` (pontual), `z` (1,96), `folds` (5),
`prior` ([1, 1]).

## Saídas

- `calibracao.json`: níveis publicáveis (pelo critério e pelo pontual), precisão, Wilson, ponderada, validação
  cruzada, confiança por nível, tabela por nível, acerto isolado de cada modelo, avisos.
- `avaliacao_questoes.csv`: uma linha por questão rotulada, com nível, previsto, gabarito e acerto de A, B e baseline.
