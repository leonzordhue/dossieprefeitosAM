"""Quanto cada Câmara Municipal do AM gasta por ano: despesa empenhada da Câmara (MSC) e despesa com pessoal do Legislativo (RGF).

Fontes (API do SICONFI, Tesouro Nacional — https://apidatalake.tesouro.gov.br/ords/siconfi/tt/):
  - MSC (Matriz de Saldos Contábeis), msc_orcamentaria, matriz MSCC, classe 6, saldo final de dezembro (ending_balance):
    soma das contas 6.2.2.1.3.xx (crédito empenhado, em todos os estágios: a liquidar, liquidado, pago) por poder/órgão.
    poder_orgao 1xxxx = Executivo (Prefeitura e entidades), 2xxxx = Legislativo (Câmara). A MSC existe a partir de 2018.
  - RGF Anexo 1 do Poder Legislativo (co_poder=L): despesa total com pessoal da Câmara e % da RCL (LRF art. 20, III, a:
    limite de 6% para o Legislativo municipal). Quadrimestral (3º) ou semestral (2º, "RGF Simplificado").
Limite de gasto total da Câmara (CF art. 29-A) não é calculado: a base (receita tributária + transferências do ano
anterior) não está nessas fontes.
Conferência: Executivo (MSC) deve bater com a despesa empenhada da DCA (dados/indicadores/financas.csv) — mesma fonte,
outro demonstrativo.

Saídas: dados/indicadores/camaras_financas.csv, dados/integridade/22_camaras_financas.md
Uso: python -I scripts/22_camaras_financas.py   (~1 requisição/s; respostas em dados/brutos/cache_http)
"""
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANOS_MSC = range(2018, datetime.now().year)
ANOS_RGF = range(2014, datetime.now().year)


def consulta(caminho):
    itens, off = [], 0
    while True:
        url = API + caminho + (f"&offset={off}" if off else "")
        if not rede.em_cache(url):
            time.sleep(1)
        d = rede.get_json(url)
        itens += d.get("items", [])
        if not d.get("hasMore"):
            return itens, API + caminho
        off += len(d["items"])


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    fin = {(r["cod_ibge"], int(r["ano"])): r for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "financas.csv"), encoding="utf-8"))}
    linhas, checagens, alertas, confere, compara = [], [], [], 0, 0
    for m in muns:
        cod = m["cod_ibge"]
        for a in sorted(set(ANOS_MSC) | set(ANOS_RGF)):
            lin = {"cod_ibge": cod, "municipio": m["municipio"], "ano": a, "camara_empenhado": "", "executivo_empenhado": "",
                   "camara_pessoal": "", "camara_pessoal_pct_rcl": "", "fonte_msc": "", "fonte_rgf": ""}
            if a in ANOS_MSC:
                itens, url = consulta(f"msc_orcamentaria?id_ente={cod}&an_referencia={a}&me_referencia=12&co_tipo_matriz=MSCC&classe_conta=6&id_tv=ending_balance")
                emp = defaultdict(float)
                for x in itens:
                    if str(x["conta_contabil"]).startswith("6221") and str(x["conta_contabil"])[:5] == "62213":
                        emp[str(x["poder_orgao"])[0]] += x["valor"] or 0
                if itens:
                    lin.update(camara_empenhado=round(emp["2"], 2), executivo_empenhado=round(emp["1"], 2), fonte_msc=url)
                    dca = fin.get((cod, a), {}).get("despesa_empenhada")
                    if dca and emp["1"]:
                        compara += 1
                        d = abs(emp["1"] - float(dca)) / float(dca)
                        confere += d <= 0.03
                        if d > 0.03:
                            alertas.append(f"{a} {m['municipio']}: Executivo na MSC R$ {emp['1']:,.0f} ≠ DCA R$ {float(dca):,.0f} ({100 * d:.1f}%)")
            if a in ANOS_RGF:
                for per, tipo, dem in ((3, "Q", "RGF"), (2, "S", "RGF%20Simplificado"), (2, "S", "RGF"), (3, "Q", "RGF%20Simplificado")):
                    itens, url = consulta(f"rgf?an_exercicio={a}&in_periodicidade={tipo}&nr_periodo={per}&co_tipo_demonstrativo={dem}&co_poder=L&id_ente={cod}")
                    a1 = [x for x in itens if x["anexo"] == "RGF-Anexo 01"]
                    if a1:
                        break
                v = lambda cc, pct: next((x["valor"] for x in a1 if x["cod_conta"] == cc and ("%" in x["coluna"]) == pct), None)  # noqa: E731
                if a1 and v("DespesaComPessoalTotal", False) is not None:
                    lin.update(camara_pessoal=v("DespesaComPessoalTotal", False), camara_pessoal_pct_rcl=v("DespesaComPessoalTotal", True) or "", fonte_rgf=url)
                    pct = v("DespesaComPessoalTotal", True)
                    if pct and pct > 6:
                        alertas.append(f"{a} {m['municipio']}: pessoal da Câmara {pct}% da RCL, acima do limite de 6% (LRF art. 20, III, a)")
            if lin["fonte_msc"] or lin["fonte_rgf"]:
                linhas.append(lin)
        print(m["municipio"], flush=True)
    checagens.append((compara and confere >= 0.9 * compara, f"Executivo na MSC = despesa empenhada da DCA (±3%): {confere} de {compara} município-anos"))
    for a in ANOS_MSC:
        n = sum(1 for x in linhas if x["ano"] == a and x["camara_empenhado"] not in ("", 0, 0.0))
        checagens.append((n >= 50, f"{a}: {n} de 62 Câmaras com despesa na MSC"))
    n_rgf = sum(1 for x in linhas if x["camara_pessoal"] != "")
    checagens.append((n_rgf >= 0.6 * 62 * len(ANOS_RGF), f"RGF do Legislativo: {n_rgf} de {62 * len(ANOS_RGF)} Câmara-anos"))
    with open(os.path.join(DADOS, "indicadores", "camaras_financas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "22_camaras_financas.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — finanças das Câmaras (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas[:200]) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
