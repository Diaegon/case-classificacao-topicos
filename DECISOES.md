# Decisões tomadas à mão

Cada entrada traz a data, a decisão e o motivo.

## 2026-10-16: Modelos

- **A = `gpt-5.4-mini`, B = `gpt-6-luna`, embedding = `text-embedding-3-small`.** Foi a opção mais barata
  apresentada (~US$ 4 no total estimado). Os modelos A e B são de gerações diferentes, para que os erros
  sejam menos correlacionados e a concordância entre eles tenha valor como sinal. Os preços foram conferidos na página
  oficial da OpenAI na mesma data. Os modelos são trocáveis em `config/settings.yaml`.

## 2026-10-16: Gabarito manual às cegas, sorteado antes de qualquer modelo rodar

- Amostra de 80 questões (`src/amostra_gold.py`, seed 42), estratificada por **disciplina de origem**, com mínimo
  de 8 por disciplina do recorte e 2 para fora do recorte. As questões são embaralhadas para evitar efeito de ordem.
- O CSV de rotulagem **não** traz sugestões de modelo nem assunto de origem, para não ancorar quem rotula.
  O prompt original pedia o CSV "com sugestões"; mudamos de propósito.
- Como o sorteio aconteceu antes dos buckets existirem, ele **não** é estratificado por bucket. Consequência: buckets
  pequenos podem ter poucas questões no gabarito. Se o intervalo de algum bucket ficar largo demais, sorteamos
  uma segunda onda com `--excluir data/gold/amostra_ids.csv`, mirando nesses buckets e mantendo os pesos.
- O gabarito é rotulado **somente pelo usuário**.
- Para consulta durante a rotulagem, `data/gold/arvore_para_consulta.md` traz só id e título dos temas ativos.
  As contagens "N questões no source" ficaram de fora porque vêm da classificação ruim antiga.

## Suposições pendentes (aguardando a recrutadora; configuráveis em `settings.yaml > suposicoes`)

1. Publicar na raiz da disciplina (nível 0) **não** conta como pai: nunca publicamos lá.
2. "Pai ou filho" vale para um nível só.
3. Em temas duplicados, o gabarito usa o nó original (id antigo).

## 2026-10-17: Tratamento da árvore de temas (`src/temas_tratamento.py`)

- **A entrada nunca é alterada.** `data/raw/temas.csv` é somente leitura. A saída é uma tabela nova,
  `data/interim/temas_tratados.csv`, **só com dados tratados** (decisão do usuário): estrutura idêntica ao
  original (`tema_id`, `parent_id`, `disciplina`, `nivel`, testado), textos corrigidos (`titulo`, `caminho`,
  `descricao_oficial`) e as colunas de classificação. O texto cru não é copiado, para nenhum módulo posterior
  usar por engano a descrição com contagens. A auditoria fica no arquivo original. As 377 linhas são mantidas
  (inclusive duplicatas e raízes), porque a função de acerto precisa da árvore completa.
- **Descrições padrão descartadas.** Os 337 textos "Subtema de X. N questões no source" seguem dois moldes fixos
  (conferido) e trazem contagens da classificação antiga, que não podem virar prior. As 20 descrições reais são mantidas.
- **Grafia corrigida por dicionário explícito** (`config/correcoes_grafia.yaml`, 12 títulos + 1 descrição), não por
  corretor automático: é auditável e não "corrige" termo jurídico. Uma correção cujo trecho não existe faz o
  tratamento falhar. A palavra árabe em 5530 ("الدفاع") foi trocada por "defesa", que é o sentido no contexto.
- **Duplicatas** (`config/duplicatas.yaml`, 20 nós 67xx): todo 67xx é folha de nível 1, sem descrição e sem filhos,
  ou seja, irmão do original e não filho. Proposta automática (rapidfuzz, ignorando "(Parte N)"), todos com score
  ≥ 92 e conferidos um a um. O canônico é o nó original; as duplicatas ficam `publicavel=False`.
  Risco: se o gabarito usar o 67xx, publicar no original conta como irmão (erro). Isso depende da pergunta 3
  à recrutadora.
