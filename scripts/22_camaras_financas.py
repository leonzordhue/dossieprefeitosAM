"""Quanto cada Câmara Municipal do AM gasta por ano: despesa empenhada da Câmara (MSC) e despesa com pessoal do Legislativo (RGF).

Fontes (API do SICONFI, Tesouro Nacional — https://apidatalake.tesouro.gov.br/ords/siconfi/tt/):
  - MSC (Matriz de Saldos Contábeis), msc_orcamentaria, matriz MSCC, classe 6, saldo final de dezembro (ending_balance):
    soma das contas 6.2.2.1.3.xx (crédito empenhado, em todos os estágios: a liquidar, liquidado, pago) por poder/órgão.
    poder_orgao 1xxxx = Executivo (Prefeitura e entidades), 2xxxx = Legislativo (Câmara). Para municípios do AM a API só
    tem MSC a partir de 2019 (2018 veio vazio para os 62).
    Muitos municípios mandam o saldo de dezembro sem acumular o ano (ex.: Anamã 2025: saldo de R$ 19 mi, DCA R$ 86 mi).
    Quando o saldo de dezembro não confere com a DCA, usa-se a soma dos movimentos dos 12 meses (period_change, C − D),
    que fechou no real em Anamã 2025 (83.261.256 + 2.688.774 = 85.950.030).
  - RGF Anexo 1 do Poder Legislativo (co_poder=L): despesa total com pessoal da Câmara e % da RCL (LRF art. 20, III, a:
    limite de 6% para o Legislativo municipal). Quadrimestral (3º) ou semestral (2º, "RGF Simplificado").
  - Despesa empenhada na função 01 – Legislativa (Portaria MOG 42/1999), de dados/indicadores/financas.csv (11_financas.py:
    FINBRA 2002–2012 e DCA-Anexo I-E 2014+). No município, a função Legislativa é a Câmara: cobre quase todos os anos e
    Câmaras, inclusive onde a MSC não separa o Legislativo. É a série principal (coluna legislativa_empenhado);
    a MSC fica como conferência. 2000–2001 usam a classificação antiga e 2013 não tem fonte (lacuna do FINBRA/DCA).
Limite de gasto total da Câmara (CF art. 29-A) não é calculado: a base (receita tributária + transferências do ano
anterior) não está nessas fontes.
Conferência: Executivo + Legislativo (MSC) deve bater (±3%) com a despesa empenhada da DCA (dados/indicadores/financas.csv),
que é consolidada e inclui a Câmara. Coluna msc_confere: "saldo dez" ou "soma mensal" (conferiu), "sem DCA" (sem como
conferir; publicado com aviso), "não" (não conferiu: o valor da Câmara NÃO é publicado e vira alerta).
Câmara sem lançamento próprio na MSC (poder_orgao 2 ausente ou zero) fica em branco, nunca R$ 0.
Empenhado da Câmara menor que o pessoal dela no RGF (impossível: a folha é parte do empenhado) também fica em branco.

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
ANOS_MSC = range(2019, datetime.now().year)
ANOS_RGF = range(2014, datetime.now().year)
ANOS_LEG = range(2002, datetime.now().year)


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


def msc(cod, a, tv):
    """Empenhado por poder ('1' Executivo, '2' Legislativo) no ano: saldo de dezembro ou soma dos 12 movimentos mensais."""
    emp, url = defaultdict(float), ""
    for me in ([12] if tv == "ending_balance" else range(1, 13)):
        itens, url = consulta(f"msc_orcamentaria?id_ente={cod}&an_referencia={a}&me_referencia={me}&co_tipo_matriz=MSCC&classe_conta=6&id_tv={tv}")
        for x in itens:
            if str(x["conta_contabil"])[:5] == "62213":
                sinal = 1 if tv == "ending_balance" or x["natureza_conta"] == "C" else -1
                emp[str(x["poder_orgao"])[0]] += sinal * (x["valor"] or 0)
        if tv == "ending_balance" and not itens:
            return None, url, ""
    return (emp if emp else None), url.replace("me_referencia=12", "me_referencia=1..12") if tv == "period_change" else url, "saldo dez"


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    fin = {(r["cod_ibge"], int(r["ano"])): r for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "financas.csv"), encoding="utf-8"))}
    linhas, checagens, alertas, confere, compara = [], [], [], 0, 0
    for m in muns:
        cod = m["cod_ibge"]
        for a in sorted(set(ANOS_MSC) | set(ANOS_RGF) | set(ANOS_LEG)):
            leg = fin.get((cod, a), {})
            lin = {"cod_ibge": cod, "municipio": m["municipio"], "ano": a,
                   "legislativa_empenhado": float(leg["desp_legislativa"]) if leg.get("desp_legislativa") else "",
                   "fonte_legislativa": ("" if not leg.get("desp_legislativa") else f"{API}dca?an_exercicio={a}&id_ente={cod}&no_anexo=DCA-Anexo%20I-E"
                                         if a >= 2014 else leg.get("fonte_serie", "")),
                   "camara_empenhado": "", "executivo_empenhado": "",
                   "camara_pessoal": "", "camara_pessoal_pct_rcl": "", "msc_confere": "", "fonte_msc": "", "fonte_rgf": ""}
            if a in ANOS_MSC:
                dca = fin.get((cod, a), {}).get("despesa_empenhada")
                dca = float(dca) if dca else None
                emp, url, modo = msc(cod, a, "ending_balance")
                if emp and dca and abs(emp["1"] + emp["2"] - dca) / dca > 0.03:
                    emp2, url2, _ = msc(cod, a, "period_change")
                    if emp2:
                        emp, url, modo = emp2, url2, "soma mensal"
                if emp:
                    tot = emp["1"] + emp["2"]
                    ok_ = dca is None or abs(tot - dca) / dca <= 0.03
                    lin.update(executivo_empenhado=round(emp["1"], 2), fonte_msc=url,
                               msc_confere=("sem DCA" if dca is None else modo if ok_ else "não"),
                               # Câmara = 0 na MSC é "não informada à parte" (o Executivo leva tudo), não gasto zero
                               camara_empenhado=round(emp["2"], 2) if ok_ and emp["2"] else "")
                    if dca:
                        compara += 1
                        confere += ok_
                        if not ok_:
                            alertas.append(f"{a} {m['municipio']}: MSC (Executivo + Câmara) R$ {tot:,.0f} ≠ DCA R$ {dca:,.0f} "
                                           f"({100 * abs(tot - dca) / dca:.1f}%); gasto da Câmara não publicado")
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
            # o empenhado da Câmara inclui a folha dela: se vier menor que o pessoal do RGF, a divisão Executivo/Câmara da MSC está errada
            if lin["camara_empenhado"] != "" and lin["camara_pessoal"] != "" and lin["camara_empenhado"] < 0.95 * lin["camara_pessoal"]:
                alertas.append(f"{a} {m['municipio']}: empenhado da Câmara na MSC R$ {lin['camara_empenhado']:,.0f} < pessoal no RGF "
                               f"R$ {lin['camara_pessoal']:,.0f}; gasto da Câmara não publicado")
                lin.update(camara_empenhado="", msc_confere="não (Câmara < pessoal)")
            if lin["legislativa_empenhado"] != "" and lin["camara_pessoal"] != "" and lin["legislativa_empenhado"] < 0.95 * lin["camara_pessoal"]:
                alertas.append(f"{a} {m['municipio']}: função Legislativa R$ {lin['legislativa_empenhado']:,.0f} < pessoal da Câmara no RGF "
                               f"R$ {lin['camara_pessoal']:,.0f}; despesa da Câmara não publicada")
                lin.update(legislativa_empenhado="", fonte_legislativa="")
            if lin["fonte_msc"] or lin["fonte_rgf"] or lin["fonte_legislativa"]:
                linhas.append(lin)
        print(m["municipio"], flush=True)
    # a MSC é conferência: só se publica o valor da Câmara onde Executivo + Câmara fecha com a DCA
    soltos = sum(1 for x in linhas if x["camara_empenhado"] not in ("", 0, 0.0) and x["msc_confere"] not in ("saldo dez", "soma mensal", "sem DCA"))
    checagens.append((soltos == 0, f"MSC publicada só onde confere com a DCA ({confere} de {compara} conferem; {soltos} publicados sem conferir)"))
    for a in ANOS_MSC:
        n = sum(1 for x in linhas if x["ano"] == a and (x["camara_empenhado"] not in ("", 0, 0.0) or x["legislativa_empenhado"] != ""))
        checagens.append((n >= 50, f"{a}: {n} de 62 Câmaras com despesa (função Legislativa ou MSC)"))
    for a in ANOS_LEG:
        n = sum(1 for x in linhas if x["ano"] == a and x["legislativa_empenhado"] != "")
        checagens.append((n >= 35 or a == 2013, f"{a}: {n} de 62 Câmaras com despesa na função Legislativa" + (" (2013: sem fonte)" if a == 2013 else "")))
    msc_leg = [(x["camara_empenhado"], x["legislativa_empenhado"]) for x in linhas if x["camara_empenhado"] not in ("", 0, 0.0) and x["legislativa_empenhado"] != ""]
    perto = sum(1 for c, l in msc_leg if abs(c - l) / l <= 0.15)
    checagens.append((perto >= 0.7 * len(msc_leg), f"Câmara na MSC × função Legislativa (±15%): {perto} de {len(msc_leg)} município-anos"))
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
