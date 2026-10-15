"""Candidaturas e mandatos de vereador dos 62 municípios do Amazonas, eleições 2000-2024.

Fontes (TSE, baixadas por 01_tse_baixar.py; proveniência em dados/brutos/tse/_proveniencia.json):
  - consulta_cand_<ano>_AM.csv             candidatos, situação, resultado (DS_SIT_TOT_TURNO)
  - votacao_candidato_munzona_<ano>_AM.csv votos nominais por zona (somados por candidato)

Regras: mandato de 4 anos, posse em 1º de janeiro do ano seguinte (CF art. 29, I e III). Número de vereadores por
município conforme CF art. 29, IV (mínimo 9; Manaus, faixa de 1,5 a 3 milhões de hab., até 41).
O TSE registra quem foi ELEITO e quem ficou SUPLENTE, mas NÃO registra suplente que assumiu (licença, cassação, morte,
nomeação para secretaria). Por isso o mandato aqui é o do eleito; posse de suplente fica para fontes das Câmaras.
A ordem de suplência é indicativa: votos dentro da coligação (até 2016) ou do partido/federação (2020+, EC 97/2017).

Saídas: dados/candidaturas_vereador.csv, dados/mandatos_vereador.csv, pessoas acrescentadas a dados/pessoas.csv,
        dados/integridade/05_vereadores.md
Uso: python -I scripts/05_vereadores.py   (depois de 02_mandatos.py)
"""
import csv
import hashlib
import os
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(BASE_DIR, "dados", "brutos", "tse")
DADOS = os.path.join(BASE_DIR, "dados")
CICLOS = (2000, 2004, 2008, 2012, 2016, 2020, 2024)
# 2008 grava "MÉDIA" para o eleito por média; 2024 "ELEITO POR QP"
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "MÉDIA"}
DISPUTOU = ELEITO | {"SUPLENTE", "NÃO ELEITO"}

checagens, alertas, divergencias = [], [], []


def chk(ok, desc):
    checagens.append((bool(ok), desc))
    return ok


