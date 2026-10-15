"""Série harmonizada das finanças municipais do AM, 2000-2025: uma linha por município e ano.

Entradas (geradas antes): dados/financas/finbra_longo.csv (04_finbra.py, 2000-2012), dados/financas/dca_despesa_funcao.csv,
dca_receita.csv e rgf_pessoal.csv (03_siconfi.py, 2014-2025), dados/indicadores/ibge.csv (08_ibge.py).
2013 não existe em nenhuma das duas fontes (o FINBRA para em 2012; a DCA do SICONFI começa em 2014): fica lacuna.

Definições (a fonte de cada coluna fica em fonte_serie):
  - despesa_empenhada: despesa orçamentária empenhada, sem intraorçamentárias (Lei 4.320/1964, art. 58-60)
  - desp_<função>: despesa empenhada na função da Portaria MOG 42/1999. Em 2000-2001 o FINBRA usa a classificação antiga
    ("Saúde e Saneamento", "Educação e Cultura"), que não é comparável: essas colunas ficam vazias nesses anos.
  - receita_orcamentaria: FINBRA "Rec Orçamentária"; SICONFI "Total Receitas" brutas menos as deduções (FUNDEB,
    transferências constitucionais, outras) — a receita que fica no município.
  - pessoal_empenhado: FINBRA, natureza "Pessoal e Encargos Sociais" (até 2012)
  - dtp_pct_rcl: despesa total com pessoal do Executivo / RCL (RGF Anexo 1, LRF art. 19-20; limite 54%), 2014+
  - pct_saude_desp / pct_educacao_desp: participação na despesa empenhada total. NÃO é o mínimo constitucional
    (15% saúde, LC 141/2012; 25% educação, CF art. 212), que usa a receita de impostos como base (ver 12_minimos.py).

Saídas: dados/indicadores/financas.csv, dados/integridade/11_financas.md
Uso: python -I scripts/11_financas.py
"""
import csv
import os
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
FIN = os.path.join(DADOS, "financas")
FUNCOES = {"01": "legislativa", "04": "administracao", "08": "assistencia", "10": "saude", "12": "educacao",
           "15": "urbanismo", "17": "saneamento", "26": "transporte"}
NOME_FINBRA = {"Legislativa": "legislativa", "Administração": "administracao", "Assistência Social": "assistencia",
               "Saúde": "saude", "Educação": "educacao", "Urbanismo": "urbanismo", "Saneamento": "saneamento", "Transporte": "transporte"}
TAB_FUNCAO = {2002: "RecDesp", 2003: "RecDesp", 2004: "DFuncao"}  # 2005-2012: DSubFuncao


