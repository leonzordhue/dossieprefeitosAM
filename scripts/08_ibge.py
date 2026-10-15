"""População e PIB dos 62 municípios do AM (IBGE, API do SIDRA: https://apisidra.ibge.gov.br).

Tabelas:
  - 202  Censo, população residente (usa 2000 e 2010)
  - 793  Contagem da População 2007 (população residente)
  - 4709 Censo 2022, população residente
  - 6579 Estimativas de população (TCU, art. 102 da Lei 8.443/1992), 2001 em diante, exceto anos de censo/contagem
  - 5938 PIB dos municípios a preços correntes (variável 37, mil R$), 2002 em diante
Censo/contagem prevalecem sobre estimativa no mesmo ano. Ano sem dado fica vazio (lacuna), nunca interpolado.

Saídas: dados/indicadores/ibge.csv (cod_ibge, ano, populacao, populacao_fonte, pib_mil_reais, pib_per_capita, fonte_pib),
        dados/integridade/08_ibge.md
Uso: python -I scripts/08_ibge.py
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
SAIDA = os.path.join(DADOS, "indicadores")
API = "https://apisidra.ibge.gov.br/values/t/{t}/n6/in%20n3%2013/v/{v}/p/{p}"
# (tabela, variável, períodos, rótulo da fonte); a ordem define a prioridade (o primeiro que tiver o ano vence)
POP = (("202", "93", "2000,2010", "IBGE Censo (tabela 202)"),
       ("793", "93", "2007", "IBGE Contagem da População 2007 (tabela 793)"),
       ("4709", "93", "2022", "IBGE Censo 2022 (tabela 4709)"),
       ("6579", "9324", "all", "IBGE Estimativa da população (tabela 6579)"))


def serie(t, v, p):
    url = API.format(t=t, v=v, p=p)
    d = rede.get_json(url)
    cab = d[0]
    # a coluna do município e a do ano mudam de posição (D1/D2/D3) entre tabelas: acha pelo nome do cabeçalho
    cm = next(k[:2] + "C" for k, n in cab.items() if k.endswith("N") and n.startswith("Município"))
    ca = next(k[:2] + "N" for k, n in cab.items() if k.endswith("N") and n == "Ano")
    out = {}
    for x in d[1:]:
        if x["V"] not in ("", "-", "...", "X"):
            out[(x[cm], int(x[ca]))] = float(x["V"])
    return out, url


def main():
    os.makedirs(SAIDA, exist_ok=True)
    muns = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, alertas = [], []
    pop = {}
    for t, v, p, rot in POP:
        s, url = serie(t, v, p)
        checagens.append((len({c for c, _ in s}) == 62, f"{rot}: {len(s)} valores, {len({c for c, _ in s})} municípios ({url})"))
        for k, val in s.items():
            pop.setdefault(k, (int(val), rot))
    pib, url_pib = serie("5938", "37", "all")
    checagens.append((len({c for c, _ in pib}) == 62, f"PIB (tabela 5938): {len(pib)} valores ({url_pib})"))
    anos = sorted({a for _, a in pop} | {a for _, a in pib})
    linhas = []
    for c in sorted(muns):
        for a in anos:
            pp, pf = pop.get((c, a), ("", ""))
            pb = pib.get((c, a), "")
            linhas.append({"cod_ibge": c, "municipio": muns[c], "ano": a, "populacao": pp, "populacao_fonte": pf,
                           "pib_mil_reais": pb, "pib_per_capita": round(1000 * pb / pp, 2) if pb != "" and pp else "",
                           "fonte_pib": "IBGE PIB dos Municípios (tabela 5938, v37)" if pb != "" else ""})
    # coerência: população não pode saltar mais de 40% de um ano para o outro sem revisão de censo
    for c in muns:
        serie_c = [(a, pop[(c, a)][0]) for a in anos if (c, a) in pop]
        for (a0, p0), (a1, p1) in zip(serie_c, serie_c[1:]):
            if p0 and abs(p1 - p0) / p0 > 0.4:
                alertas.append(f"{muns[c]}: população {p0} ({a0}) → {p1} ({a1}), variação de {100 * (p1 - p0) / p0:+.0f}%")
    soma_am = sum(pop[(c, 2022)][0] for c in muns if (c, 2022) in pop)
    checagens.append((3_900_000 < soma_am < 4_000_000, f"soma da população do Censo 2022 nos 62 municípios = {soma_am} (AM: 3.941.613)"))
    with open(os.path.join(SAIDA, "ibge.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    falta = [a for a in anos if sum(1 for c in muns if (c, a) in pop) < 62]
    with open(os.path.join(DADOS, "integridade", "08_ibge.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — IBGE (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n")
        f.write(f"- Anos sem população para todos os municípios: {falta or 'nenhum'}\n\n## Alertas\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} alertas={len(alertas)} anos_falta={falta}")


if __name__ == "__main__":
    main()
