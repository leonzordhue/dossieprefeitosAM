"""Quem cada prefeitura do AM declarou como prefeito ao SIOPE (FNDE), comparado com o mandato do TSE: sinal de interinos,
afastamentos, cassações pela Câmara e sucessões que o TSE não registra.

Fonte: API de dados abertos do SIOPE (OData, FNDE), função Dados_Gerais_Siope_Dados_Responsaveis(Ano_Consulta, Num_Peri,
       Sig_UF='AM'), responsável do tipo P (prefeito). 2008-2016: uma declaração por ano (Num_Peri=1); 2017 em diante: por
       bimestre (1 a 6). Só nome e data da declaração são usados; e-mail, telefone e endereço do responsável não são lidos.
Leitura: o nome é quem estava como prefeito quando a declaração foi transmitida (DAT_DECL), não necessariamente no período
a que ela se refere (declaração atrasada costuma sair pelo sucessor). Por isso a comparação é feita com o mandato do TSE
vigente no fim do período e na data da declaração. "Outra pessoa" é sinal a investigar, não prova de quem governou.
Ligação a pessoa_id: só por nome (semelhança ≥ 0,85) entre os candidatos a prefeito, vice ou vereador do mesmo município;
nome que casa com mais de uma pessoa fica sem ligação.

Saídas: dados/prefeito_declarado.csv, dados/integridade/18_prefeito_declarado.md
Uso: python -I scripts/18_prefeito_declarado.py
"""
import calendar
import csv
import os
import re
import unicodedata
import sys
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

tce = import_module("17_tceam")  # mesmo_nome (semelhança de nomes)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
API = ("https://www.fnde.gov.br/olinda-ide/servico/DADOS_ABERTOS_SIOPE/versao/v1/odata/"
       "Dados_Gerais_Siope_Dados_Responsaveis(Ano_Consulta=@A,Num_Peri=@P,Sig_UF=@U)?@A={a}&@P={p}&@U='AM'&$format=json"
       "&$filter=TIP_RESP%20eq%20'P'&$select=COD_MUNI,NOM_MUNI,NOM_RESP,DAT_DECL")
ANOS = range(2008, datetime.now().year + 1)


PARTICULAS = {"DE", "DA", "DO", "DOS", "DAS", "E"}


def palavras(n):
    return [w for w in re.findall(r"[A-Z]+", unicodedata.normalize("NFKD", n or "").encode("ascii", "ignore").decode().upper())
            if w not in PARTICULAS]


def parecido(a, b):
    return a == b or (len(a) == 1 or len(b) == 1) and a[0] == b[0] or SequenceMatcher(None, a, b).ratio() >= 0.8


def mesmo(n1, n2):
    """Mesma pessoa a menos de grafia: cada palavra do nome mais curto (>= 2 palavras) casa com uma do mais longo
    (letra trocada, abreviação por inicial, ordem trocada, sobrenome omitido)."""
    if tce.mesmo_nome(n1, n2):
        return True
    a, b = sorted((palavras(n1), palavras(n2)), key=len)
    return len(a) >= 2 and all(any(parecido(x, y) for y in b) for x in a)


def quase(n1, n2):
    """Mesmo primeiro nome e mesmo último sobrenome, meio diferente: provável grafia, a conferir."""
    a, b = palavras(n1), palavras(n2)
    return bool(a and b) and a[0] == b[0] and parecido(a[-1], b[-1])


def fim_periodo(a, p, anual):
    if anual:
        return date(a, 12, 31)
    m = 2 * p
    return date(a, m, calendar.monthrange(a, m)[1])