def ler(nome):
    p = os.path.join(FIN, nome)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def main():
    muns = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    pop = {(r["cod_ibge"], int(r["ano"])): float(r["populacao"]) for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "ibge.csv"),
                                                                                            encoding="utf-8")) if r["populacao"]}
    lin = defaultdict(dict)
    checagens, alertas = [], []

    # ---- FINBRA 2000-2012
    for r in ler("finbra_longo.csv"):
        a, c, t, col, v = int(r["ano"]), r["cod_ibge"], r["tabela"], r["coluna"], float(r["valor"])
        d = lin[(c, a)]
        tab_desp = "RecDesp" if a in (2002, 2003) else "Despesa"
        tab_rec = "RecDesp" if a in (2002, 2003) else "Receita"
        if t == tab_desp and col == "Despesas Orçamentárias":
            d["despesa_empenhada"] = v
        elif t == tab_rec and col == "Rec Orçamentária":
            d["receita_orcamentaria"] = v
        elif t == tab_desp and col in ("Desp de Pessoal", "Pessoal e Encarg Soc_PES"):
            d["pessoal_empenhado"] = v
        elif a >= 2002 and t == TAB_FUNCAO.get(a, "DSubFuncao") and col in NOME_FINBRA:
            d["desp_" + NOME_FINBRA[col]] = v
        d["fonte_serie"] = f"FINBRA {a} (Tesouro Nacional; dados/brutos/finbra/_proveniencia.json)"

    # ---- SICONFI 2014+
    for r in ler("dca_despesa_funcao.csv"):
        if r["coluna"] != "Despesas Empenhadas" or r.get("secao") != "exceto_intra":
            continue
        d = lin[(r["cod_ibge"], int(r["ano"]))]
        if r["nivel"] == "total":
            d["despesa_empenhada"] = float(r["valor"])
        elif r["nivel"] == "funcao" and r["conta"][:2] in FUNCOES:
            d["desp_" + FUNCOES[r["conta"][:2]]] = float(r["valor"])
        d["fonte_serie"] = f"SICONFI DCA {r['ano']} (Tesouro Nacional, apidatalake)"
    bruta, deduz = defaultdict(float), defaultdict(float)
    for r in ler("dca_receita.csv"):
        if r["cod_conta"] != "TotalReceitas":
            continue
        k = (r["cod_ibge"], int(r["ano"]))
        if r["coluna"] == "Receitas Brutas Realizadas":
            bruta[k] += float(r["valor"])
        elif "Dedu" in r["coluna"]:
            deduz[k] += abs(float(r["valor"]))  # o sinal das deduções varia entre declarações; o que importa é o módulo
    for k, v in bruta.items():
        lin[k]["receita_orcamentaria"] = v - deduz.get(k, 0.0)
        lin[k]["receita_bruta"] = v
    for r in ler("rgf_pessoal.csv"):
        d = lin[(r["cod_ibge"], int(r["ano"]))]
        d["dtp_pct_rcl"] = r["dtp_pct_rcl"]
        d["rcl"] = r["rcl_ajustada"]
        d["situacao_pessoal_lrf"] = r["situacao"]

    # ---- montagem, derivados e checagens
    linhas = []
    for (c, a), d in sorted(lin.items(), key=lambda x: (muns.get(x[0][0], ""), x[0][1])):
        if c not in muns:
            continue
        de = d.get("despesa_empenhada")
        p = pop.get((c, a))
        out = {"cod_ibge": c, "municipio": muns[c], "ano": a, **{k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}}
        if de:
            for f in ("saude", "educacao"):
                if d.get("desp_" + f) is not None:
                    out[f"pct_{f}_desp"] = round(100 * d["desp_" + f] / de, 2)
            if p:
                out["despesa_per_capita"] = round(de / p, 2)
            soma_f = sum(d.get("desp_" + f, 0) for f in FUNCOES.values())
            if soma_f > de * 1.001:
                alertas.append(f"{muns[c]} {a}: soma de 8 funções (R$ {soma_f:,.2f}) maior que a despesa total (R$ {de:,.2f})")
        if p:
            out["populacao"] = int(p)
        linhas.append(out)
    # salto de despesa entre anos seguidos (mais de 3x ou menos de 1/3) = erro de declaração provável
    serie = defaultdict(list)
    for x in linhas:
        if x.get("despesa_empenhada"):
            serie[x["cod_ibge"]].append((x["ano"], x["despesa_empenhada"]))
    for c, s in serie.items():
        for (a0, v0), (a1, v1) in zip(s, s[1:]):
            if a1 == a0 + 1 and (v1 > 3 * v0 or v1 < v0 / 3):
                alertas.append(f"{muns[c]}: despesa empenhada R$ {v0:,.0f} ({a0}) → R$ {v1:,.0f} ({a1}); conferir a declaração")
    anos = sorted({x["ano"] for x in linhas})
    for a in anos:
        n = sum(1 for x in linhas if x["ano"] == a and x.get("despesa_empenhada"))
        checagens.append((n >= 50, f"{a}: {n} de 62 municípios com despesa empenhada"))
    fora = [x for x in linhas for f in ("saude", "educacao") if not 0 <= float(x.get(f"pct_{f}_desp", 0) or 0) <= 100]
    checagens.append((not fora, f"participação de saúde e educação entre 0% e 100%: {len(fora)} fora"))
    campos = ["cod_ibge", "municipio", "ano", "fonte_serie", "populacao", "receita_orcamentaria", "receita_bruta", "despesa_empenhada",
              "despesa_per_capita"] + [f"desp_{f}" for f in FUNCOES.values()] + ["pct_saude_desp", "pct_educacao_desp",
                                                                                   "pessoal_empenhado", "rcl", "dtp_pct_rcl", "situacao_pessoal_lrf"]
    with open(os.path.join(DADOS, "indicadores", "financas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "11_financas.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — finanças harmonizadas (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Linhas: {len(linhas)}; anos: {anos[0]}–{anos[-1]} (2013 sem fonte)\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Alertas para verificação humana\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} anos={anos[0]}-{anos[-1]} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
