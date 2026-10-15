"""Finanças das prefeituras do AM pelo SICONFI (Tesouro Nacional), exercícios 2014-2025.

Fonte: API do SICONFI — https://apidatalake.tesouro.gov.br/ords/siconfi/tt/ (documentação em
       https://apidatalake.tesouro.gov.br/docs/siconfi/). Respostas guardadas em dados/brutos/cache_http.
  - DCA Anexo I-E: despesa orçamentária por função (empenhada, liquidada, paga) — Lei 4.320/1964 e Portaria 42/1999
  - DCA Anexo I-C: receita orçamentária por natureza
  - RGF Anexo 01 (Poder Executivo, último período do ano): despesa total com pessoal (DTP) e % da RCL — LRF art. 19, 20 e 55
    Limite do Executivo municipal: 54% da RCL (LRF art. 20, III, b); prudencial 95% (51,3%); alerta 90% (48,6%).
A DCA só existe na API a partir do exercício 2014 (2013 vem vazio, conferido em 15/10/2026); 2000-2013 virá do FINBRA.

Saídas (dados/financas/): dca_despesa_funcao.csv, dca_receita.csv, rgf_pessoal.csv; integridade em dados/integridade/03_siconfi.md
Uso: python -I scripts/03_siconfi.py   (~1 requisição/s; o cache faz a segunda rodada ser instantânea)
"""
import csv
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(BASE_DIR, "dados", "financas")
API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANOS = range(2014, 2026)


def consulta(caminho):
    """Todos os itens de uma consulta (a API pagina com hasMore/offset)."""
    itens, offset = [], 0
    while True:
        url = API + caminho + (f"&offset={offset}" if offset else "")
        if not rede.em_cache(url):
            time.sleep(1)  # pedido do Tesouro: no máximo 1 requisição por segundo
        d = rede.get_json(url)
        itens += d.get("items", [])
        if not d.get("hasMore"):
            return itens, url
        offset += len(d["items"])


def nivel(conta):
    """Na DCA I-E a função vem no texto da conta: "10 - Saúde" (função), "10.301 - Atenção Básica" (subfunção),
    "FU10 - Demais Subfunções"; o resto é linha de total."""
    c = conta.strip()
    if re.match(r"^\d{2} - ", c):
        return "funcao"
    if re.match(r"^(\d{2}\.\d{3}|FU\d{2}) - ", c):
        return "subfuncao"
    return "total"


def gravar(nome, linhas, campos):
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def main():
    os.makedirs(SAIDA, exist_ok=True)
    muns = list(csv.DictReader(open(os.path.join(BASE_DIR, "dados", "municipios.csv"), encoding="utf-8")))
    assert len(muns) == 62, "rode 02_mandatos.py antes"
    desp, rec, pes = [], [], []
    falta = defaultdict(list)  # (conjunto) -> [(ano, município)]
    checagens, alertas = [], []
    for ano in ANOS:
        for m in muns:
            cod, nome = m["cod_ibge"], m["municipio"]
            base = {"ano": ano, "cod_ibge": cod, "municipio": nome}
            for anexo, destino in (("DCA-Anexo I-E", desp), ("DCA-Anexo I-C", rec)):
                itens, url = consulta(f"dca?an_exercicio={ano}&id_ente={cod}&no_anexo={quote(anexo)}")
                if not itens:
                    falta[anexo].append((ano, nome))
                for x in itens:
                    destino.append({**base, "instituicao": x["instituicao"], "coluna": x["coluna"], "cod_conta": x["cod_conta"],
                                    "conta": x["conta"], "nivel": nivel(x["conta"]) if anexo.endswith("I-E") else "",
                                    "valor": x["valor"], "populacao": x.get("populacao", ""), "fonte": url})
            # RGF do Executivo: quadrimestral (3º quadrimestre) ou semestral (2º semestre), conforme a opção do município (LRF art. 63)
            for per, tipo in ((3, "Q"), (2, "S")):
                itens, url = consulta(f"rgf?an_exercicio={ano}&in_periodicidade={tipo}&nr_periodo={per}"
                                      f"&co_tipo_demonstrativo=RGF&co_poder=E&id_ente={cod}")
                a1 = [x for x in itens if x["anexo"] == "RGF-Anexo 01"]
                if a1:
                    break
            if not a1:
                falta["RGF-Anexo 01"].append((ano, nome))
                continue
            v = lambda cc, pct: next((x["valor"] for x in a1 if x["cod_conta"] == cc and ("%" in x["coluna"]) == pct), None)  # noqa: E731
            dtp, dtp_pct = v("DespesaComPessoalTotal", False), v("DespesaComPessoalTotal", True)
            rcl = v("ReceitaCorrenteLiquidaLimiteLegal", False) or v("ReceitaCorrenteLiquida", False)
            lim = v("LimiteMaximoDespesaComPessoalTotal", True)
            pes.append({**base, "periodicidade": tipo, "periodo": per, "rcl_ajustada": rcl, "dtp": dtp, "dtp_pct_rcl": dtp_pct,
                        "limite_max_pct": lim, "situacao": ("" if dtp_pct is None else "acima do limite (54%)" if dtp_pct > 54
                                                            else "acima do prudencial (51,3%)" if dtp_pct > 51.3
                                                            else "acima do alerta (48,6%)" if dtp_pct > 48.6 else "dentro"),
                        "fonte": url})
            if dtp and rcl and dtp_pct is not None and abs(100 * dtp / rcl - dtp_pct) > 0.5:
                alertas.append(f"{ano} {nome}: DTP/RCL calculado {100 * dtp / rcl:.2f}% ≠ informado {dtp_pct}% (RCL ajustada difere?)")
        print(ano, "ok", flush=True)

    # integridade: soma das funções = total geral, por município/ano/coluna
    tot, soma = {}, defaultdict(float)
    for d in desp:
        k = (d["ano"], d["cod_ibge"], d["coluna"])
        if d["nivel"] == "total" and d["conta"].startswith("Despesas Exceto Intra"):
            tot[k] = d["valor"]
        elif d["nivel"] == "funcao":
            soma[k] += d["valor"]
    dif = [(k, tot[k], soma[k]) for k in tot if k in soma and abs(tot[k] - soma[k]) > 1.0]
    checagens.append((not dif, f"soma das funções = total geral da despesa (tolerância R$ 1): {len(tot) - len(dif)} de {len(tot)} conferem"))
    for (a, c, col), t, s in dif[:50]:
        alertas.append(f"{a} {c} {col}: total {t:,.2f} ≠ soma das funções {s:,.2f}")
    esperado = 62 * len(ANOS)
    for conj in ("DCA-Anexo I-E", "DCA-Anexo I-C", "RGF-Anexo 01"):
        n = esperado - len(falta[conj])
        checagens.append((n == esperado, f"{conj}: {n} de {esperado} município-anos com dados"))
    gravar("dca_despesa_funcao.csv", desp, list(desp[0].keys()))
    gravar("dca_receita.csv", rec, list(rec[0].keys()))
    gravar("rgf_pessoal.csv", pes, list(pes[0].keys()))
    with open(os.path.join(BASE_DIR, "dados", "integridade", "03_siconfi.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — SICONFI (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n")
        for conj, lst in falta.items():
            f.write(f"## Sem dados no SICONFI — {conj} ({len(lst)})\n\n" + ", ".join(f"{n} {a}" for a, n in lst) + "\n\n")
        f.write("## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"despesa={len(desp)} receita={len(rec)} pessoal={len(pes)} faltas={ {k: len(v) for k, v in falta.items()} } alertas={len(alertas)}")


if __name__ == "__main__":
    main()
