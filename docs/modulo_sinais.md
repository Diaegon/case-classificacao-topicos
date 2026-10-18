# Módulo 2: sinais

Para cada questão, três sinais independentes sobre qual é o tema. Saída: `data/interim/sinais.csv`.

```bash
make sinais                                   # python -m src.sinais (embeddings em cache)
python -m src.sinais --propor-mapa-assunto    # gera config/mapa_assunto_origem.csv (não sobrescreve)
```

## Para onde vai cada sinal

| Sinal | Juiz LLM (etapa 3) | Regra de decisão (etapa 4) |
|---|---|---|
| (I) Busca híbrida | sim: top-10 + pais, com as fronteiras ("não entra") de cada candidato | sim: o voto está no top-3? score baixo indica "fora" |
| (II) Regra de lei | sim: "cita a Lei X (tema Y), no enunciado" | sim: a lei concorda com o voto? |
| (III) Assunto de origem | **não** (sujo; ancoraria o juiz no erro) | sim: voto fraco e independente |

O juiz sempre recebe a árvore inteira no system prompt e pode escolher um tema fora das sugestões.

## (I) Busca híbrida (`src/sinais_busca.py`)

- **Embeddings** (`text-embedding-3-small`): cosseno entre `texto_completo` da questão e `texto_embedding` do tema.
  Pega o sentido sem palavra em comum.
- **BM25** sobre `texto_bm25` (título + títulos acima + termos típicos). Pega termos técnicos exatos. Tokens em
  minúsculas, sem acento, sem stopwords e sem o vocabulário de instrução ("assinale", "alternativa", "correta"),
  cortados em 6 letras como radical grosseiro.
- **RRF** (k = 60): score = Σ 1/(60 + posição). Funde por posição porque cosseno e BM25 têm escalas incomparáveis.
- Candidatos: só publicáveis, sem filtro por disciplina de origem. Top-10 + pai de cada candidato.

## (II) Regras de lei (`src/sinais_leis.py`, `config/regras_leis.yaml`)

- 26 leis e 2 artigos do CPP (3º-A a 3º-F → Juiz das Garantias; 28-A → ANPP).
- Aceita "Lei nº 11.343/06", "Lei 11343", "L. 11.343", "Lei n. º 11.343", nomes ("Lei de Drogas", "Maria da Penha")
  e siglas em caixa alta (LEP, ECA, CTB). Número sozinho só com ponto e ano ("11.343/06").
- Guarda onde está (enunciado, alternativas ou ambos) e quantas vezes. Citação mostra que o tema aparece, não que é o
  central: Q0070 é prisão preventiva num caso de tráfico.

## (III) Assunto de origem (`src/sinais_assunto.py`, `config/mapa_assunto_origem.csv`)

Proposta automática por par (disciplina, assunto), revisável:

1. Similaridade do assunto com os títulos (≥ 90), primeiro na mesma disciplina. Assunto composto vale pela melhor parte.
2. Nos assuntos com ≥ 5 questões, o tema sugerido (ou pai/filho) precisa aparecer no top-10 da busca em ≥ 30% delas;
   abaixo disso é lixeira do site. Assuntos menores não passam por esse filtro: a própria questão decidiria e o voto
   perderia a independência.

Resultado: 101 pares, 79 com tema; **244 das 341 questões com assunto** recebem voto. Rejeitados como lixeira:
"Concurso de Crimes" (Penal 32 questões, Leg. Especial 11) e "Comunicação dos atos processuais" (13).

## Resultados

| Cobertura | |
|---|---|
| Busca híbrida | 359 (100%), cosseno máximo mediano 0,65 |
| Regra de lei | 70 (19%), 53 com citação no enunciado |
| Assunto de origem | 244 (68%) |

| Concordância | exata | ramo (tema, pai ou filho) |
|---|---|---|
| embedding × BM25 (top-1) | 42% | 49% |
| lei × busca top-1 | 46% | 49% |
| lei × busca top-10 | 79% | 80% |
| assunto × busca top-1 | 11% | 36% |
| assunto × busca top-10 | 55% | 72% |
| lei × assunto | 3% (1/36) | 3% |

Leitura:
- Embedding e BM25 discordam no top-1 em metade dos casos: a fusão e o juiz são necessários; nenhum dos dois sozinho
  basta.
- O tema da lei está no top-10 em 80% dos casos. Nos 20% restantes, ou a lei é só contexto (Q0070, Q0346) ou a busca
  falhou e a regra salva (Q0125 e Q0184, Lei de Drogas).
- Lei × assunto quase nunca concordam: nas questões de Legislação Especial, o site usa assuntos de Penal ("Teoria da
  Pena", "Prescrição") como lixeira. Pendência registrada.

Custo: US$ 0,0034 (710 embeddings), em cache.

## Colunas de `sinais.csv`

`id`, `busca_top_ids` (10 ids, `;`), `busca_pais_ids`, `busca_json` (posição, RRF, cosseno, posição no embedding e no
BM25 de cada candidato), `cos_max`, `top1_emb`, `top1_bm25`, `lei_temas`, `lei_no_enunciado`, `lei_json` (lei, temas,
onde, n), `assunto_tema_id`.
