# Um alvo por etapa. Tudo usa o cache em cache/, então rodar de novo não chama a API.
PY = .venv/bin/python

setup:
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -r requirements.txt

teste-modelos:
	$(PY) -m src.teste_modelos

gold-amostra: questoes   # sorteio às cegas sobre as questões tratadas (não sobrescreve rótulos sem --force)
	$(PY) src/amostra_gold.py --n 80 --seed 42
	$(PY) src/arvore_consulta.py

test:
	$(PY) -m pytest -q tests

.PHONY: setup teste-modelos gold-amostra test

temas:          # árvore tratada (determinístico) e descrições enriquecidas (LLM, com cache)
	$(PY) -m src.temas_tratamento
	$(PY) -m src.temas_descricoes
	$(PY) -m src.temas_textos
.PHONY: temas

questoes:       # preparo das questões (determinístico, sem API)
	$(PY) -m src.questoes_preparo
.PHONY: questoes

sinais:         # busca híbrida (embeddings com cache), regras de lei e assunto de origem
	$(PY) -m src.sinais
.PHONY: sinais

juiz:           # juiz LLM: variantes a, b e baseline (respostas em cache)
	$(PY) -m src.juiz
.PHONY: juiz

decisao:        # regra determinística: consenso, evidências, níveis (sem API)
	$(PY) -m src.decisao

custos:         # custo de reprodução por etapa e gasto real (cache inteiro)
	$(PY) -m src.custos
.PHONY: decisao custos

avaliacao:      # calibração com o gabarito: precisão por nível, Wilson, níveis publicáveis (sem API)
	$(PY) -m src.avaliacao
.PHONY: avaliacao

entregas: avaliacao   # publicacao.csv, previsao.txt e metricas.md, com validador (sem API)
	$(PY) -m src.entregas
.PHONY: entregas
