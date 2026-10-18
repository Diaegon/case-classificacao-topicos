# Módulo 4: regra de decisão

`src/decisao.py` transforma os votos dos dois modelos e os sinais em um **nível de confiança** por questão. Não
chama API. A LLM classifica; quem decide é esta regra. **O limiar de publicação não está aqui**: a etapa 5 mede a
precisão de cada nível no gabarito e escolhe quais níveis publicam.

```bash
make decisao     # → data/interim/decisoes.csv
```

## Passo a passo

1. **Duplicatas → canônico** antes de comparar votos.
2. **Nó de consenso** entre A e B:

   | Concordância | Exemplo | Consenso |
   |---|---|---|
   | exata | 5527 × 5527 | 5527 |
   | pai_filho | Furto 5159 × Crimes contra o Patrimônio 5157 | o pai, 5157 |
   | irmãos | Homicídio 5150 × Feminicídio 5151 | o pai, 5149 Crimes contra a Vida |
   | sobreposição | Ação Penal 5063 (Penal) × 5466 (Processo Penal) | nenhum: o gabarito usa só um |
   | diverge | qualquer outro par | nenhum |

   Em todos os casos com consenso, o nó publicado é um acerto se o gabarito for qualquer um dos dois votos. A raiz da
   disciplina nunca é consenso (irmãos de nível 1 divergem).
3. **Evidências** independentes do voto, todas pelo ramo do consenso (tema, pai ou filho):
   - `ev_lei`: a lei citada aponta para lá (ou para um tema sobreposto);
   - `ev_assunto`: o assunto de origem aponta para lá;
   - `ev_busca`: está entre os 3 primeiros da busca.
4. **Nível:**

   | Nível | Regra |
   |---|---|
   | A | modelos concordam (exata ou pai_filho) + 2 ou 3 evidências |
   | B | modelos concordam + 1 evidência |
   | C | modelos concordam, sem evidência |
   | D | modelos só concordam no pai (irmãos) |
   | E | sem consenso (diverge, sobreposição, ou um modelo disse "nenhum serve") |

5. **Penalidades**, cada uma desce um nível: `generico` (antilixeira), `lei_contra` (lei citada no enunciado apontando
   para outro tema), `ocr_suspeito`, `fora_recorte` (disciplina de origem fora do recorte ou vazia).
6. **Fora:** os dois modelos dizem "nenhum serve" e o cosseno máximo da busca fica abaixo de 0,60 (~percentil 25). Se a
   busca acha algo parecido, vai para revisar com a sugestão da busca.
7. **Sem consenso:** a sugestão para o professor é o voto com mais evidências; empate → melhor posição na busca → A. O
   motivo é legível: "modelos divergem: 5209 (Efeitos da Condenação) vs 4703 (Lei de Execução Penal)".
8. **Extras:** extras dos dois modelos (e o voto vencido, quando não há consenso), fora do ramo do central, até 3.

## Resultados

| Nível | Questões | Decisão prévia |
|---|---|---|
| A | 114 | candidata |
| B | 129 | candidata |
| C | 32 | candidata |
| D | 15 | candidata |
| E | 67 | revisar |
| fora | 2 (Q0142 Tributário, Q0168 Lei Geral do Esporte) | fora |

| Concordância | Questões |
|---|---|
| exata | 250 |
| pai_filho | 28 |
| irmãos | 14 |
| diverge | 55 |
| sobreposição | 7 |
| um "nenhum serve" | 3 |
| os dois "nenhum serve" | 2 |

Penalidades aplicadas: `lei_contra` 15, `generico` 13, `fora_recorte` 7, `ocr_suspeito` 1.

Quais níveis publicam depende da precisão medida no gabarito. Se A e B chegarem a ≥ 95% no limite inferior, a
cobertura fica em torno de 68% (243/359).

## Configuração

`config/settings.yaml` → `decisao`: `busca_top_n` (3), `cos_fora` (0,60), `max_extras` (3).

## Colunas de `decisoes.csv`

`id`, `voto_a`, `voto_b`, `segunda_a`, `segunda_b`, `decisao_previa`, `nivel`, `nivel_sem_penalidade`,
`concordancia`, `tema_central_id`, `extras_ids`, `ev_lei`, `ev_assunto`, `ev_busca`, `lei_contra`, `penalidades`,
`motivo`.
