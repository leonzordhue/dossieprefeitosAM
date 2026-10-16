"""Quanto cada prefeito do AM arrecadou e gastou na sua gestão: soma, por mandato, da série financeira anual (11_financas.py).

Regra de atribuição: cada ano vai para o prefeito que governou a maior parte dele (≥ 183 dias, pelas datas de dados/mandatos.csv).
Ano sem dado na fonte (2013 em todos; anos não declarados pela prefeitura) fica listado em anos_sem_dado e NÃO é estimado:
o total da gestão é a soma dos anos com dado, e a cobertura vai junto.
Correção monetária: IPCA (IBGE, SIDRA tabela 1737, variável 2266 = número-índice), média dos 12 meses de cada ano;
valores reais em R$ do último ano completo da série do IPCA. Despesa = empenhada (Lei 4.320/1964); receita = orçamentária.
Interinos e mandatos-tampão que o TSE não registra ficam sem atribuição (o ano vai para quem o TSE mostra).

Saídas: dados/indicadores/gestoes.csv, dados/integridade/21_gestoes.md
Uso: python -I scripts/21_gestoes.py
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2266/p/all"
CAMPOS = ("receita_orcamentaria", "despesa_empenhada", "desp_saude", "desp_educacao", "desp_administracao", "desp_urbanismo",
          "desp_assistencia", "desp_saneamento", "desp_transporte", "desp_legislativa")


def num(v):
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def main():
    # IPCA: média anual do número-índice
    meses = defaultdict(list)
    for r in rede.get_json(IPCA)[1:]:
        if num(r.get("V")) is not None:
            meses[int(r["D3C"][:4])].append(float(r["V"]))
    media = {a: sum(v) / len(v) for a, v in meses.items() if len(v) == 12}
    ref = max(media)
    fin = {(r["cod_ibge"], int(r["ano"])): r for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "financas.csv"), encoding="utf-8"))}
    mand = [m for m in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")) if m["inicio"] and m["fim_previsto"]]
    dono = {}  # (cod, ano) -> mandato
    for m in mand:
        ini, fim = date.fromisoformat(m["inicio"]), date.fromisoformat(m["fim_previsto"])
        for a in range(ini.year, fim.year + 1):
            dias = (min(fim, date(a, 12, 31)) - max(ini, date(a, 1, 1))).days + 1
            if dias >= 183:
                dono[(m["cod_ibge"], a)] = m
    linhas, checagens = [], []
    soma_anos = defaultdict(float)
    for m in mand:
        anos = sorted(a for (c, a), mm in dono.items() if mm is m)
        if not anos:
            continue
        com = [a for a in anos if (m["cod_ibge"], a) in fin and num(fin[(m["cod_ibge"], a)]["despesa_empenhada"]) is not None]
        sem = [a for a in anos if a not in com and a < datetime.now().year]  # ano corrente e futuros: gestão em curso, não lacuna
        tot = {c: 0.0 for c in CAMPOS}
        real = {c: 0.0 for c in CAMPOS}
        pop, dtp = [], []
        for a in com:
            r = fin[(m["cod_ibge"], a)]
            f = media[ref] / media[a] if a in media else None
            for c in CAMPOS:
                v = num(r[c])
                if v is not None:
                    tot[c] += v
                    if f:
                        real[c] += v * f
            soma_anos[m["cod_ibge"]] += num(r["despesa_empenhada"])
            if num(r["populacao"]):
                pop.append(num(r["populacao"]))
            if num(r["dtp_pct_rcl"]) is not None:
                dtp.append(num(r["dtp_pct_rcl"]))
        linhas.append({"cod_ibge": m["cod_ibge"], "municipio": m["municipio"], "ciclo": m["ciclo"], "pessoa_id": m["pessoa_id"], "prefeito": m["prefeito"],
                       "inicio": m["inicio"], "fim": m["fim_previsto"], "anos_atribuidos": " ".join(map(str, anos)), "anos_sem_dado": " ".join(map(str, sem)), "em_curso": "sim" if m["fim_previsto"] >= date.today().isoformat() else "",
                       **{f"{c}_nominal": round(tot[c], 2) for c in CAMPOS}, **{f"{c}_real": round(real[c], 2) for c in CAMPOS},
                       "despesa_real_por_habitante_ano": round(real["despesa_empenhada"] / (sum(pop) / len(pop)) / len(com), 2) if pop and com else "",
                       "pessoal_pct_rcl_medio": round(sum(dtp) / len(dtp), 2) if dtp else "", "ipca_referencia": ref,
                       "fonte": "dados/indicadores/financas.csv (FINBRA 2000-2012, SICONFI 2014+) + IPCA IBGE/SIDRA 1737"})
    # integridade: cada ano com dado foi atribuído a exatamente um mandato e a soma por município fecha com a série
    tot_serie = defaultdict(float)
    for (c, a), r in fin.items():
        if (c, a) in dono and num(r["despesa_empenhada"]) is not None:
            tot_serie[c] += num(r["despesa_empenhada"])
    dif = [c for c in tot_serie if abs(tot_serie[c] - soma_anos[c]) > 1]
    checagens.append((not dif, f"soma das gestões = soma dos anos atribuídos, por município: {len(tot_serie) - len(dif)} de {len(tot_serie)} conferem"))
    sem_dono = sorted({a for (c, a), r in fin.items() if (c, a) not in dono and num(r["despesa_empenhada"]) is not None})
    checagens.append((len(sem_dono) <= 5, f"anos com dado financeiro sem prefeito atribuído (lacuna de mandato no TSE): {len(sem_dono)} anos distintos"))
    checagens.append((ref >= datetime.now().year - 1, f"IPCA de referência: média de {ref}"))
    with open(os.path.join(DADOS, "indicadores", "gestoes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "21_gestoes.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — gasto por gestão (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Gestões: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n")
    print(f"gestoes={len(linhas)} checagens={ok}/{len(checagens)} ref={ref}")


if __name__ == "__main__":
    main()
