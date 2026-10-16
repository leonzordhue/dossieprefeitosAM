"""IDHM dos 62 municípios do AM (Atlas do Desenvolvimento Humano no Brasil — PNUD, Ipea e FJP), censos 1991, 2000 e 2010.

Fonte: API OData do Ipeadata — http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='<série>')
  ADH_IDHM (geral), ADH_IDHM_E (educação), ADH_IDHM_L (longevidade), ADH_IDHM_R (renda).
O Atlas recalculou 1991 e 2000 pela metodologia de 2010 e harmonizou as fronteiras municipais, então os 3 anos são
comparáveis. O IDHM com o Censo 2022 ainda não foi publicado por município (conferido em 16/10/2026).
Faixas do Atlas: muito baixo < 0,500; baixo < 0,600; médio < 0,700; alto < 0,800; muito alto ≥ 0,800.

Saídas: dados/indicadores/idhm.csv (cod_ibge, ano, idhm, idhm_educacao, idhm_longevidade, idhm_renda, faixa, fonte),
        dados/integridade/15_idhm.md
Uso: python -I scripts/15_idhm.py
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
API = "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{s}')"
SERIES = {"ADH_IDHM": "idhm", "ADH_IDHM_E": "idhm_educacao", "ADH_IDHM_L": "idhm_longevidade", "ADH_IDHM_R": "idhm_renda"}
ANOS = (1991, 2000, 2010)


def faixa(v):
    return "muito baixo" if v < 0.5 else "baixo" if v < 0.6 else "médio" if v < 0.7 else "alto" if v < 0.8 else "muito alto"


def main():
    muns = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    tab = {}
    for s, col in SERIES.items():
        for x in rede.get_json(API.format(s=s))["value"]:
            cod = str(x.get("TERCODIGO", ""))
            if cod in muns and x["VALVALOR"] is not None:
                tab.setdefault((cod, int(x["VALDATA"][:4])), {})[col] = x["VALVALOR"]
    linhas = [{"cod_ibge": c, "ano": a, **v, "faixa": faixa(v["idhm"]) if "idhm" in v else "",
               "fonte": "Atlas do Desenvolvimento Humano (PNUD/Ipea/FJP) via Ipeadata, séries " + ", ".join(SERIES)}
              for (c, a), v in sorted(tab.items())]
    checagens = []
    for a in ANOS:
        n = sum(1 for x in linhas if x["ano"] == a and all(k in x for k in SERIES.values()))
        checagens.append((n == 62, f"{a}: {n} de 62 municípios com as 4 séries"))
    fora = [x for x in linhas if not all(0 < x.get(k, 0.5) < 1 for k in SERIES.values())]
    checagens.append((not fora, f"valores fora de (0, 1): {len(fora)}"))
    # o IDHM é a média geométrica das 3 dimensões (metodologia do Atlas); confere com tolerância de arredondamento
    dif = [x for x in linhas if all(k in x for k in SERIES.values())
           and abs((x["idhm_educacao"] * x["idhm_longevidade"] * x["idhm_renda"]) ** (1 / 3) - x["idhm"]) > 0.002]
    checagens.append((not dif, f"IDHM = média geométrica das 3 dimensões (tolerância 0,002): {len(dif)} divergências"))
    with open(os.path.join(DADOS, "indicadores", "idhm.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "ano", *SERIES.values(), "faixa", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "15_idhm.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — IDHM (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Divergências da média geométrica\n\n"
                + ("\n".join(f"- {x['ano']} {muns[x['cod_ibge']]}: {x['idhm']}" for x in dif) or "- nenhuma") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