- **Sobreposições mantêm os dois nós publicáveis** (decisão do usuário). `config/sobreposicoes.yaml` lista 24 grupos
  (18 manuais e 6 confirmados a partir da busca por títulos parecidos). Os demais pares da busca por similaridade são
  falsos positivos de texto (ex.: "Teoria Geral das Prisões" × "Teoria Geral das Provas") ou irmãos comuns.
- **Nó pai com sobreposição segue publicável** (decisão do usuário), ex.: 5063 Ação Penal (Penal).
- **Genéricos** (`config/genericos.yaml`): regex de título + 6 lixeiras conhecidas − exceções.   Exceções aprovadas pelo usuário (9): 4366, 4367, 5174, 5468, 5516, 5532, 5573, 5525 e 5513, títulos com
  "Classificação" ou "Princípios" que são cobrados em prova como assunto próprio. Resultado: 25 genéricos.
- **Revisão das descrições enriquecidas:** todas as que citam artigo ou lei (decisão do usuário). As correções vão para
  `config/descricoes_overrides.yaml`; a saída da LLM não é editada à mão.

## 2026-10-17: Curadoria manual dos arquivos de config (em vez de propostas automáticas)

- Grafia, sobreposições, lixeiras e exceções continuam curadas à mão, por `tema_id`. Só as duplicatas têm
  proposta automática. Motivo: o case avalia julgamento, e uma lista revisada com motivo é mais auditável que uma
  heurística. Custo: reutilizar o software com outra árvore exige refazer esses arquivos (ver README,
  "Configurações"). A validação falha se um arquivo citar ids que não existem na base.

## 2026-10-17: Descrições enriquecidas sem base legal nos textos de classificação

- 351 descrições geradas com `gpt-5.4-mini` (US$ 0,99; 2 min 26 s). O modelo citou base legal em 320 temas
  (814 citações). Numa amostra de 15 temas foram achados erros: "arts. 187 a 193 do CPP" em 5193 (são da LEP),
  feminicídio só como qualificadora em 5151 (crime autônomo desde a Lei 14.994/2024).
- **Decisão do usuário (caminho 3):** a base legal fica fora de todos os textos de classificação (embedding, BM25,
  prompt do juiz). Ela continua guardada em `temas_descricoes.jsonl`. As citações numeradas que a LLM escreveu no
  texto livre (102) também são removidas por `src/temas_textos.py`: artigo some com a preposição, e lei numerada
  vira "lei". Termos típicos que eram só citação ("art. 403, caput") saem inteiros. Uma validação garante que
  nenhuma citação sobrou. Citações de lei **nas questões** ficam a cargo de `config/regras_leis.yaml` (etapa 2).
- A revisão "de todas as descrições que citam lei" deixou de ser necessária e foi removida.
- **Overrides de conteúdo** (`config/descricoes_overrides.yaml`), propostos por mim e pendentes de revisão:
  5151 Feminicídio (cobre os regimes antigo e atual) e 5108 Corrupção de Menores (a LLM descreveu a do ECA, art.
  244-B; o tema, em Dignidade Sexual, é a do CP, art. 218). O segundo é um erro de conteúdo, não de citação: tirar
  a base legal não resolve esse tipo de erro.
- 141 ids citados em "não entra" foram descartados por serem filhos ou pai do próprio tema (39 temas). Nenhum id
  inventado.
- **Tabela final:** `data/interim/temas_classificacao.csv` = árvore tratada + campos enriquecidos + três textos
  (embedding sem fronteiras, porque embedding não entende negação; BM25 com título, ancestrais e termos; prompt
  com a descrição curta, ~14 mil tokens para os 351 temas). É a única tabela de temas que as etapas seguintes leem.
- **Custos:** `outputs/custos.json` registra `custo_total_usd`, o custo de gerar tudo do zero, calculado a partir do
  uso guardado em cada resposta do cache. Assim, rodar o pipeline de novo não zera o custo do relatório. O tempo da
  primeira execução das descrições foi registrado à mão (medido), porque o cache não guarda latência.

## 2026-10-17: Pendências não bloqueiam a construção

