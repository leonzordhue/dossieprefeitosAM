"""Fotos oficiais dos candidatos (TSE) para quem disputou prefeitura ou foi eleito vereador no AM.

Fonte: TSE, cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes<ano>/fotos/foto_cand<ano>_AM_div.zip (existe de 2004 em diante).
Nome dentro do zip: 2004 "FAM<SG_UE>_<SQ>_div.png" (SQ único só no município); depois "FAM<SQ>_div.<ext>".
Regra do contrato da plataforma (projetos/pesquisa/PLATAFORMA-POLITICOS-AM.md §3): fotos/<pessoa_id>.jpg, 240 px de largura,
JPEG qualidade 80, a foto MAIS RECENTE. Zips ficam em _cache/ (fora do git) e são apagados depois.

Saídas: fotos/<pessoa_id>.jpg, fotos/_indice.csv (pessoa_id, foto_ano, fonte), colunas foto/foto_ano em dados/pessoas.csv,
        dados/integridade/07_fotos.md
Uso: python -I scripts/07_fotos.py   (depois de 02, 05)
"""
import csv
import hashlib
import io
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402,F401  (injeta o truststore)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(BASE_DIR, "dados", "brutos", "tse")
DADOS = os.path.join(BASE_DIR, "dados")
FOTOS = os.path.join(BASE_DIR, "fotos")
CACHE = os.path.join(BASE_DIR, "_cache")
ANOS = (2024, 2020, 2016, 2012, 2008, 2004)  # do mais recente para o mais antigo: a primeira foto achada fica
URL = "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{a}/fotos/foto_cand{a}_AM_div.zip"
NOME = re.compile(r"^F?[A-Z]{2}(?:(\d{5})_)?(\d+)_div\.\w+$", re.I)  # 2012 vem sem o "F": "AM<SQ>_div.jpg"


def pid(titulo):
    return hashlib.sha1(titulo.encode()).hexdigest()[:10]


def main():
    os.makedirs(FOTOS, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)
    alvo = {c["pessoa_id"] for c in csv.DictReader(open(os.path.join(DADOS, "candidaturas_prefeito.csv"), encoding="utf-8"))}
    alvo |= {m["vice_pessoa_id"] for m in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")) if m["vice_pessoa_id"]}
    alvo |= {m["pessoa_id"] for m in csv.DictReader(open(os.path.join(DADOS, "mandatos_vereador.csv"), encoding="utf-8")) if m["pessoa_id"]}
    feitas, linhas, checagens, alertas = {}, [], [], []
    # retoma: anos já processados (com foto gravada no índice) não são baixados de novo
    indice = os.path.join(FOTOS, "_indice.csv")
    if os.path.exists(indice):
        for r in csv.DictReader(open(indice, encoding="utf-8")):
            if os.path.exists(os.path.join(BASE_DIR, r["foto"])):
                feitas[r["pessoa_id"]] = int(r["foto_ano"])
                linhas.append(r)
    for ano in ANOS:
        if ano in feitas.values():
            checagens.append((True, f"{ano}: já processado em rodada anterior (fotos/_indice.csv)"))
            continue
        sq, sq_ano = {}, set()
        with open(os.path.join(TSE, f"consulta_cand_{ano}_AM.csv"), encoding="latin1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                p = pid(r["NR_TITULO_ELEITORAL_CANDIDATO"])
                sq[(r["SG_UE"], r["SQ_CANDIDATO"])] = p
                sq_ano.add((r["SG_UE"], r["SQ_CANDIDATO"]))
                if ano > 2004:
                    sq[(None, r["SQ_CANDIDATO"])] = p
        z = os.path.join(CACHE, f"foto_cand{ano}_AM_div.zip")
        url = URL.format(a=ano)
        if not os.path.exists(z):
            print("baixando", url, flush=True)
            with urllib.request.urlopen(url, timeout=600) as r, open(z + ".part", "wb") as f:
                esperado = int(r.headers.get("Content-Length", 0))
                shutil.copyfileobj(r, f, 1 << 20)
            if esperado and os.path.getsize(z + ".part") != esperado:
                raise SystemExit(f"download incompleto: {url}")
            os.replace(z + ".part", z)
        sem_par = novas = ruins = 0
        with zipfile.ZipFile(z) as zf:
            nomes = [n for n in zf.namelist() if not n.endswith("/")]
            for n in nomes:
                m = NOME.match(os.path.basename(n))
                p = m and sq.get((m.group(1), m.group(2).lstrip("0") or "0")) or (m and sq.get((m.group(1), m.group(2))))
                if not p:
                    sem_par += 1
                    continue
                if p not in alvo or p in feitas:
                    continue
                try:
                    im = Image.open(io.BytesIO(zf.read(n))).convert("RGB")
                    if im.width > 240:
                        im = im.resize((240, round(im.height * 240 / im.width)), Image.LANCZOS)
                    im.save(os.path.join(FOTOS, f"{p}.jpg"), "JPEG", quality=80, optimize=True)
                except Exception as e:  # imagem corrompida no zip do TSE
                    ruins += 1
                    alertas.append(f"{ano} {n}: imagem ilegível ({e.__class__.__name__})")
                    continue
                feitas[p] = ano
                novas += 1
                linhas.append({"pessoa_id": p, "foto": f"fotos/{p}.jpg", "foto_ano": ano, "fonte": f"{url} ({os.path.basename(n)})"})
        # o zip pode ter fotos de candidaturas que saíram do consulta_cand (2012: 8.779 fotos para 7.795 candidaturas);
        # o que prova a ligação é quase toda candidatura do ano achar a sua foto
        ligadas = len(nomes) - sem_par
        checagens.append((ligadas >= 0.95 * min(len(sq_ano), len(nomes)),
                          f"{ano}: {len(nomes)} fotos no zip, {ligadas} ligadas às {len(sq_ano)} candidaturas do consulta_cand "
                          f"(mínimo 95%), {sem_par} sem candidatura, {novas} gravadas, {ruins} ilegíveis"))
        if checagens[-1][0]:
            os.remove(z)  # zip com falha fica em _cache para diagnóstico
    falta = alvo - set(feitas)
    checagens.append((True, f"{len(feitas)} de {len(alvo)} pessoas-alvo com foto; {len(falta)} sem foto no TSE (2000 não tem fotos)"))
    with open(os.path.join(FOTOS, "_indice.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["pessoa_id", "foto", "foto_ano", "fonte"])
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda x: x["pessoa_id"]))
    pessoas = list(csv.DictReader(open(os.path.join(DADOS, "pessoas.csv"), encoding="utf-8")))
    campos = [c for c in pessoas[0] if c not in ("foto", "foto_ano")] + ["foto", "foto_ano"]
    for p in pessoas:
        a = feitas.get(p["pessoa_id"])
        p["foto"], p["foto_ano"] = (f"fotos/{p['pessoa_id']}.jpg", a) if a else ("", "")
    with open(os.path.join(DADOS, "pessoas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(pessoas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "07_fotos.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — fotos (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Alertas\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"fotos={len(feitas)} de {len(alvo)} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
