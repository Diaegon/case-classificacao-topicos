# Pendências

Decisão do usuário (2026-10-17): montar o pipeline camada por camada sem parar para revisar cada
curadoria; as revisões abaixo ficam anotadas e são resolvidas depois que o conceito estiver completo.
Enquanto não forem revisados, os arquivos valem como estão (propostas do Claude, motivo em DECISOES.md).

Marque `[x]` quando resolver. Cada item diz onde mexer e o que regenerar.

## Revisões de curadoria (usuário)

| | Arquivo | O que revisar | Depois de mudar, rodar |
|---|---|---|---|
| [ ] | `config/correcoes_grafia.yaml` | 11 títulos e 1 descrição corrigidos | `make temas` |
| [ ] | `config/duplicatas.yaml` | 20 duplicatas 67xx → original | `make temas` |
| [ ] | `config/sobreposicoes.yaml` | 24 grupos de temas que cobrem o mesmo assunto | `make temas` |
| [ ] | `config/genericos.yaml` | 25 genéricos (lixeiras + regex − 9 exceções) | `make temas` |
| [ ] | `config/descricoes_overrides.yaml` | 5108 Corrupção de Menores e 5151 Feminicídio | `make temas` |
| [ ] | descrições da LLM (`temas_descricoes.jsonl`) | conferir por amostragem, priorizando genéricos e sobreposições; erros viram override | `make temas` |
| [ ] | `config/regras_leis.yaml` | 26 leis + 2 artigos do CPP → tema. Atenção: Lei 8.137/90 também tem crimes contra as relações de consumo (Q0298), hoje só → 4695 | `make sinais` |
| [ ] | `config/mapa_assunto_origem.csv` | 101 pares assunto → tema; 79 aceitos, 22 vazios com motivo. Ver nota da etapa 2 abaixo | `make sinais` |
| [ ] | `config/disciplinas_origem.yaml` | mapa de disciplina de origem → disciplina normalizada / fora do recorte | `make questoes` |

## Perguntas à recrutadora (suposições em `config/settings.yaml` → `suposicoes`)

| | Pergunta | Suposição atual |
|---|---|---|
| [ ] | Publicar na raiz da disciplina (nível 0) conta como pai? | não publicar lá |
| [ ] | "Pai ou filho" vale só para um nível? | sim, um nível |
| [ ] | Nas duplicatas, qual nó o gabarito usa? | o original (id antigo) |

## Gabarito manual (usuário)

| | Item |
|---|---|
| [ ] | Rotular as 80 questões de `data/gold/gold_para_rotular.csv` (15/80 em 2026-10-18). Cada rótulo a mais estreita o intervalo e pode liberar o nível B: rodar `make entregas` |
| [ ] | Corrigir as linhas Q0222, Q0074 e Q0185 do gabarito: obs com vírgula sem aspas (campos a mais). A avaliação já junta o excesso na obs e avisa, mas `amostra_gold.py --atualizar-texto` se recusa a rodar com elas |
| [x] | Critério de publicação: `pontual` com o Wilson como incerteza (2026-10-18, DECISOES.md) |

## Itens abertos pelas etapas

Cada etapa acrescenta aqui o que ficou para revisar.

| | Etapa | Item |
|---|---|---|
| [ ] | 1a | Q0078 tem OCR ruim no enunciado; decidir se vai direto para `revisar` na etapa 4 ou se o juiz decide |
| [ ] | 1a | 8 questões fora do recorte ou sem disciplina (Q0014, Q0016, Q0036, Q0137, Q0142, Q0218, Q0277, Q0309): conferir se o "fora" proposto pela etapa 4 faz sentido |
| [ ] | 2 | Assuntos de Legislação Especial ("Teoria da Pena", "Prescrição", "Medida de Segurança") quase nunca batem com a lei citada: provável lixeira do site. Decidir se todos os assuntos dessa disciplina ficam vazios no mapa |
| [ ] | 2 | Assuntos rejeitados por similaridade < 90 que parecem certos: "Lesão Corporal" → 5077, "Rito Sumaríssimo" → 5539, "Conceitos Gerais de Criminologia" → 4381, "Fixação do regime inicial" → 5576. Preencher `tema_id` à mão se concordar |
| [ ] | 3 | Questões em que algum modelo marcou "nenhum serve": Q0107, Q0132, Q0142, Q0168, Q0358 (Q0168 é Lei Geral do Esporte, sem tema na árvore). Conferir quando a etapa 4 propuser "fora" |
| [ ] | 4 | Os valores da regra (`decisao` em settings.yaml: top-3 da busca, cosseno 0,60 para "fora") e a escolha das penalidades são propostas; a etapa 5 mostra se cada nível se sustenta |
| [x] | 5 | (resolvido: critério pontual) Para certificar 95% pelo limite inferior (z = 1,96) são precisas ≥ 73 publicadas rotuladas sem erro; a amostra de 80 terá ~55 candidatas A+B. Opções: 2ª onda de rótulos só nas candidatas, z = 1,645 (unilateral: ≥ 52 sem erro), ou critério pontual com o Wilson reportado |
| [ ] | 6 | `fora` recebe confiança 0,5 (prior sem dados). Se o avaliador esperar outro valor (vazio, 0 ou a chance de "fora" estar certo), mudar em `src/entregas.py` |
