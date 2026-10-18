# Módulo 1b: tratamento da árvore de temas

Este módulo transforma `data/raw/temas.csv` (377 temas, intocado) em
`data/interim/temas_classificacao.csv`, **a única tabela de temas que as etapas seguintes leem**
(busca por embedding, BM25, prompt do juiz LLM e função de acerto).

```bash
make temas    # roda os três passos em sequência; com o cache cheio, custo zero
make test     # 3 testes do tratamento
```

## Visão geral

```
data/raw/temas.csv  (somente leitura, sha256 conferido)
   │
   │  src/temas_tratamento.py      determinístico, sem API
   │    + config/correcoes_grafia.yaml, duplicatas.yaml, sobreposicoes.yaml, genericos.yaml
   ▼
data/interim/temas_tratados.csv     árvore limpa + marcações (publicável, genérico, sobreposições, vizinhança)
   │
   │  src/temas_descricoes.py      LLM (gpt-5.4-mini), 1 chamada por tema publicável
   │    + prompts/descricao_tema_system.md, descricao_tema_user.md
   ▼
data/interim/temas_descricoes.jsonl saída bruta da LLM (guardada, nunca editada à mão)
   │
   │  src/temas_textos.py          determinístico, sem API
   │    + config/descricoes_overrides.yaml
   ▼
data/interim/temas_classificacao.csv  tabela final: árvore + descrições + 3 textos de classificação
```

A separação em três passos tem um motivo: o passo caro (LLM) fica isolado e em cache. Mudar uma
regra de limpeza ou de montagem de texto não exige pagar as descrições de novo.

## Passo 1: tratamento (`src/temas_tratamento.py`)

A tabela de saída é **nova**: traz só a estrutura original (`tema_id`, `parent_id`, `disciplina`,
`nivel`) e colunas tratadas. Nenhuma coluna crua é copiada.

| O que faz | Por quê | Resultado |
|---|---|---|
| Descarta as descrições "padrão" (`Subtema de ...`, `Disciplina (root)`) | Seguem dois moldes e trazem a contagem "N questões" da classificação antiga, que não pode virar prior | 20 temas ficam com `descricao_oficial` real |
| Corrige grafia de títulos e descrições (`correcoes_grafia.yaml`) | Erros como "Crimescontra" e "Comeptência" pioram a busca; uma descrição tinha texto em árabe | 11 títulos e 1 descrição corrigidos; falha se o trecho não existir |
| Refaz o `caminho` a partir dos títulos corrigidos | A correção precisa chegar aos filhos (ex.: 5144 corrige 5146) | – |
| Marca o que é publicável | Nível 0 (raiz de disciplina) e inativos não podem receber questão; duplicatas apontam para o original | **351 publicáveis**; 4 raízes, 2 inativos e 20 duplicatas não publicáveis |
| Duplicatas 67xx (`duplicatas.yaml`) | São folhas sem descrição e sem filhos, com título quase igual a outro tema (similaridade ≥ 92) | `canonico_id` aponta para o original |
| Sobreposições (`sobreposicoes.yaml`) | Temas em ramos diferentes que cobrem o mesmo assunto (ex.: 5063 e 5466). Os dois continuam publicáveis; só anotamos | 24 grupos, 50 temas com `sobrepoe_ids` |
| Genéricos (`genericos.yaml`) | Títulos introdutórios ("Conceito", "Princípios", "Disposições gerais") viram lixeira para o classificador | 25 genéricos (regex + lixeiras conhecidas − 9 exceções aprovadas) |
| Vizinhança | `filhos_ids` e `irmaos_ids` (só publicáveis), usados no prompt de descrição e na regra de decisão | – |
| Validação | Estrutura igual à original, ids únicos, pais existentes, nenhum caractere não latino, nenhuma contagem, configs só com ids publicáveis | Falha com mensagem clara se algo quebrar |

**Suposição de risco registrada:** se o gabarito usar o id 67xx da duplicata e nós publicarmos no
original, isso conta como irmão, ou seja, erro. A suposição (`duplicata_canonica: original`) está em
`settings.yaml` e é uma das perguntas pendentes à recrutadora.

## Passo 2: descrições pela LLM (`src/temas_descricoes.py`)

Só 20 dos 351 temas têm descrição real, e um título curto ("Ação Penal") é pouco para separar temas
vizinhos. Para cada tema publicável, o `gpt-5.4-mini` recebe o caminho, o nível, a descrição
oficial, o pai, os filhos, os irmãos e as sobreposições, e devolve, via JSON schema estrito:

| Campo | Conteúdo |
|---|---|
| `entra` | o que uma questão deste tema costuma cobrar |
| `nao_entra` | até 6 fronteiras, **só com irmãos e sobreposições** ("vai para 5105 o ato libidinoso sem violência...") |
| `termos_tipicos` | 5 a 12 termos que aparecem em enunciados |
| `descricao_curta` | até 25 palavras |
| `base_legal` | gerado, mas **não usado** (ver abaixo) |

- A resposta é validada: ids em `nao_entra` que não sejam irmãos nem sobreposições são descartados
  (141 ids em 39 temas, todos filho ou pai). Fronteira com filho estaria errada: publicar no filho
  conta como acerto.
- Custo: **US$ 0,99**, 351 chamadas, 2 min 26 s. Tudo fica em `cache/`; rodar de novo custa zero.

## Passo 3: tabela final (`src/temas_textos.py`)

Junta a árvore tratada com as descrições, aplica os overrides manuais e monta um texto para cada uso:

