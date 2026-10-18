# Módulo 1a: preparo das questões

Transforma `data/raw/questoes.jsonl` (359 questões, intocado) em `data/interim/questoes_tratadas.csv`,
a tabela de questões que as etapas seguintes leem. Não chama API.

```bash
make questoes   # python -m src.questoes_preparo
make test
```

## O que faz (`src/questoes_preparo.py`)

| Passo | Detalhe |
|---|---|
| Leitura | linha a linha; uma linha que não for JSON válido, ou sem algum campo, para o preparo com o número da linha |
| Limpeza de HTML | remove blocos de lixo do Word (`<!--[if mso]>`, `<xml>`, `<style>`, Q0099); `<br>` e `</p>` viram quebra de linha (assertivas I, II, III separadas); `\n` literal vira espaço; `<sup>o</sup>` vira "º"; entidades e `&nbsp;` decodificados |
| Texto de trabalho | `texto_completo` = enunciado + "A) ...", "B) ...". Certo/errado: só o enunciado. O `comando` é descartado (gerado automaticamente, sem conteúdo) |
| Disciplina | `config/disciplinas_origem.yaml` normaliza ("Direito Penal" → Penal) e marca as fora do recorte. Disciplina desconhecida faz o preparo falhar |
| Flags | ver abaixo; nenhuma decide sozinha, todas vão para a regra da etapa 4 |
| Validação | 359 linhas, ids únicos, nenhum texto vazio, nenhum resto de HTML, múltipla escolha com ≥ 4 alternativas |

## Flags

| Flag | Regra | Questões |
|---|---|---|
| `enunciado_vazio` | o enunciado é só uma instrução ("Assinale a alternativa correta.") | 17 |
| `enunciado_curto` | até 5 palavras ("A prisão preventiva") | 25 |
| `ocr_suspeito` | palavra com 5 consoantes seguidas ou letra triplicada (romanos ignorados) | 1 (Q0078) |
| `disciplina_fora_recorte` | Constitucional, Civil, Tributário, Ambiental, "Disciplina Unificada" | 7 |
| `sem_disciplina` | disciplina de origem vazia | 1 (Q0036) |

Fora do recorte **não é** "fora" automático: Q0277 vem como Direito Civil e trata de crimes contra o
idoso, que tem tema na árvore.

## Colunas da saída

`id`, `enunciado`, `alternativas`, `texto_completo`, `tipo` (`multipla_escolha` 301 / `certo_errado` 58),
`n_alternativas`, `disciplina` (normalizada; vazia se fora do recorte), `assunto_origem` (espaços
normalizados; continua sujo, vale só como voto fraco na etapa 2), as cinco flags, `ocr_palavras` e
`n_palavras` (mediana 129, de 16 a 639).

## Exemplo: Q0001

```
No que se refere ao Tribunal do Júri, analise as assertivas abaixo.
I - O desaforamento é admitido por interesse da ordem pública, ...
II - A natureza jurídica da impronúncia é de uma decisão terminativa ...
III - A absolvição sumária produz coisa julgada material.
IV - A decisão de desclassificação tem natureza não terminativa.
A) I, II e IV, apenas.
B) II e IV, apenas.
...
```
