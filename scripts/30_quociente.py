"""Vereadores eleitos calculados pelo quociente eleitoral onde o TSE publica o resultado como "#NULO#" (Novo Airão 2008).

Por que: nos arquivos do TSE de 2008, todos os candidatos a vereador de Novo Airão aparecem com resultado "#NULO#"
(candidatos e votação), embora a eleição tenha valido (o prefeito foi eleito com 2.086 votos). Os votos estão publicados.
Fonte: TSE, votacao_candidato_munzona_2008 (votos nominais, via dados/candidaturas_vereador.csv) e votacao_partido_munzona_2008
       (votos de legenda), https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_partido_munzona/votacao_partido_munzona_2008.zip
Regra de 2008 (Código Eleitoral, arts. 106 a 109, antes da Lei 13.165/2015):
  - quociente eleitoral QE = votos válidos (nominais + legenda) / vagas, desprezada a fração ≤ 0,5 e arredondada a maior;
  - quociente partidário de cada partido/coligação = votos do partido/coligação // QE;
  - sobras pela maior média (votos / (vagas já obtidas + 1)), só entre quem atingiu o QE;
  - dentro de cada lista, os mais votados (registro deferido).
Vagas: as da legislatura no TSE nas eleições vizinhas do mesmo município (CF art. 29, IV).
O resultado é CALCULADO (não publicado pelo TSE) e sai marcado assim; serve de alerta até conferência com a Câmara/TRE-AM.

Saídas: dados/vereadores_calculados.csv, dados/integridade/30_quociente.md
Uso: python -I scripts/30_quociente.py
"""
import csv
import io
import os
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
TSE = os.path.join(DADOS, "brutos", "tse")
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_partido_munzona/votacao_partido_munzona_{a}.zip"
CASOS = [("1303205", 2008)]  # (cod_ibge, ciclo) com resultado de vereador "#NULO#" no TSE


def legenda(ano):
    arq = os.path.join(TSE, f"votacao_partido_munzona_{ano}_AM.csv")
    if not os.path.exists(arq):
        b = urllib.request.urlopen(URL.format(a=ano), timeout=300).read()
        z = zipfile.ZipFile(io.BytesIO(b))
        with open(arq, "wb") as f:
            f.write(z.read(next(n for n in z.namelist() if n.endswith("_AM.csv"))))
    return list(csv.DictReader(open(arq, encoding="latin1"), delimiter=";"))


def calcula(cands, leg, vagas):
    """cands: [(pessoa_id, nome, lista, votos)]; leg: {lista: votos de legenda}. Devolve eleitos e o memorial."""
    votos = defaultdict(int)
    for _, _, lista, v in cands:
        votos[lista] += v
    for lista, v in leg.items():
        votos[lista] += v
    validos = sum(votos.values())
    qe = int(validos / vagas + 0.5 - 1e-9) if (validos / vagas) % 1 > 0.5 else int(validos / vagas)
    qp = {lista: v // qe for lista, v in votos.items()}
    aptas = {lista for lista, v in votos.items() if v >= qe}
    cadeiras = {lista: qp[lista] for lista in aptas}
    while sum(cadeiras.values()) < vagas:
        lista = max(aptas, key=lambda l: (votos[l] / (cadeiras[l] + 1), votos[l]))
        cadeiras[lista] += 1
    eleitos = []
    for lista, n in cadeiras.items():
        eleitos += sorted([c for c in cands if c[2] == lista], key=lambda c: -c[3])[:n]
    return eleitos, {"validos": validos, "qe": qe, "votos": dict(votos), "cadeiras": cadeiras}


def main():
    cand = list(csv.DictReader(open(os.path.join(DADOS, "candidaturas_vereador.csv"), encoding="utf-8")))
    linhas, memorias, checagens = [], [], []
    for cod, ciclo in CASOS:
        cs = [r for r in cand if r["cod_ibge"] == cod and int(r["ciclo"]) == ciclo]
        if not all(r["resultado"].startswith(("#NULO", "REGISTRO NEGADO")) for r in cs):
            continue  # o TSE corrigiu: vale o publicado
        vagas = Counter(int(r["ciclo"]) for r in cand if r["cod_ibge"] == cod and r["resultado"].upper().startswith(("ELEITO", "MÉDIA", "QP")))
        vagas = min((v for c, v in vagas.items() if abs(c - ciclo) <= 4), default=9)
        lista = lambda r: r["partido"] if r["coligacao"] in ("", "PARTIDO ISOLADO", "#NULO#") else r["coligacao"]  # noqa: E731
        validos_cand = [(r["pessoa_id"], r["nome"], lista(r), int(r["votos"] or 0)) for r in cs if not r["resultado"].startswith("REGISTRO NEGADO")]
        leg = defaultdict(int)
        nome_mun = cs[0]["municipio"].upper()
        for r in legenda(ciclo):
            if r["DS_CARGO"].upper() == "VEREADOR" and r["NM_MUNICIPIO"].upper() == nome_mun:
                k = r["SG_PARTIDO"] if r["TP_AGREMIACAO"].upper().startswith("PARTIDO") else r["NM_COLIGACAO"]
                leg[k] += int(r["QT_VOTOS_LEGENDA"] or 0)
        eleitos, mem = calcula(validos_cand, leg, vagas)
        memorias.append((cod, ciclo, vagas, mem))
        checagens.append((len(eleitos) == vagas, f"{cs[0]['municipio']} {ciclo}: {len(eleitos)} eleitos calculados para {vagas} vagas (QE {mem['qe']}, válidos {mem['validos']})"))
        for pid, nome, lst, v in eleitos:
            linhas.append({"cod_ibge": cod, "municipio": cs[0]["municipio"], "ciclo": ciclo, "pessoa_id": pid, "vereador": nome, "lista": lst,
                           "votos": v, "resultado": "ELEITO (calculado)",
                           "fonte": f"calculado pelo quociente eleitoral (Código Eleitoral arts. 106–109) com os votos do TSE "
                                    f"(votacao_candidato_munzona_{ciclo} e votacao_partido_munzona_{ciclo}); o TSE publica o resultado como #NULO#"})
    with open(os.path.join(DADOS, "vereadores_calculados.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "municipio", "ciclo", "pessoa_id", "vereador", "lista", "votos", "resultado", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "30_quociente.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — eleitos calculados pelo quociente (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Memorial de cálculo\n\n"
                + "\n".join(f"- {cod} {ciclo}: vagas {v}; válidos {m['validos']}; QE {m['qe']}; cadeiras {m['cadeiras']}; votos por lista {m['votos']}"
                            for cod, ciclo, v, m in memorias)
                + "\n\n⚠️ Resultado calculado, não publicado pelo TSE: conferir com a Câmara Municipal ou o TRE-AM.\n")
    print(f"eleitos={len(linhas)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:  # exemplo do TSE (cartilha): 3 vagas, A 600, B 300, C 100 -> QE 333; A 1 + sobra, B 0? (B < QE fica fora)
        el, m = calcula([("a1", "a1", "A", 400), ("a2", "a2", "A", 200), ("b1", "b1", "B", 300), ("c1", "c1", "C", 100)], {}, 3)
        assert m["qe"] == 333 and m["cadeiras"] == {"A": 3}, m
        el, m = calcula([("a1", "a1", "A", 500), ("a2", "a2", "A", 100), ("b1", "b1", "B", 350), ("c1", "c1", "C", 50)], {}, 3)
        assert m["qe"] == 333 and m["cadeiras"] == {"A": 2, "B": 1}, m
        print("ok")
    else:
        main()
