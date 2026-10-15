"""Baixa os dados abertos do TSE das eleições municipais (2000-2024) e guarda só os CSVs do Amazonas.

Fonte: Portal de Dados Abertos do TSE — https://dadosabertos.tse.jus.br (arquivos em cdn.tse.jus.br/estatistica/sead/odsele/)
Saída: dados/brutos/tse/<conjunto>_<ano>_AM.csv + dados/brutos/tse/_proveniencia.json (URL, tamanho, sha256, data da coleta)
Uso: python -I scripts/01_tse_baixar.py   (retoma: pula o que já foi extraído)
"""
import datetime
import hashlib
import json
import os
import shutil
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(BASE_DIR, "_cache")  # zips inteiros (fora do git), apagados após extrair
SAIDA = os.path.join(BASE_DIR, "dados", "brutos", "tse")
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/{c}/{c}_{a}.zip"
ANOS = (2000, 2004, 2008, 2012, 2016, 2020, 2024)
# bem_candidato só existe a partir de 2008 (404 em 2000/2004, conferido em 15/10/2026)
CONJUNTOS = {"consulta_cand": ANOS, "votacao_candidato_munzona": ANOS, "bem_candidato": ANOS[2:]}
PROV = os.path.join(SAIDA, "_proveniencia.json")


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(SAIDA, exist_ok=True)
    prov = json.load(open(PROV, encoding="utf-8")) if os.path.exists(PROV) else {}
    for c, anos in CONJUNTOS.items():
        for a in anos:
            destino = os.path.join(SAIDA, f"{c}_{a}_AM.csv")
            if f"{c}_{a}" in prov and os.path.exists(destino):
                continue
            url = URL.format(c=c, a=a)
            z = os.path.join(CACHE, f"{c}_{a}.zip")
            print("baixando", url, flush=True)
            with urllib.request.urlopen(url, timeout=120) as r, open(z + ".part", "wb") as f:
                esperado = int(r.headers.get("Content-Length", 0))
                shutil.copyfileobj(r, f, 1 << 20)
            if esperado and os.path.getsize(z + ".part") != esperado:  # integridade: download incompleto
                raise SystemExit(f"download incompleto: {url} ({os.path.getsize(z + '.part')} de {esperado} bytes)")
            os.replace(z + ".part", z)
            with zipfile.ZipFile(z) as zf:
                if zf.testzip() is not None:
                    raise SystemExit(f"zip corrompido: {z}")
                am = [n for n in zf.namelist() if n.upper().endswith("_AM.CSV")]
                if len(am) != 1:
                    raise SystemExit(f"{z}: esperava 1 CSV do AM, achei {am}")
                with zf.open(am[0]) as src, open(destino, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            prov[f"{c}_{a}"] = {"url": url, "bytes_zip": esperado, "sha256_zip": sha256(z), "membro": am[0],
                                "arquivo": os.path.relpath(destino, BASE_DIR).replace("\\", "/"),
                                "sha256_csv": sha256(destino), "coletado_em": datetime.datetime.now().isoformat(timespec="seconds")}
            json.dump(prov, open(PROV, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.remove(z)
            print("  ok", am[0], flush=True)
    print("FIM", len(prov), "arquivos")


if __name__ == "__main__":
    main()
