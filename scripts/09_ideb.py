"""IDEB dos municípios do AM (INEP), anos iniciais e finais do ensino fundamental, 2005-2023, por rede.

Fonte: INEP, https://download.inep.gov.br/ideb/resultados/divulgacao_<etapa>_municipios_2023.zip (série completa 2005-2023
e metas 2007-2021). IDEB = rendimento (aprovação) × nota padronizada do SAEB (Decreto 6.094/2007, art. 3º).
A rede "Municipal" é a que responde ao prefeito; "Estadual" é do governo do estado; "Pública" soma as duas.
O md5 publicado pelo INEP dentro do zip é conferido.

Saídas: dados/indicadores/ideb.csv (cod_ibge, etapa, rede, ano, ideb, meta, nota_saeb, rendimento, fonte),
        dados/integridade/09_ideb.md
Uso: python -I scripts/09_ideb.py
"""
import csv
import hashlib
import io
import os
import sys
import zipfile
from datetime import datetime

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
BRUTOS = os.path.join(DADOS, "brutos", "inep")
URL = "https://download.inep.gov.br/ideb/resultados/divulgacao_{e}_municipios_2023.zip"
ETAPAS = {"anos_iniciais": "anos iniciais (1º ao 5º)", "anos_finais": "anos finais (6º ao 9º)"}
ANOS = range(2005, 2024, 2)


def num(v):
    if v in (None, "", "-", "--", "ND", "*"):
        return ""
    return float(str(v).replace(",", ".")) if not isinstance(v, (int, float)) else float(v)


def main():
    os.makedirs(BRUTOS, exist_ok=True)
    os.makedirs(os.path.join(DADOS, "indicadores"), exist_ok=True)
    muns = {m["cod_ibge"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, linhas = [], []
    for e, rot in ETAPAS.items():
        url = URL.format(e=e)
        arq = os.path.join(BRUTOS, f"{e}_2023.zip")
        if not os.path.exists(arq):
            open(arq, "wb").write(rede.get(url, cache=False))
        z = zipfile.ZipFile(arq)
        xl = next(n for n in z.namelist() if n.endswith(".xlsx"))
        bruto = z.read(xl)
        md5txt = z.read(next(n for n in z.namelist() if "md5" in n)).decode("latin1")
        checagens.append((hashlib.md5(bruto).hexdigest() in md5txt.lower(), f"{rot}: md5 do .xlsx confere com o publicado pelo INEP"))
        ws = openpyxl.load_workbook(io.BytesIO(bruto), read_only=True).worksheets[0]
        cab, vistos = None, set()
        for r in ws.iter_rows(values_only=True):
            if r and r[0] == "SG_UF":
                cab = {n: i for i, n in enumerate(r)}
                continue
            if not cab or not r or r[0] != "AM":
                continue
            cod = str(r[cab["CO_MUNICIPIO"]])
            vistos.add(cod)
            for a in ANOS:
                ideb = num(r[cab[f"VL_OBSERVADO_{a}"]])
                meta = num(r[cab[f"VL_PROJECAO_{a}"]]) if f"VL_PROJECAO_{a}" in cab else ""
                if ideb == "" and meta == "":
                    continue
                linhas.append({"cod_ibge": cod, "municipio": r[cab["NO_MUNICIPIO"]], "etapa": rot, "rede": r[cab["REDE"]], "ano": a,
                               "ideb": ideb, "meta": meta, "nota_saeb": num(r[cab[f"VL_NOTA_MEDIA_{a}"]]),
                               "rendimento": num(r[cab[f"VL_INDICADOR_REND_{a}"]]),
                               "fonte": f"INEP {url} (VL_OBSERVADO_{a})"})
        checagens.append((vistos <= muns and len(vistos) == 62, f"{rot}: {len(vistos)} municípios do AM na planilha, todos com código IBGE válido"))
    # coerência: IDEB = rendimento × nota (com arredondamento de 1 casa)
    ruins = [x for x in linhas if x["ideb"] != "" and x["rendimento"] != "" and x["nota_saeb"] != ""
             and abs(x["rendimento"] * x["nota_saeb"] - x["ideb"]) > 0.06]
    checagens.append((not ruins, f"IDEB = rendimento × nota SAEB (tolerância 0,06): {len(ruins)} divergências em "
                                 f"{sum(1 for x in linhas if x['ideb'] != '')} valores"))
    with open(os.path.join(DADOS, "indicadores", "ideb.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "09_ideb.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — IDEB (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Divergências\n\n"
                + ("\n".join(f"- {x['municipio']} {x['etapa']} {x['rede']} {x['ano']}: {x['rendimento']} × {x['nota_saeb']} ≠ {x['ideb']}"
                             for x in ruins[:100]) or "- nenhuma") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} divergencias={len(ruins)}")


if __name__ == "__main__":
    main()
