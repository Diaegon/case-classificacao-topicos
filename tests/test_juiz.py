"""Validação do voto do juiz: ids inventados nunca passam; central inválido gera uma nova tentativa."""

from src.juiz import validar, votar

VALIDOS = {"5527", "5524", "5534"}


def resp(central, seg="", extras=(), nenhum=False):
    return {"justificativa": "x", "tema_central_id": central, "segunda_opcao_id": seg,
            "extras_ids": list(extras), "nenhum_serve": nenhum}


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def chat(self, modelo, msgs, schema=None):
        self.chamadas.append(msgs)
        return self.respostas.pop(0)


def test_campos_secundarios_limpos():
    r, probs = validar(resp("5527", seg="9999", extras=["5527", "5524", "abc", "5524"]), VALIDOS)
    assert r["segunda_opcao_id"] == "" and r["extras_ids"] == ["5524"] and len(probs) == 4   # segunda + central repetido + inventado + duplicado


def test_central_invalido_tenta_de_novo_uma_vez():
    cli = ClienteFalso([resp("6726"), resp("5534")])
    v = votar(cli, "m", [{"role": "user", "content": "q"}], VALIDOS)
    assert v["tema_central_id"] == "5534" and v["valido"] and v["tentativas"] == 2
    assert "6726" in cli.chamadas[1][-1]["content"]                     # a correção cita o id errado


def test_central_invalido_duas_vezes_fica_invalido():
    v = votar(ClienteFalso([resp("1"), resp("2")]), "m", [], VALIDOS)
    assert not v["valido"]


def test_nenhum_serve_e_valido_sem_central():
    v = votar(ClienteFalso([resp("", nenhum=True)]), "m", [], VALIDOS)
    assert v["valido"] and v["tema_central_id"] == "" and v["tentativas"] == 1
