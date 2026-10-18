"""O tratamento da árvore não pode alterar a entrada nem deixar passar texto sujo."""

import hashlib

import pandas as pd

from src import temas_tratamento as tt


def test_entrada_inalterada_e_validacao_ok():
    antes = hashlib.sha256(tt.ENTRADA.read_bytes()).hexdigest()
    df_raw = tt.ler_entrada()
    df, _ = tt.tratar(df_raw)
    assert tt.validar(df, df_raw) == []
    assert hashlib.sha256(tt.ENTRADA.read_bytes()).hexdigest() == antes


def test_regras_principais():
    df, _ = tt.tratar(tt.ler_entrada())
    r = df.set_index("tema_id")
    assert r.at["5136", "titulo"] == "Dos Crimes contra a Propriedade Imaterial"  # grafia corrigida
    assert "Contra a Paz" in r.at["5146", "caminho"]                            # correção do pai propaga
    assert "defesa" in r.at["5530", "descricao_oficial"]                        # árabe trocado
    assert r.at["5159", "descricao_oficial"] == ""                              # molde com contagem descartado
    assert not r.at["6726", "publicavel"] and r.at["6726", "canonico_id"] == "5199"
    assert not r.at["5062", "publicavel"]                                       # raiz de disciplina
    assert not r.at["5078", "publicavel"]                                       # inativo
    assert r.at["5063", "publicavel"] and "5466" in r.at["5063", "sobrepoe_ids"]
    assert r.at["5171", "generico"] and not r.at["5525", "generico"]            # lixeira × exceção


def test_saida_so_tem_dados_tratados():
    saida = pd.read_csv(tt.SAIDA, dtype=str, keep_default_na=False)
    assert list(saida.columns) == tt.COLUNAS_SAIDA
    assert "descricao" not in saida.columns and "status" not in saida.columns
    assert saida[tt.COLUNAS_ESTRUTURA].equals(tt.ler_entrada()[tt.COLUNAS_ESTRUTURA])
    assert len(saida) == 377
