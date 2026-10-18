"""
Único ponto de contato com a API da OpenAI.

- Cache em disco: chave = sha256(tipo + modelo + entrada + parâmetros). Uma resposta
  em cache nunca é pedida de novo, então o pipeline é reprodutível e rodar de novo é grátis.
- Registro de custo: tokens, custo estimado e tempo por etapa, em outputs/custos.json.
  Dois custos: custo_usd (gasto nesta execução; cache = zero) e custo_total_usd (quanto
  custaria gerar tudo do zero, somando o uso guardado em cada resposta do cache). O
  relatório usa o segundo, que não muda quando o pipeline roda de novo.
- Retry com backoff em erros transitórios.

Uso:
    from src.cliente_api import Cliente
    cli = Cliente(etapa="etapa3_juiz")
    resp = cli.chat(modelo, mensagens, schema=SCHEMA)   # dict já parseado do JSON
    vetores = cli.embeddings(modelo, textos)
    cli.salvar_custos()
"""

import hashlib
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from src.config import RAIZ, SETTINGS, caminho

ERROS_TRANSITORIOS = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Cliente:
    def __init__(self, etapa: str):
        self.etapa = etapa
        self.cfg = SETTINGS["api"]
        self.dir_cache = RAIZ / self.cfg["dir_cache"]
        self._openai = None  # criado só se houver chamada fora do cache
        self._lock = threading.Lock()
        self.inicio = time.time()
        self.stats = {"chamadas_api": 0, "chamadas_cache": 0, "tokens_input": 0,
                      "tokens_cached": 0, "tokens_output": 0, "custo_usd": 0.0, "custo_total_usd": 0.0}

    # ---------- infraestrutura ----------

    @property
    def openai(self) -> OpenAI:
        if self._openai is None:
            self._openai = OpenAI(timeout=self.cfg["timeout_s"])
        return self._openai

    def _cache_get(self, modelo: str, chave: str):
        arq = self.dir_cache / modelo / f"{chave}.json"
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None

    def _cache_put(self, modelo: str, chave: str, dado) -> None:
        arq = self.dir_cache / modelo / f"{chave}.json"
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(dado, ensure_ascii=False), encoding="utf-8")
        tmp.replace(arq)  # escrita atômica: um processo interrompido não deixa cache corrompido

    def _com_retry(self, fn):
        for tentativa in range(self.cfg["max_tentativas"]):
            try:
                return fn()
            except ERROS_TRANSITORIOS:
                if tentativa == self.cfg["max_tentativas"] - 1:
                    raise
                # Backoff exponencial com teto e jitter: sem o jitter, as threads que bateram no
                # limite de tokens por minuto juntas voltam juntas e batem de novo.
                time.sleep(min(60, 2 ** tentativa * 2) * (1 + random.random()))

    @staticmethod
    def _custo(modelo: str, uso: dict) -> float:
        preco = SETTINGS["precos"].get(modelo)
        if preco is None:
            raise KeyError(f"Sem preço para '{modelo}' em settings.yaml (precos).")
        nao_cached = uso["input"] - uso["cached"]
        return (nao_cached * preco["input"] + uso["cached"] * preco["cached_input"]
                + uso["output"] * preco["output"]) / 1e6

    def _registrar(self, modelo: str, uso: dict | None, de_cache: bool = False) -> None:
        """uso = tokens da resposta (se conhecidos). de_cache=True: não houve gasto agora."""
        with self._lock:
            custo = self._custo(modelo, uso) if uso else 0.0
            self.stats["custo_total_usd"] += custo
            if de_cache:
                self.stats["chamadas_cache"] += 1
                return
            self.stats["chamadas_api"] += 1
            self.stats["tokens_input"] += uso["input"]
            self.stats["tokens_cached"] += uso["cached"]
            self.stats["tokens_output"] += uso["output"]
            self.stats["custo_usd"] += custo

    # ---------- chamadas ----------

    def chat(self, modelo: str, mensagens: list[dict], schema: dict | None = None, **params) -> dict:
        """
        Uma chamada de chat. Com `schema`, usa structured outputs (JSON schema estrito)
        e devolve o dict parseado; sem schema, devolve {"texto": ...}.
        `params` (ex.: reasoning_effort) entram na chave do cache.
        """
        pedido = {"tipo": "chat", "modelo": modelo, "mensagens": mensagens, "schema": schema, "params": params}
        chave = _hash(pedido)
        em_cache = self._cache_get(modelo, chave)
        if em_cache is not None:
            self._registrar(modelo, em_cache.get("uso"), de_cache=True)
            return em_cache["resposta"]

        kwargs = dict(model=modelo, messages=mensagens, **params)
        if schema is not None:
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": "saida", "strict": True, "schema": schema}}
        r = self._com_retry(lambda: self.openai.chat.completions.create(**kwargs))
        conteudo = r.choices[0].message.content
        resposta = json.loads(conteudo) if schema is not None else {"texto": conteudo}

        detalhes = getattr(r.usage, "prompt_tokens_details", None)
        uso = {"input": r.usage.prompt_tokens, "output": r.usage.completion_tokens,
               "cached": (getattr(detalhes, "cached_tokens", 0) or 0) if detalhes else 0}
        self._registrar(modelo, uso)
        self._cache_put(modelo, chave, {"pedido": pedido, "resposta": resposta, "uso": uso})
        return resposta

    def embeddings(self, modelo: str, textos: list[str], lote: int = 256) -> list[list[float]]:
        """Embeddings com cache por texto (mudar um texto não invalida os outros)."""
        saida: list = [None] * len(textos)
        faltando = []
        for i, t in enumerate(textos):
            em_cache = self._cache_get(modelo, _hash({"tipo": "emb", "modelo": modelo, "texto": t}))
            if em_cache is not None:
                saida[i] = em_cache["vetor"]
                self._registrar(modelo, em_cache.get("uso"), de_cache=True)
            else:
                faltando.append(i)

        for k in range(0, len(faltando), lote):
            idx = faltando[k:k + lote]
            r = self._com_retry(lambda: self.openai.embeddings.create(model=modelo, input=[textos[i] for i in idx]))
            self._registrar(modelo, {"input": r.usage.prompt_tokens, "cached": 0, "output": 0})
            # A API informa os tokens do lote, não de cada texto: rateamos pelo tamanho, para que o
            # custo de reprodução (custo_total_usd) continue certo quando o vetor vier do cache.
            total_chars = sum(len(textos[i]) for i in idx) or 1
            for i, d in zip(idx, r.data):
                saida[i] = d.embedding
                uso = {"input": r.usage.prompt_tokens * len(textos[i]) / total_chars, "cached": 0, "output": 0}
                self._cache_put(modelo, _hash({"tipo": "emb", "modelo": modelo, "texto": textos[i]}),
                                {"vetor": d.embedding, "uso": uso})
        return saida

    def mapear(self, fn, itens: list, concorrencia: int | None = None) -> list:
        """Aplica fn a cada item com concorrência limitada, preservando a ordem."""
        with ThreadPoolExecutor(max_workers=concorrencia or self.cfg["max_concorrencia"]) as ex:
            return list(ex.map(fn, itens))

    # ---------- relatório ----------

    def salvar_custos(self) -> dict:
        """Grava as estatísticas desta etapa em outputs/custos.json (sobrescreve só a própria etapa)."""
        arq = caminho("outputs") / "custos.json"
        todos = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        registro = dict(self.stats, custo_usd=round(self.stats["custo_usd"], 4),
                        custo_total_usd=round(self.stats["custo_total_usd"], 4),
                        tempo_s=round(time.time() - self.inicio, 1))
        # Tempo de API ACUMULADO entre execuções: uma execução toda em cache não soma nada, e uma
        # reexecução parcial (só os prompts que mudaram) soma só o que de fato chamou a API.
        # Sobrescrever com a última execução apagava o tempo da rodada completa.
        anterior = todos.get(self.etapa, {})
        registro["tempo_api_s"] = round(anterior.get("tempo_api_s", 0)
                                        + (registro["tempo_s"] if self.stats["chamadas_api"] else 0), 1)
        todos[self.etapa] = registro
        etapas = [v for k, v in todos.items() if k != "total"]
        todos["total"] = {
            "custo_total_usd": round(sum(v.get("custo_total_usd", 0) for v in etapas), 4),
            "tempo_api_s": round(sum(v.get("tempo_api_s", 0) for v in etapas), 1),
        }
        arq.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")
        return registro
