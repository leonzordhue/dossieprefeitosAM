"""Acesso HTTP comum aos scripts: certificados do Windows (truststore; a rede da SEINFRA quebra a cadeia ICP-Brasil),
gzip, novas tentativas e cache em disco (dados/brutos/cache_http) para o reprocessamento não depender da rede."""
import gzip
import hashlib
import json
import os
import time
import urllib.request

import truststore

truststore.inject_into_ssl()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(BASE_DIR, "dados", "brutos", "cache_http")


def em_cache(url):
    return os.path.exists(os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:20]))


def esquecer(url):
    """Tira a resposta do cache (ex.: resposta vazia gravada durante instabilidade da API)."""
    arq = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:20])
    if os.path.exists(arq):
        os.remove(arq)


def get(url, tentativas=5, cache=True, data=None):
    """Bytes da URL. Com cache=True, a resposta fica gravada e é reutilizada (a URL é a chave; num POST, URL + corpo).
    data (bytes) faz POST de formulário."""
    arq = os.path.join(CACHE, hashlib.sha1(url.encode() + (b"\n" + data if data else b"")).hexdigest()[:20])
    if cache and os.path.exists(arq):
        return open(arq, "rb").read()
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, data=data, headers={"Accept-Encoding": "gzip", "User-Agent": "dossieprefeitosAM/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                dados = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or dados[:2] == b"\x1f\x8b":
                    dados = gzip.decompress(dados)
            break
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(3 * 2 ** i)
    if cache:
        os.makedirs(CACHE, exist_ok=True)
        open(arq, "wb").write(dados)
    return dados


def get_json(url, **kw):
    return json.loads(get(url, **kw))