def ler(arq):
    with open(os.path.join(TSE, arq), encoding="latin1", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def iso(d):
    """Data do TSE (DD/MM/AAAA) em ISO, como pede o contrato da plataforma; valor inválido (#NULO#) vira vazio."""
    try:
        return datetime.strptime(d, "%d/%m/%Y").date().isoformat()
    except (ValueError, TypeError):
        return ""


def pid(titulo):
    return hashlib.sha1(titulo.encode()).hexdigest()[:10]


def gravar(nome, linhas, campos):
    with open(os.path.join(DADOS, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def main():
    mun = {m["cod_tse"]: m for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    assert len(mun) == 62, "rode 02_mandatos.py antes"
    pessoas = {p["pessoa_id"]: p for p in csv.DictReader(open(os.path.join(DADOS, "pessoas.csv"), encoding="utf-8"))}
    n_pessoas_antes = len(pessoas)
    candidaturas, mandatos = [], []
    nasc = defaultdict(set)

    for ciclo in CICLOS:
        todos = ler(f"consulta_cand_{ciclo}_AM.csv")
        cand = [r for r in todos if r["DS_CARGO"].upper() == "VEREADOR"]
        for r in todos:  # candidato a vice de chapa derrotada não passa pelo 02 sem chapa ligada; entra aqui para os bens terem dono
            if r["DS_CARGO"].upper() == "VICE-PREFEITO":
                p = pid(r["NR_TITULO_ELEITORAL_CANDIDATO"])
                pessoas.setdefault(p, {"pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nascimento": iso(r["DT_NASCIMENTO"]),
                                       "genero": r["DS_GENERO"].title(), "uf_nascimento": r["SG_UF_NASCIMENTO"],
                                       "municipio_nascimento": r.get("NM_MUNICIPIO_NASCIMENTO", "").title()})
        votos, res_vot = Counter(), {}
        for r in ler(f"votacao_candidato_munzona_{ciclo}_AM.csv"):
            if r["DS_CARGO"].upper() == "VEREADOR":
                # 2000 grava os votos só em QT_VOTOS_NOMINAIS_VALIDOS; SQ_CANDIDATO só é único por município em 2000/2004
                k = (r["CD_ELEICAO"], r["SG_UE"], r["SQ_CANDIDATO"])
                votos[k] += max(int(r["QT_VOTOS_NOMINAIS"] or 0), int(r.get("QT_VOTOS_NOMINAIS_VALIDOS") or 0))
                res_vot.setdefault(k, r["DS_SIT_TOT_TURNO"].upper())
        chaves = {(r["CD_ELEICAO"], r["SG_UE"], r["SQ_CANDIDATO"]) for r in cand}
        orfaos = [k for k in res_vot if k not in chaves]
        chk(not orfaos, f"{ciclo}: todo vereador do arquivo de votação está no arquivo de candidatos ({len(orfaos)} fora)")
        for k in orfaos[:20]:
            alertas.append(f"{ciclo}: vereador SQ {k[2]} (UE {k[1]}) só no arquivo de votação ({res_vot[k]}) — não incluído")

        linhas = []
        for r in cand:
            k = (r["CD_ELEICAO"], r["SG_UE"], r["SQ_CANDIDATO"])
            res = r["DS_SIT_TOT_TURNO"].upper()
            rv = res_vot.get(k, "")
            if res.startswith("#NULO") and rv and not rv.startswith("#"):
                res = rv  # 2008 e 2024 têm centenas de #NULO no arquivo de candidatos; o da votação é o válido
            elif rv and not rv.startswith("#") and rv != res:
                alertas.append(f"{ciclo} {mun[r['SG_UE']]['municipio']}: {r['NM_CANDIDATO'].title()} — resultado diverge "
                               f"entre candidatos ({res}) e votação ({rv})")
            p = pid(r["NR_TITULO_ELEITORAL_CANDIDATO"])
            nasc[p].add(r["DT_NASCIMENTO"])
            if p not in pessoas or not pessoas[p].get("nascimento"):
                pessoas[p] = {"pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nascimento": iso(r["DT_NASCIMENTO"]),
                              "genero": r["DS_GENERO"].title(), "uf_nascimento": r["SG_UF_NASCIMENTO"],
                              "municipio_nascimento": r.get("NM_MUNICIPIO_NASCIMENTO", "").title()}
            # agrupamento que disputa as vagas: coligação até 2016; partido ou federação a partir de 2020
            if ciclo >= 2020:
                grupo = r.get("NR_FEDERACAO") if r.get("NR_FEDERACAO") not in (None, "", "-1", "#NULO#") else r["SG_PARTIDO"]
            else:
                grupo = r["SQ_COLIGACAO"] if r["SQ_COLIGACAO"] not in ("", "-1", "#NULO#") else r["SG_PARTIDO"]
            linhas.append({
                "ciclo": ciclo, "cod_ibge": mun[r["SG_UE"]]["cod_ibge"], "municipio": mun[r["SG_UE"]]["municipio"],
                "tipo_eleicao": "suplementar" if r["CD_TIPO_ELEICAO"] == "1" else "ordinária", "cd_eleicao": r["CD_ELEICAO"],
                "data_eleicao": datetime.strptime(r["DT_ELEICAO"], "%d/%m/%Y").date().isoformat(),
                "pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nome_urna": r["NM_URNA_CANDIDATO"], "numero": r["NR_CANDIDATO"],
                "partido": r["SG_PARTIDO"], "coligacao": r["NM_COLIGACAO"], "situacao_candidatura": r["DS_SITUACAO_CANDIDATURA"],
                "resultado": res, "votos": votos.get(k, 0), "_na_votacao": k in res_vot, "_grupo": (r["SG_UE"], r["CD_ELEICAO"], grupo),
                "instrucao": r.get("DS_GRAU_INSTRUCAO", "").title(), "ocupacao": r.get("DS_OCUPACAO", "").title(),
                "fonte": f"TSE consulta_cand_{ciclo} + votacao_candidato_munzona_{ciclo} (SQ_CANDIDATO {r['SQ_CANDIDATO']})",
            })

        # % dos votos nominais e ordem de suplência
        tot = Counter()
        for c in linhas:
            tot[(c["cod_ibge"], c["cd_eleicao"])] += c["votos"]
        sup_grupo = defaultdict(list)
        for c in linhas:
            t = tot[(c["cod_ibge"], c["cd_eleicao"])]
            c["pct_votos_nominais"] = round(100 * c["votos"] / t, 3) if t else ""
            if c["resultado"] == "SUPLENTE":
                sup_grupo[c["_grupo"]].append(c)
        for lst in sup_grupo.values():
            for i, c in enumerate(sorted(lst, key=lambda x: -x["votos"]), 1):
                c["ordem_suplencia_indicativa"] = i
        candidaturas += linhas

        # checagens por município
        eleitos = defaultdict(list)
        for c in linhas:
            if c["resultado"] in ELEITO:
                eleitos[c["cod_ibge"]].append(c)
        disputaram = [c for c in linhas if c["resultado"] in DISPUTOU]
        # candidato com 0 voto existe (linha na votação com QT 0); o que se confere é a presença no arquivo de votação
        com_voto = sum(1 for c in disputaram if c["_na_votacao"])
        chk(com_voto >= 0.95 * len(disputaram),
            f"{ciclo}: {com_voto} de {len(disputaram)} que disputaram estão no arquivo de votação (mínimo 95%)")
        for m in mun.values():
            n = len(eleitos.get(m["cod_ibge"], []))
            # CF art. 29, IV (EC 58/2009): até 23 vagas abaixo de 450 mil hab.; no AM só Manaus passa disso
            maximo = 41 if m["municipio"] == "Manaus" else 23
            if n == 0:
                alertas.append(f"{ciclo} {m['municipio']}: resultado de vereador #NULO no TSE (candidatos e votação) — "
                               "eleitos não identificados; completar com TRE-AM/Câmara")
                mandatos.append({"ciclo": ciclo, "periodo": f"{ciclo + 1}-{ciclo + 4}", "cargo": "vereador", "cod_ibge": m["cod_ibge"],
                                 "municipio": m["municipio"], "vereador": "(eleitos não identificados no TSE)", "origem": "lacuna",
                                 "inicio": f"{ciclo + 1}-01-01", "fim_previsto": f"{ciclo + 4}-12-31",
                                 "observacao": "DS_SIT_TOT_TURNO #NULO em todos os candidatos", "fonte": f"TSE consulta_cand_{ciclo}"})
                continue
            if not chk(9 <= n <= maximo, f"{ciclo} {m['municipio']}: {n} vereadores eleitos (CF art. 29, IV: 9 a {maximo})"):
                alertas.append(f"{ciclo} {m['municipio']}: {n} eleitos fora da faixa esperada — conferir cassação/recontagem")
            elif n % 2 == 0 and ciclo not in (2004, 2008):  # 2004/2008: vagas pela tabela da Res. TSE 21.702/2004, há pares
                alertas.append(f"{ciclo} {m['municipio']}: número par de eleitos ({n}) — a CF fixa número ímpar; conferir")
        for c in sum(eleitos.values(), []):
            if c["votos"] == 0:
                alertas.append(f"{ciclo} {c['municipio']}: eleito {c['nome']} sem votos no arquivo de votação")
            mandatos.append({
                "ciclo": ciclo, "periodo": f"{ciclo + 1}-{ciclo + 4}", "cargo": "vereador", "cod_ibge": c["cod_ibge"],
                "municipio": c["municipio"], "pessoa_id": c["pessoa_id"], "vereador": c["nome"], "nome_urna": c["nome_urna"],
                "partido": c["partido"], "votos": c["votos"], "resultado": c["resultado"], "origem": "eleição",
                "inicio": f"{ciclo + 1}-01-01", "fim_previsto": f"{ciclo + 4}-12-31",
                "observacao": "posse de suplente e afastamentos não constam no TSE", "fonte": c["fonte"],
            })

    for p, ds in nasc.items():
        if len(ds) > 1:
            divergencias.append(f"{p} ({pessoas[p]['nome']}): {sorted(ds)}")
    seguidos = {(m["cod_ibge"], m["ciclo"], m.get("pessoa_id")) for m in mandatos}
    for m in mandatos:
        m["mandato_seguido"] = "sim" if m.get("pessoa_id") and (m["cod_ibge"], m["ciclo"] - 4, m["pessoa_id"]) in seguidos else "não"
    reais = [m for m in mandatos if m["origem"] != "lacuna"]
    chk(len({(m["ciclo"], m["pessoa_id"]) for m in reais}) == len(reais), "ninguém eleito vereador duas vezes no mesmo ciclo")

    campos_c = ["ciclo", "cod_ibge", "municipio", "tipo_eleicao", "cd_eleicao", "data_eleicao", "pessoa_id", "nome", "nome_urna",
                "numero", "partido", "coligacao", "situacao_candidatura", "resultado", "votos", "pct_votos_nominais",
                "ordem_suplencia_indicativa", "instrucao", "ocupacao", "fonte"]
    gravar("candidaturas_vereador.csv", candidaturas, campos_c)
    gravar("mandatos_vereador.csv", mandatos, ["ciclo", "periodo", "cargo", "cod_ibge", "municipio", "pessoa_id", "vereador",
                                               "nome_urna", "partido", "votos", "resultado", "mandato_seguido", "origem",
                                               "inicio", "fim_previsto", "observacao", "fonte"])
    gravar("pessoas.csv", sorted(pessoas.values(), key=lambda x: x["nome"]),
           ["pessoa_id", "nome", "nascimento", "genero", "uf_nascimento", "municipio_nascimento"]
           + [c for c in ("foto", "foto_ano") if any(c in p for p in pessoas.values())])  # mantém o que 07_fotos.py gravou

    ok = sum(1 for o, _ in checagens if o)
    por_ciclo = Counter(m["ciclo"] for m in mandatos)
    with open(os.path.join(DADOS, "integridade", "05_vereadores.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — vereadores (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n")
        f.write(f"- Candidaturas a vereador: {len(candidaturas)}\n- Mandatos (eleitos): {len(mandatos)} — "
                + ", ".join(f"{a}: {n}" for a, n in sorted(por_ciclo.items())) + "\n"
                f"- Pessoas distintas candidatas a vereador: {len(nasc)} (pessoas.csv agora tem {len(pessoas)})\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        falhas = [d for o, d in checagens if not o]
        f.write("## Checagens que falharam\n\n" + ("\n".join(f"- ❌ {d}" for d in falhas) or "- nenhuma") + "\n\n")
        f.write("## Alertas para verificação humana\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n\n")
        f.write(f"## Datas de nascimento divergentes entre eleições no TSE ({len(divergencias)})\n\n"
                "Mesmo título de eleitor com datas diferentes (erro de cadastro no TSE); pessoas.csv guarda a primeira.\n\n"
                + "\n".join(f"- {d}" for d in divergencias) + "\n\n")
        f.write("## Todas as checagens\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n")
    print(f"candidaturas={len(candidaturas)} mandatos={len(mandatos)} {dict(sorted(por_ciclo.items()))} "
          f"pessoas+={len(pessoas) - n_pessoas_antes} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
