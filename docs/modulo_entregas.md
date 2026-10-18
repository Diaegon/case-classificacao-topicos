# Módulo 6: entregas

`src/entregas.py` junta a regra (etapa 4) e a calibração (etapa 5) e escreve as entregas do case. Não chama API.

```bash
make entregas    # roda make avaliacao antes → outputs/publicacao.csv, previsao.txt, metricas.md
```

## Decisão final

| Situação na etapa 4 | Decisão | tema_central_id | motivo |
|---|---|---|---|
| nível em `niveis_publicaveis` (calibração) | `publicar` | consenso dos modelos | vazio |
| candidata de nível que não publica | `revisar` | consenso (sugestão) | "nível B não publica (8/9 no gabarito; alvo 95%)" + penalidades |
| nível E | `revisar` | voto com mais evidências | motivo da regra ("modelos divergem: …") |
| fora | `fora` | vazio | motivo da regra |

`confianca` = (acertos + 1) / (n + 2) do nível no gabarito (prior Beta(1, 1)). "fora" não tem rotuladas: recebe o
prior sem dados, 0,5.

## Previsão (`previsao.txt`)

- **Precisão:** ponto = média da confiança das publicadas; intervalo = Wilson das publicadas rotuladas.
  A média a posteriori fica abaixo da precisão observada de propósito: 4/4 não é uma previsão crível de 100%.
- **Cobertura:** ponto = publicadas / 359 (exata: é uma escolha); intervalo = cobertura dos cortes escolhidos em cada
  parte da validação cruzada, ou seja, quanto o corte mudaria com outra amostra de rótulos.

## Validador

Roda antes de gravar; se falhar, o script para e nada é escrito. Confere: colunas do modelo, 359 linhas, ids únicos,
decisão válida, confiança em [0, 1], motivo em `revisar` e `fora`, central publicável (vazio em `fora`), extras
publicáveis e fora do ramo do central. Testes em `tests/test_entregas.py`.
