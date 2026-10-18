"""O preparo das questões não pode alterar a entrada nem deixar passar HTML ou perder conteúdo."""

import hashlib

import pandas as pd
import yaml

from src import questoes_preparo as qp


def tratar():
    return qp.tratar(qp.ler_entrada(), yaml.safe_load(qp.DISCIPLINAS.read_text(encoding="utf-8")))


def test_limpar_html():
    assert qp.limpar_html("A<br><br>I - um<br>II - dois") == "A\nI - um\nII - dois"      # assertivas separadas
    assert qp.limpar_html("<!--[if gte mso 9]><xml><w:X/></xml><![endif]--><p>texto</p>") == "texto"
    assert qp.limpar_html("<style>p{mso-x:1}</style>ok") == "ok"
    assert qp.limpar_html("Ministério\\nPúblico&nbsp;e <i>habeas corpus</i> .") == "Ministério Público e habeas corpus."
    assert qp.limpar_html("Lei n. <sup>o</sup> 10.826") == "Lei n. º 10.826"


def test_entrada_inalterada_e_validacao_ok():
    antes = hashlib.sha256(qp.ENTRADA.read_bytes()).hexdigest()
    df = tratar()
    assert qp.validar(df, 359) == []
    assert hashlib.sha256(qp.ENTRADA.read_bytes()).hexdigest() == antes


def test_regras_principais():
    r = tratar().set_index("id")
    assert r.at["Q0001", "texto_completo"].count("\n") >= 9                     # 4 assertivas + 5 alternativas
    assert "mso-" not in r.at["Q0099", "texto_completo"]                         # lixo do Word removido
    assert r.at["Q0033", "enunciado_curto"] and "A)" in r.at["Q0033", "texto_completo"]
    assert r.at["Q0090", "enunciado_vazio"]                                      # "Assinale a alternativa CORRETA."
    assert r.at["Q0078", "ocr_suspeito"] and not r.at["Q0020", "ocr_suspeito"]   # número romano não é OCR
    assert r.at["Q0169", "disciplina"] == "Processo Penal"                       # "Direito Processual Penal"
    assert r.at["Q0277", "disciplina_fora_recorte"] and r.at["Q0036", "sem_disciplina"]
    ce = r[r.tipo == "certo_errado"]
    assert len(ce) == 58 and (ce.alternativas == "").all()                       # "Certo/Errado" não é conteúdo


def test_saida_sem_comando():
    saida = pd.read_csv(qp.SAIDA, dtype=str, keep_default_na=False)
    assert len(saida) == 359 and "comando" not in saida.columns and "enunciado_html" not in saida.columns
