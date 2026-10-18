"""
Etapa 2, sinal I: busca híbrida (embeddings + BM25, fundidos por Reciprocal Rank Fusion).

- Embeddings pegam o sentido sem palavra em comum ("subtrair coisa alheia" ~ Furto).
- BM25 pega termos técnicos exatos ("desaforamento", "impronúncia"), em que o embedding é fraco.
- RRF funde por POSIÇÃO, não por score: cosseno e BM25 têm escalas incomparáveis, e RRF dispensa
  calibrar pesos (score = Σ 1/(k + posição), k = 60, valor usual da literatura).

Só temas publicáveis entram como candidatos. O pai de cada candidato do top-10 é anexado
(marcado como "pai"), porque publicar no pai conta como acerto e o juiz precisa enxergá-lo.
"""

import re
import unicodedata

import numpy as np
from rank_bm25 import BM25Okapi

K_RRF = 60
TOP = 10

# Palavras sem conteúdo temático: artigos, preposições e o vocabulário de instrução das provas
# ("assinale a alternativa correta"), que aparece em quase toda questão.
STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para ao aos
e ou que se com sem sob sobre entre ate apos como mais menos muito ja nao sim ser sera sao foi
esta este esse essa isso isto aquele aquela seu sua seus suas ele ela eles elas lhe lhes quando
qual quais onde cujo cuja tal tais todo toda todos todas outro outra outros outras mesmo mesma
assinale alternativa alternativas correta corretas incorreta incorretas afirmativa afirmativas
assertiva assertivas opcao item itens julgue analise marque considere questao acima abaixo seguir
""".split())


def dobrar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(s: str) -> list[str]:
    """Minúsculas, sem acento, sem stopwords; corta em 6 letras como radical grosseiro
    ("prisão"/"prisões" → "prisao"/"prisoe"... "preventiva"/"preventivo" → "preven")."""
    return [w[:6] for w in re.findall(r"[a-z]{3,}", dobrar(s)) if w not in STOPWORDS]


def ranking(scores: np.ndarray) -> np.ndarray:
    """Posição (1 = melhor) de cada tema."""
    ordem = np.argsort(-scores, kind="stable")
    pos = np.empty_like(ordem)
    pos[ordem] = np.arange(1, len(scores) + 1)
    return pos


def normalizar(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def buscar(vet_q: np.ndarray, vet_t: np.ndarray, toks_q: list[list[str]], bm25: BM25Okapi,
           tema_ids: list[str], pai: dict[str, str], publicaveis: set[str]) -> list[dict]:
    """Para cada questão → {top: [...], cos_max, ...}."""
    cos = normalizar(vet_q) @ normalizar(vet_t).T
    saida = []
    for i, tq in enumerate(toks_q):
        s_emb, s_bm = cos[i], bm25.get_scores(tq)
        r_emb, r_bm = ranking(s_emb), ranking(s_bm)
        rrf = 1 / (K_RRF + r_emb) + 1 / (K_RRF + r_bm)
        top_idx = np.argsort(-rrf, kind="stable")[:TOP]
        top = [{"tema_id": tema_ids[j], "pos": k + 1, "rrf": round(float(rrf[j]), 5),
                "cos": round(float(s_emb[j]), 4), "pos_emb": int(r_emb[j]), "pos_bm25": int(r_bm[j])}
               for k, j in enumerate(top_idx)]
        ids_top = {t["tema_id"] for t in top}
        pais = sorted({pai[t] for t in ids_top if pai.get(t) in publicaveis} - ids_top)
        saida.append({"top": top, "pais": pais, "cos_max": round(float(s_emb.max()), 4),
                      "top1_emb": tema_ids[int(np.argmax(s_emb))], "top1_bm25": tema_ids[int(np.argmax(s_bm))]})
    return saida