def data_decl(v):
    s = str(v or "")
    try:
        return date.fromisoformat(s[:10]) if s[4:5] == "-" else datetime.strptime(s[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def responsaveis(a, p, muns):
    """Prefeitos declarados no período. Se a consulta do estado inteiro falhar (a partir de 2024 a API devolve JSON cortado ou
    erro 500 quando um registro está ruim), consulta município a município com $filter, para um registro ruim não derrubar os outros."""
    try:
        return rede.get_json(API.format(a=a, p=p), tentativas=1 if a >= 2024 else 5)["value"], []
    except Exception:
        pass
    v, falhas = [], []
    for c in muns:
        u = API.format(a=a, p=p).replace("$filter=TIP_RESP%20eq%20'P'", f"$filter=COD_MUNI%20eq%20{c}%20and%20TIP_RESP%20eq%20'P'")
        try:
            # 1 tentativa: o 500 do FNDE é fixo por município/ano (ex.: Anamã falha nos 6 bimestres de 2024, testado em 16/10/2026)
            v += rede.get_json(u, tentativas=1)["value"]  # o que falhar não fica no cache: rodar de novo repete só as falhas
        except Exception as e:
            falhas.append(f"{a}/{p} município {c}: {e.__class__.__name__}")
    return v, falhas


def main():
    muns = {m["cod_ibge"][:6]: m for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    mand = defaultdict(list)
    for m in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")):
        if m["inicio"]:
            mand[m["cod_ibge"]].append(m)
    nomes = defaultdict(dict)  # cod_ibge -> {pessoa_id: nome}
    for arq, campos in (("candidaturas_prefeito.csv", (("pessoa_id", "nome"), ("vice_pessoa_id", "vice_nome"))),
                        ("candidaturas_vereador.csv", (("pessoa_id", "nome"),))):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            for cp, cn in campos:
                if r.get(cp) and r.get(cn):
                    nomes[r["cod_ibge"]][r[cp]] = r[cn]
    nome_pessoa = {p["pessoa_id"]: p["nome"] for p in csv.DictReader(open(os.path.join(DADOS, "pessoas.csv"), encoding="utf-8"))}
    vereador = defaultdict(list)  # (cod, pessoa_id) -> [(inicio, fim)]
    for m in csv.DictReader(open(os.path.join(DADOS, "mandatos_vereador.csv"), encoding="utf-8")):
        if m["pessoa_id"] and m["inicio"]:
            vereador[(m["cod_ibge"], m["pessoa_id"])].append((m["inicio"], m["fim_previsto"]))

    def vigente(cod, d):
        return next((m for m in mand[cod] if m["inicio"] <= d.isoformat() <= m["fim_previsto"]), None)

    def papel(nome, m):
        if not m:
            return None
        if mesmo(nome, m["prefeito"]):
            return "titular"
        if m["vice"] and mesmo(nome, m["vice"]):
            return "vice"
        return None

    checagens, alertas, linhas, faltas, lixo = [], [], [], [], []
    for a in ANOS:
        anual = a <= 2016
        for p in ((1,) if anual else range(1, 7)):
            v, f_ = responsaveis(a, p, list(muns))
            faltas += f_
            if not v:  # ano ainda não publicado ou instabilidade da API
                faltas.append(f"{a}/{p}: sem resposta")
                continue
            for x in v:
                mu = muns.get(str(x["COD_MUNI"]))
                if not mu:
                    continue  # a 63ª linha é o governo do estado
                if len(palavras(x.get("NOM_RESP"))) < 2:
                    lixo.append(f"{a}/{p} {mu['municipio']}: “{x.get('NOM_RESP')}”")
                    continue  # campo preenchido com lixo ("***-+98", ",C")
                cod, nome = mu["cod_ibge"], x["NOM_RESP"].strip()
                dfim, ddec = fim_periodo(a, p, anual), data_decl(x.get("DAT_DECL"))
                m_per, m_dec = vigente(cod, dfim), vigente(cod, ddec) if ddec else None
                pp, pd = papel(nome, m_per), papel(nome, m_dec)
                cands = [pid for pid, n in nomes[cod].items() if mesmo(nome, n)]
                pid = cands[0] if len(cands) == 1 else ""
                if pp:
                    sit = f"{pp} eleito no TSE para o período"
                elif pd:
                    sit = f"{pd} do mandato seguinte (declaração transmitida depois)"
                elif m_per and quase(nome, m_per["prefeito"]):
                    sit = "provável titular com nome grafado diferente (conferir)"
                elif pid and any(i <= dfim.isoformat() <= f for i, f in vereador[(cod, pid)]):
                    sit = "outra pessoa: vereador(a) em exercício no período (possível presidente da Câmara como interino)"
                else:
                    sit = "outra pessoa: não é o titular nem o vice eleitos no TSE"
                if not m_per:
                    sit = "sem mandato no TSE para o período (lacuna)" + ("" if pp else f"; declarado: {nome}")
                linhas.append({"cod_ibge": cod, "municipio": mu["municipio"], "ano": a, "periodo": "anual" if anual else f"{p}º bimestre",
                               "nome_declarado": nome.title(), "data_declaracao": ddec.isoformat() if ddec else "",
                               "titular_tse": m_per["prefeito"] if m_per else "", "situacao": sit, "pessoa_id": pid,
                               "ligacao": "nome + município" if pid else ("ambíguo" if len(cands) > 1 else ""),
                               "fonte": f"SIOPE/FNDE {API.format(a=a, p=p)}"})
        n_ano = len({x["cod_ibge"] for x in linhas if x["ano"] == a})
        if n_ano and a < datetime.now().year:  # o ano corrente ainda está sendo declarado
            checagens.append((n_ano >= 60, f"{a}: {n_ano} de 62 municípios com prefeito declarado no SIOPE"))
    outras = [x for x in linhas if x["situacao"].startswith("outra pessoa")]
    # a mesma pessoa em períodos seguidos vira um registro só no relatório
    resumo = defaultdict(list)
    for x in outras:
        resumo[(x["municipio"], x["nome_declarado"], x["titular_tse"])].append(f"{x['ano']} {x['periodo']}")
    checagens.append((True, f"declarações com outra pessoa como prefeito: {len(outras)} ({len(resumo)} casos distintos) — ver lista"))
    with open(os.path.join(DADOS, "prefeito_declarado.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "municipio", "ano", "periodo", "nome_declarado", "data_declaracao", "titular_tse", "situacao",
                               "pessoa_id", "ligacao", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "18_prefeito_declarado.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — prefeito declarado ao SIOPE (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Outra pessoa declarada como prefeito (sinal de interino, afastamento ou sucessão — conferir)\n\n"
                + "\n".join(f"- {m}: **{n}** declarado(a) em {', '.join(per[:4])}{' …' if len(per) > 4 else ''} (titular no TSE: {t or '—'})"
                            for (m, n, t), per in sorted(resumo.items()))
                + "\n\n## Nome do responsável ilegível (descartado)\n\n" + ("\n".join(f"- {x}" for x in lixo) or "- nenhum")
                + "\n\n## Períodos sem resposta da API\n\n" + ("\n".join(f"- {x}" for x in faltas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} outras={len(outras)} casos={len(resumo)} faltas={len(faltas)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