- Decisão do usuário: montar o pipeline camada por camada e revisar as curadorias depois, quando o conceito estiver
  completo. Toda revisão em aberto fica em `PENDENCIAS.md`; até lá, valem as propostas atuais.

## 2026-10-17: Preparo das questões (etapa 1a)

- Saída em CSV (`data/interim/questoes_tratadas.csv`), e não parquet como no plano inicial: mesmo formato da tabela de
  temas, legível sem código. Só colunas tratadas; `comando` e `enunciado_html` não entram.
- `comando` descartado: parece gerado automaticamente e não informa o conteúdo.
- `texto_completo` = enunciado + alternativas rotuladas ("A) ..."). Em certo/errado (58) as alternativas são só
  "Certo"/"Errado" e ficam de fora.
- HTML: blocos de lixo do Word (comentários condicionais com `<xml>`/`<style>`, Q0099) saem inteiros; `<br>` e `</p>`
  viram quebra de linha para as assertivas I, II, III não se fundirem; "\n" literal no meio das alternativas vira
  espaço; `<sup>o</sup>` vira "º" para a regra de lei da etapa 2 reconhecer "Lei n.º".
- Disciplina de origem: `config/disciplinas_origem.yaml` ("Direito Penal" e "Penal" → Penal; "Direito Processual
  Penal" → Processo Penal). Fora do recorte vira **flag, não "fora" automático**: Q0277 vem como Direito Civil e trata de
  crimes contra o idoso, que tem tema na árvore. Disciplina desconhecida faz o preparo falhar.
- Flags: `enunciado_vazio` (só instrução, 17), `enunciado_curto` (≤ 5 palavras, 25), `ocr_suspeito` (palavra com 5
  consoantes seguidas ou letra triplicada, ignorando números romanos: só Q0078), `disciplina_fora_recorte` (7),
  `sem_disciplina` (1). Nenhuma flag decide sozinha; elas entram na regra da etapa 4.
- A heurística de OCR é deliberadamente simples e pega só o caso grosseiro. Q0078 tem outros erros ("dagrante", "imil
  reis") que ela não detecta; o texto continua legível para o juiz.

## 2026-10-17: Gabarito sobre as questões tratadas

- `src/amostra_gold.py` passou a ler `data/interim/questoes_tratadas.csv` (etapa 1a): o texto para rotular é o mesmo
  `texto_completo` que o pipeline classifica, e o estrato é a disciplina normalizada. A limpeza de HTML própria do
  script foi removida (ela deixava passar, por exemplo, o lixo do Word da Q0099).
- Com a mesma seed (42) e os mesmos tamanhos de estrato, o sorteio é **idêntico**: mesmas 80 questões, mesma ordem.
  Os rótulos já feitos foram mantidos (`--atualizar-texto`, que se recusa a gravar se o sorteio mudar ou se uma linha
  tiver campos a mais). Backup da versão anterior em `data/gold/backup_2026-10-17_pre_sanitizacao/`.

## 2026-10-17: Quais sinais o juiz vê

- Decisão do usuário: o juiz LLM recebe a busca híbrida (top-10 + pais, com as fronteiras de cada candidato) e as
  regras de lei. O **assunto de origem não vai para o juiz**: está sujo e ancoraria o voto no erro. Ele entra só na
  regra de decisão (etapa 4), como voto independente.
- A concordância juiz × busca e juiz × lei não é independente (o juiz viu esses sinais). Isso não invalida a
  estimativa porque a precisão de cada bucket é medida no gabarito; o baseline sem sinais mede o ganho.

## 2026-10-17: Sinais (etapa 2)

- **Busca híbrida:** embeddings (`text-embedding-3-small`, US$ 0,0034) do `texto_completo` contra o `texto_embedding`
  dos 351 temas publicáveis + BM25 contra o `texto_bm25` (minúsculas, sem acento, sem stopwords nem vocabulário de
  instrução, radical grosseiro de 6 letras). Fusão por RRF (k = 60), que usa posição e dispensa calibrar pesos entre
  escalas incomparáveis. Top-10 + pais dos candidatos. Sem filtro por disciplina de origem, que pode estar errada.
- **Regras de lei** (`config/regras_leis.yaml`): lista inicial do usuário + leis com tema óbvio na árvore (CTB, Idoso,
  ECA, Contravenções, Eleitoral, Identificação Criminal, Biossegurança, leis antigas de abuso de autoridade, drogas e
  crime organizado, 12.683 da lavagem). Números sem tema único ficaram de fora e estão listados no arquivo. O número
  sozinho só conta com ponto e ano ("11.343/06"). Guarda onde (enunciado/alternativas) e quantas vezes.
- **Assunto de origem** (`config/mapa_assunto_origem.csv`, proposta automática): similaridade de título (rapidfuzz,
  ≥ 90; mesma disciplina primeiro, e fora dela exige o texto inteiro parecido) e, nos assuntos com ≥ 5 questões,
  concordância ≥ 30% com o top-10 da busca (tema, pai ou filho). O filtro de concordância não vale para assuntos
  pequenos porque, com 1 ou 2 questões, a própria questão decidiria e o voto deixaria de ser independente. Rejeitados
  como lixeira: "Concurso de Crimes" (Penal, 32 questões, 28%; Leg. Especial, lixeira conhecida) e "Comunicação dos atos
  processuais" (13, 23%).
- **Custo de embeddings no cache:** a API informa tokens por lote; o uso é rateado por tamanho e guardado em cada vetor,
  para o custo de reprodução continuar certo.

  ## Observações do modelo

  - Criar a possibilidade de ter id_gerais para questões que misturam diferentes temas como principais.

  - Decidir se o tema da questão é o mais abrangente ou se é o mais próximo do item correto.

  -

## 2026-10-17: Juiz LLM (etapa 3)

- Três variantes, uma chamada independente por questão: A (`gpt-5.4-mini`) e B (`gpt-6-luna`) com a árvore tratada
  e as sugestões (busca top-10 com fronteiras, pais, leis); baseline (`gpt-5.4-mini`) com a árvore crua de
  `temas.csv` (ativos, com as descrições originais, inclusive as contagens) e sem sugestões. As instruções são as
  mesmas nas três, para o baseline medir só o efeito do tratamento e dos sinais.
- Árvore no system prompt: só publicáveis, com marca [GENÉRICO] e "≈ id" nas sobreposições, mais a descrição curta
  (~23 mil tokens). Prefixo idêntico por variante; a 1ª chamada roda sozinha para aquecer o cache.
- Schema: `justificativa` primeiro (a ordem dos campos é a ordem de geração; o modelo diz o que a questão cobra antes de
  escolher), depois central, segunda opção, extras e `nenhum_serve`. Ids inválidos nos campos secundários são
  descartados; central inválido gera uma 2ª tentativa com a correção na conversa (não foi necessária nenhuma vez).
- Rate limit: com 8 chamadas simultâneas de ~26 mil tokens a conta passou de 2 milhões de tokens/min (o prefixo em cache
  também conta). Concorrência do juiz reduzida para 4 (`max_concorrencia_juiz`) e retry com teto de 60 s e jitter. As
  respostas recebidas antes da falha ficaram em cache e não foram pagas de novo; `custo_total_usd` as inclui. O tempo
  da primeira tentativa não foi registrado (`tempo_api_s` cobre só a segunda).
- Custo de reprodução: A US$ 1,88, B US$ 0,24, baseline US$ 1,00 (total da etapa US$ 3,12).

## 2026-10-17: Regra de decisão (etapa 4)

- Consenso entre A e B (baseline fora da decisão): exata → o tema; pai_filho → o pai; irmãos → o pai (se não for a raiz);
  sobreposição e divergência → sem consenso. Todos os casos com consenso publicam num nó que a regra de acerto aceita
  se o gabarito for qualquer um dos dois votos.
- Evidências independentes do voto, pelo ramo (tema, pai ou filho): lei citada, assunto de origem, consenso entre os
  3 primeiros da busca. Níveis: A (concordam + ≥ 2 evidências), B (+ 1), C (+ 0), D (só no pai, irmãos), E (sem
  consenso). Penalidades descem um nível cada: tema genérico (antilixeira), lei citada no enunciado apontando para
  outro tema, OCR suspeito, disciplina de origem fora do recorte.
- Penalidade por níveis em vez de bucket próprio: com 80 questões no gabarito, mais buckets deixariam cada um com
  poucas questões para medir.
- "fora" exige os dois modelos em nenhum_serve E cosseno máximo < 0,60 (~p25). Se a busca achar algo parecido, vai
  para revisar com a sugestão da busca.
- Sem consenso, a sugestão para o professor é o voto com mais evidências (empate: melhor posição na busca; depois A).
- `regras_leis.yaml`: 5569 (Recursos no Âmbito dos Juizados) entrou na regra da Lei 9.099 (Q0012). Como a linha de lei
  vai para o juiz, as 11 questões que citam a 9.099 foram reclassificadas por A e B (US$ 0,03).
- Custos: `make custos` separa custo de reprodução (artefatos atuais) e gasto real (cache inteiro: US$ 4,15 até aqui).
  O tempo de API passou a ser acumulado; o tempo das rodadas completas de A e B da etapa 3 se perdeu ao ser
  sobrescrito pela reexecução parcial (o registro antigo guardava só a última execução). O baseline (220 s) está certo.

## 2026-10-17: Calibração (etapa 5)

- Acerto = previsto no ramo do gabarito (tema, pai ou filho), depois de canonicalizar duplicatas; os acertos que só
  existem pelo mapa de duplicatas são contados à parte (dependem da suposição `duplicata_canonica`).
- Os níveis são ordenados, então a escolha é só o corte ({A}, {A,B}, {A,B,C}, {A,B,C,D}): publica o maior corte cuja
  precisão acumulada passa no critério. Padrão: limite inferior de Wilson ≥ 95% (z = 1,96).
- Validação cruzada (5 partes, seed 42) em vez de separar calibração e teste: com 80 rótulos, dividir deixaria os dois
  lados pequenos demais. A precisão da validação cruzada estima o procedimento fora da amostra.
- Confiança de cada questão = precisão do nível com prior Beta(1, 1): (acertos + 1) / (n + 2).
- Precisão ponderada pelo peso do estrato (amostra estratificada) reportada ao lado da simples.
- Linha do gabarito com vírgula sem aspas na obs: a avaliação junta o excesso na obs e avisa (os campos do rótulo vêm
  antes e não mudam). Não é correção de rótulo; o arquivo do usuário não é alterado.
- Limite descoberto: acertando tudo, n publicadas rotuladas certificam no máximo 1 / (1 + z²/n). Para 95% com
  z = 1,96, n ≥ 73. A amostra de 80 não chega lá: decisão do critério está em PENDENCIAS.md.


## 2026-10-18: Critério pontual e entregas (etapa 6)

- Critério de corte trocado para `pontual` (precisão observada acumulada ≥ 95%), com o Wilson reportado como
  incerteza. Motivo: com um erro já no gabarito (Q0058, nível B), certificar 95% pelo limite inferior exigiria
  ≥ 110 publicadas rotuladas com z = 1,96 e ≥ 87 com z = 1,645, mais que a amostra inteira de 80. O z unilateral
  (proposto antes) não resolve.
- Correção em `escolher_corte`: um nível sem nenhuma rotulada encerra o corte. Antes, C e D (0 rotuladas) entravam de
  carona no acumulado de A+B; numa parte da validação cruzada o corte ia até D.
- Precisão prevista = média da confiança (Beta(1, 1)) das publicadas, não a precisão observada: com 4 rotuladas em A,
  100% observado não é previsão crível. Intervalo = Wilson das publicadas rotuladas.
- Cobertura é exata (publicadas / 359); o intervalo mostra a cobertura dos cortes que a validação cruzada escolheu em
  cada parte (sensibilidade do corte à amostra de rótulos).
- `fora` recebe confiança 0,5 (prior sem dados): o case pede número de 0 a 1 e não há rotuladas nesse grupo.
- Candidata de nível não publicável vai para `revisar` com o consenso como sugestão e o motivo "nível X não publica
  (k/n no gabarito; alvo 95%)", mais as penalidades, se houver.
