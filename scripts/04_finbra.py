"""FINBRA — Finanças do Brasil, dados contábeis dos municípios (Tesouro Nacional), exercícios 2000-2012, só o Amazonas.

Fonte: https://www.tesourotransparente.gov.br/publicacoes/finbra-dados-contabeis-dos-municipios-1989-a-2012/<ano>/26
       (cada página aponta um zip em thot-arquivos.tesouro.gov.br com um banco Access .mdb).
Base legal da declaração: LRF (LC 101/2000) art. 51; antes do SICONFI, Quadro de Dados Contábeis Consolidados (QDCC).
O esquema muda de ano para ano, então tudo vai para o formato longo, sem interpretar colunas:
  dados/financas/finbra_longo.csv  (ano, tabela, cod_ibge, municipio, coluna, valor) — valores zero omitidos;
  a URL de origem de cada ano está em dados/brutos/finbra/_proveniencia.json
Proveniência (URL, sha256 do zip, tabelas, linhas do AM) em dados/brutos/finbra/_proveniencia.json;
integridade em dados/integridade/04_finbra.md (quais municípios não declararam em cada ano).
Requer o driver ODBC "Microsoft Access Driver (*.mdb, *.accdb)" (vem com o Office) e pyodbc.
Uso: python -I scripts/04_finbra.py
"""
import csv
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime

import pyodbc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRUTOS = os.path.join(BASE_DIR, "dados", "brutos", "finbra")
PAGINA = "https://www.tesourotransparente.gov.br/publicacoes/finbra-dados-contabeis-dos-municipios-1989-a-2012/{}/26"
ANOS = range(2000, 2013)
UF_AM = 13
# colunas que identificam o município em cada tabela (o FINBRA usa CD_UF/CD_MUN; DSubFuncao usa UF/Cod Mun)
CHAVES = (("CD_UF", "CD_MUN"), ("UF", "Cod Mun"), ("CdUF", "CdMun"))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    os.makedirs(BRUTOS, exist_ok=True)
    muns = {int(m["cod_ibge"]) // 10 % 10000: m for m in
            csv.DictReader(open(os.path.join(BASE_DIR, "dados", "municipios.csv"), encoding="utf-8"))}
    assert len(muns) == 62
    prov, linhas, cobertura = {}, [], {}
    for ano in ANOS:
        html = rede.get(PAGINA.format(ano)).decode("utf-8", "replace")
        urls = sorted(set(re.findall(r"https://thot-arquivos\.tesouro\.gov\.br/publicacao/\d+", html)))
        if len(urls) != 1:
            raise SystemExit(f"{ano}: esperava 1 arquivo na página do FINBRA, achei {urls}")
        zbytes = rede.get(urls[0])
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
        mdbs = [n for n in zf.namelist() if n.lower().endswith(".mdb")]
        if len(mdbs) != 1:
            raise SystemExit(f"{ano}: esperava 1 .mdb no zip, achei {zf.namelist()}")
        mdb = os.path.join(BRUTOS, f"{ano}.mdb")
        if not os.path.exists(mdb):
            open(mdb, "wb").write(zf.read(mdbs[0]))
        con = pyodbc.connect(r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + mdb + ";")
        cur = con.cursor()
        tabelas = [t.table_name for t in cur.tables(tableType="TABLE")]
        info, declararam = {}, set()
        for t in tabelas:
            cur.execute(f"SELECT * FROM [{t}]")
            cols = [d[0] for d in cur.description]
            chave = next((k for k in CHAVES if k[0] in cols and k[1] in cols), None)
            if not chave or t.startswith(("Cod ", "CT ", "Pop")):
                continue  # tabelas de código/descrição e população não são dados do município
            iu, im = cols.index(chave[0]), cols.index(chave[1])
            n = 0
            for r in cur.fetchall():
                if num(r[iu]) != UF_AM:
                    continue
                m = muns.get(int(num(r[im])))
                if not m:
                    raise SystemExit(f"{ano} {t}: município AM sem par no IBGE: CD_MUN={r[im]}")
                n += 1
                declararam.add(m["cod_ibge"])
                for c, v in zip(cols, r):
                    if c in chave or not num(v):  # zeros omitidos (≈80% das células); ausência = 0 ou não declarado
                        continue
                    linhas.append({"ano": ano, "tabela": t, "cod_ibge": m["cod_ibge"], "municipio": m["municipio"],
                                   "coluna": c.strip(), "valor": num(v)})
            info[t] = n
        con.close()
        cobertura[ano] = declararam
        prov[ano] = {"pagina": PAGINA.format(ano), "url": urls[0], "membro": mdbs[0],
                     "sha256_zip": hashlib.sha256(zbytes).hexdigest(), "linhas_AM_por_tabela": info,
                     "coletado_em": datetime.now().isoformat(timespec="seconds")}
        print(ano, len(declararam), "municípios", info, flush=True)

    os.makedirs(os.path.join(BASE_DIR, "dados", "financas"), exist_ok=True)
    with open(os.path.join(BASE_DIR, "dados", "financas", "finbra_longo.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["ano", "tabela", "cod_ibge", "municipio", "coluna", "valor"])  # fonte por ano: _proveniencia.json
        w.writeheader()
        w.writerows(linhas)
    json.dump(prov, open(os.path.join(BRUTOS, "_proveniencia.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nomes = {m["cod_ibge"]: m["municipio"] for m in muns.values()}
    with open(os.path.join(BASE_DIR, "dados", "integridade", "04_finbra.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — FINBRA 2000-2012 (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n")
        f.write("Município ausente = não declarou as contas ao Tesouro naquele ano (o dado não existe na fonte).\n\n")
        f.write("| Ano | Declararam | Ausentes |\n|---|---|---|\n")
        for ano, dec in cobertura.items():
            aus = sorted(nomes[c] for c in nomes if c not in dec)
            f.write(f"| {ano} | {len(dec)} de 62 | {', '.join(aus) or '—'} |\n")
    print("linhas", len(linhas))


if __name__ == "__main__":
    main()
