"""Mínimos legais da educação nas prefeituras do AM, declarados ao SIOPE (FNDE), por ano.

Fonte: API de dados abertos do SIOPE (OData, FNDE) — https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_SIOPE/versao/v1/odata/
       função Indicadores_Siope(Ano_Consulta, Num_Peri=6 [6º bimestre = ano fechado], Sig_UF='AM').
Indicadores usados (código de exibição do SIOPE):
  1.1  % das receitas de impostos e transferências aplicado em MDE — mínimo 25% (CF art. 212)
  1.2  % do FUNDEB na remuneração dos profissionais da educação — mínimo 60% até 2020 (Lei 11.494/2007, art. 22)
       e 70% a partir de 2021 (Lei 14.113/2020, art. 26)
  2.8  % das despesas em educação sobre as despesas de todas as áreas
EC 119/2022: quem não aplicou o mínimo de MDE em 2020 e 2021 (pandemia) não é responsabilizado, mas deve complementar a
diferença até 2023 (ADCT art. 119). A coluna observacao marca esses anos.
É o que o município declarou; a verificação oficial é do TCE-AM. O código do município no SIOPE tem 6 dígitos (IBGE sem o
dígito verificador); a ligação ao código de 7 dígitos é feita pelos 6 primeiros.

Saídas: dados/indicadores/siope.csv (cod_ibge, ano, indicador, valor, minimo, cumpriu, fonte), dados/integridade/12_siope.md
Uso: python -I scripts/12_siope.py
"""
import csv
import os
import sys
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
API = ("https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_SIOPE/versao/v1/odata/"
       "Indicadores_Siope(Ano_Consulta=@Ano_Consulta,Num_Peri=@Num_Peri,Sig_UF=@Sig_UF)"
       "?@Ano_Consulta={a}&@Num_Peri=6&@Sig_UF='AM'&$format=json&$filter=" + quote("TIPO eq 'Municipal'"))
ANOS = range(2006, datetime.now().year)
INDIC = {"1.1": ("mde_pct", lambda a: 25.0), "1.2": ("fundeb_remuneracao_pct", lambda a: 70.0 if a >= 2021 else 60.0),
         "2.8": ("educacao_pct_despesa_total", lambda a: None)}


def main():
    nomes = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    muns = {m["cod_ibge"][:6]: m["cod_ibge"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, alertas, linhas = [], [], []
    for a in ANOS:
        url = API.format(a=a)
        try:
            v = rede.get_json(url)["value"]
        except Exception as e:  # ano sem publicação na API
            checagens.append((False, f"{a}: falha ao consultar ({e.__class__.__name__})"))
            continue
        vistos = set()
        for x in v:
            cod = muns.get(str(x["COD_MUNI"]))
            if x["COD_EXIB"] not in INDIC:
                continue
            if not cod:
                alertas.append(f"{a}: município SIOPE {x['COD_MUNI']} {x['NOM_MUNI']} sem par no IBGE")
                continue
            nome, minimo = INDIC[x["COD_EXIB"]]
            try:
                val = float(str(x["VAL_INDI"]).replace(",", "."))
            except ValueError:
                continue
            mi = minimo(a)
            vistos.add(cod)
            linhas.append({"cod_ibge": cod, "ano": a, "indicador": nome, "valor": val, "minimo": mi if mi is not None else "",
                           "cumpriu": ("" if mi is None else "sim" if val >= mi else "não"),
                           "observacao": "EC 119/2022: sem responsabilização em 2020-2021; complementar até 2023"
                           if nome == "mde_pct" and a in (2020, 2021) and mi is not None and val < mi else "",
                           "descricao": x["NOM_INDI"].strip(), "fonte": f"SIOPE/FNDE {url}"})
        if v:
            checagens.append((len(vistos) >= 50, f"{a}: {len(vistos)} de 62 municípios com indicadores no SIOPE"))
    zeros = [x for x in linhas if x["indicador"] == "mde_pct" and x["valor"] == 0]
    for x in zeros:
        alertas.append(f"{x['ano']} {x['cod_ibge']}: MDE declarado 0% — provável declaração incompleta, não aplicação zero")
    with open(os.path.join(DADOS, "indicadores", "siope.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "ano", "indicador", "valor", "minimo", "cumpriu", "observacao", "descricao", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    abaixo = [x for x in linhas if x["cumpriu"] == "não" and x["valor"] > 0]
    with open(os.path.join(DADOS, "integridade", "12_siope.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — SIOPE (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + f"\n\n## Declarações abaixo do mínimo ({len(abaixo)})\n\nValor declarado pelo município; a apuração oficial é do TCE-AM.\n\n"
                + "\n".join(f"- {x['ano']} {nomes[x['cod_ibge']]} {x['indicador']}: {x['valor']}% (mínimo {x['minimo']}%)"
                            + (f" — {x['observacao']}" if x["observacao"] else "") for x in abaixo)
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} abaixo={len(abaixo)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