| Coluna | Montagem | Uso | Tamanho |
|---|---|---|---|
| `texto_embedding` | caminho + `entra` + termos | busca vetorial (etapa 2) | ~84 mil tokens |
| `texto_bm25` | título + títulos dos ancestrais + termos | busca lexical (etapa 2) | curto |
| `texto_prompt` | `descricao_curta` | lista de temas no system prompt do juiz (etapa 3) | ~14 mil tokens |

O `nao_entra` **não vai para o embedding**: embedding não entende negação, e "não confundir com
Roubo" puxaria o vetor de Furto na direção de Roubo. As fronteiras ficam disponíveis para o juiz LLM.

### Base legal fora dos textos

A amostragem achou artigos errados (ex.: tema da LEP citando o CPP). Revisar 814 citações não
compensava, então a base legal saiu de todos os textos:

- o campo `base_legal` é ignorado;
- as 102 citações que a LLM escreveu no texto livre são removidas por regex. O artigo sai com a
  preposição ("a tipificação do art. 147-B do CP:" → "a tipificação:") e a lei numerada vira "lei"
  ("sobre a Lei 12.850/2013 que" → "sobre a lei que");
- termos típicos que eram só citação ("art. 403, caput") saem inteiros;
- uma validação independente barra a geração se sobrar qualquer citação.

Citações de lei **nas questões** continuam sendo sinal forte; elas serão tratadas na etapa 2 por um
mapa revisado à mão (`config/regras_leis.yaml`), não por texto gerado.

### Overrides manuais (`config/descricoes_overrides.yaml`)

Erros de conteúdo que tirar a base legal não resolve. A saída da LLM fica intocada; o override
substitui campos na montagem e é marcado na coluna `override`.

- **5108 Corrupção de Menores:** a LLM descreveu a do ECA; o tema está em Dignidade Sexual (art. 218 do CP).
- **5151 Feminicídio:** a LLM só conhecia a qualificadora; desde a Lei 14.994/2024 é crime autônomo.

Revisão do usuário pendente.

## Colunas de `temas_classificacao.csv`

| Grupo | Colunas |
|---|---|
| Estrutura (igual ao original) | `tema_id`, `parent_id`, `disciplina`, `nivel` |
| Texto tratado | `titulo`, `caminho`, `descricao_oficial` |
| Marcações | `publicavel`, `motivo_nao_publicavel`, `canonico_id`, `generico`, `motivo_generico`, `sobrepoe_ids`, `filhos_ids`, `irmaos_ids` |
| Descrição (LLM + overrides, sem citações) | `entra`, `nao_entra` (`id: fronteira \| ...`), `termos_tipicos` (`;`), `descricao_curta`, `override` |
| Textos de classificação | `texto_embedding`, `texto_bm25`, `texto_prompt` |

Os não publicáveis continuam na tabela, com os textos vazios: a função de acerto precisa da árvore
inteira para saber quem é pai, filho ou irmão.

### Exemplo: 5103 Estupro e Estupro de Vulnerável

- **caminho:** Penal > Dos Crimes Contra a Dignidade Sexual > Estupro e Estupro de Vulnerável
- **descricao_curta:** Estupro e estupro de vulnerável: violência ou grave ameaça, ato libidinoso e hipóteses de vulnerabilidade penal.
- **termos_tipicos:** conjunção carnal; ato libidinoso diverso; violência ou grave ameaça; estupro de vulnerável; menor de 14 anos; ...
- **nao_entra:** 5106 (assédio sexual), 5105 (importunação), 5108 (corrupção de menores), 5104 (violação mediante fraude), 5110 (disposições gerais), 5109 (outros crimes sexuais)

## Números

| | |
|---|---|
| Temas na entrada / saída | 377 / 377 |
| Publicáveis | 351 (Penal 170, Processo Penal 130, Leg. Especial 26, Criminologia 25) |
| Duplicatas, raízes, inativos | 20, 4, 2 |
| Genéricos | 25 |
| Com sobreposição | 50 (24 grupos) |
| Com descrição oficial real | 20 |
| Citações removidas | 102 |
| Overrides | 2 |
| Custo / tempo de API | US$ 0,99 / 145,8 s (`outputs/custos.json`) |

## Infraestrutura compartilhada

- **`src/cliente_api.py`**: único ponto de contato com a OpenAI. Cache em disco por sha256 do pedido
  (modelo + mensagens + schema + parâmetros), gravação atômica, retry com backoff e registro de custo.
  `custo_usd` é o gasto da execução atual; `custo_total_usd` é o custo de reproduzir tudo do zero,
  somando o uso guardado no cache, e não zera quando o pipeline roda de novo.
- **`src/config.py`**: lê `settings.yaml` e o `.env`.
- **`tests/test_temas_tratamento.py`**: entrada inalterada, regras principais (correção, propagação,
  duplicata, raiz, sobreposição, genérico, exceção) e formato da saída.

## O que é curadoria desta base

O código vale para outra árvore. Já `correcoes_grafia.yaml`, `duplicatas.yaml`, `sobreposicoes.yaml`,
as listas de `genericos.yaml` e `descricoes_overrides.yaml` citam ids deste case e teriam de ser
refeitos. Se um deles citar um id inexistente ou não publicável, o tratamento falha em vez de aplicar
config velha em silêncio. Detalhes em `README.md`; o motivo de cada decisão está em `DECISOES.md`.

## Pendências

- Revisão do usuário dos cinco arquivos curados (todos marcados "Revisado por: (pendente)").
- Três suposições à recrutadora: nível 0 não publicável, pai/filho só a um nível de distância, gabarito
  usando o nó original nas duplicatas.
