"""Candidatos do AM inabilitados pelo TCU para cargo em comissão ou função de confiança (Lei 8.443/1992, art. 60).

Fonte: API pública do TCU, https://contas.tcu.gov.br/ords/condenacao/consulta/inabilitados (lista vigente, com CPF,
processo, acórdão, trânsito em julgado e fim da inabilitação).
Ligação: SÓ por CPF idêntico ao do registro de candidatura no TSE (consulta_cand 2000-2020; em 2024 o TSE mascara o CPF).
Homônimo sem CPF igual não entra. O CPF não é publicado: a saída traz só o pessoa_id.
Inabilitação é sanção administrativa do TCU; não é inelegibilidade automática (quem decide é a Justiça Eleitoral).

Saídas: dados/indicadores/tcu_inabilitados.csv, dados/integridade/13_tcu.md
Uso: python -I scripts/13_tcu.py
"""
import csv
import hashlib
import os
import re
import sys
import unicodedata
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
TSE = os.path.join(DADOS, "brutos", "tse")
API = "https://contas.tcu.gov.br/ords/condenacao/consulta/inabilitados"
ANOS_CPF = (2000, 2004, 2008, 2012, 2016, 2020)


def sem_acento(s):
    return re.sub(r"[^A-Z]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper())


def so_digitos(s):
    return re.sub(r"\D", "", s or "").zfill(11)


def main():
    cpf_pid, nome_pid = {}, {}
    for a in ANOS_CPF:
        with open(os.path.join(TSE, f"consulta_cand_{a}_AM.csv"), encoding="latin1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                c = so_digitos(r["NR_CPF_CANDIDATO"])
                if c.strip("0") and not r["NR_CPF_CANDIDATO"].startswith("-"):
                    p = hashlib.sha1(r["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10]
                    if cpf_pid.get(c, p) != p:
                        cpf_pid[c] = None  # mesmo CPF com títulos diferentes: ambíguo, não liga
                    else:
                        cpf_pid[c] = p
                    nome_pid[p] = r["NM_CANDIDATO"]
    itens, url = [], API + "?limit=1000"
    while url:
        d = rede.get_json(url, cache=False)
        itens += d.get("items", [])
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None) if d.get("hasMore") else None
    checagens = [(len(itens) > 100, f"{len(itens)} inabilitados na lista vigente do TCU")]
    linhas, por_nome = [], []
    for x in itens:
        p = cpf_pid.get(so_digitos(x["cpf"]))
        if p:
            linhas.append({"pessoa_id": p, "nome_tcu": x["nome"], "processo": x["processo"], "acordao": x["deliberacao"],
                           "data_acordao": (x["data_acordao"] or "")[:10], "transito_julgado": (x["data_transito_julgado"] or "")[:10],
                           "inabilitado_ate": (x["data_final"] or "")[:10], "uf": x["uf"], "municipio": x["municipio"],
                           "ligacao": "cpf", "fonte": f"TCU {API} (processo {x['processo']})"})
            if sem_acento(x["nome"]) != sem_acento(nome_pid[p]):
                por_nome.append(f"{p}: nome no TCU “{x['nome']}” ≠ no TSE “{nome_pid[p]}” (mesmo CPF)")
    checagens.append((not por_nome, f"nomes conferem entre TCU e TSE nos {len(linhas)} casos ligados por CPF"))
    with open(os.path.join(DADOS, "indicadores", "tcu_inabilitados.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["pessoa_id", "nome_tcu", "processo", "acordao", "data_acordao", "transito_julgado", "inabilitado_ate",
                               "uf", "municipio", "ligacao", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "13_tcu.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — TCU inabilitados (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Divergência de nome (verificar)\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in por_nome) or "- nenhuma") + "\n")
    print(f"tcu={len(itens)} ligados={len(linhas)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
