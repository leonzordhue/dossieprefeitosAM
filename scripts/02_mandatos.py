"""Candidaturas e mandatos de prefeito dos 62 municípios do Amazonas, ciclos 2000-2024 (inclui eleições suplementares).

Fontes (todas do TSE, baixadas por 01_tse_baixar.py; proveniência em dados/brutos/tse/_proveniencia.json):
  - consulta_cand_<ano>_AM.csv            candidatos, situação, resultado (DS_SIT_TOT_TURNO)
  - votacao_candidato_munzona_<ano>_AM.csv votos nominais por zona (somados por candidato)
  - IBGE localidades (servicodados.ibge.gov.br/api/v1/localidades/estados/13/municipios) para o código IBGE

Regras (Lei 9.504/1997 e CF art. 29): mandato de 4 anos, posse em 1º de janeiro do ano seguinte à eleição ordinária.
Eleição suplementar (CD_TIPO_ELEICAO=1) completa o mandato; a data exata da posse não está no TSE, então o início
do mandato suplementar é marcado como aproximado (data da eleição). Quem governou entre a saída do eleito e a posse
do suplementar (em geral o presidente da Câmara) NÃO está no TSE: fica como lacuna explícita.

Identidade da pessoa: título de eleitor (o CPF vem mascarado a partir de 2024). Publicamos só um código derivado
(sha1 do título, 10 caracteres), nunca o título.

Saídas: dados/municipios.csv, dados/candidaturas_prefeito.csv, dados/mandatos.csv, dados/pessoas.csv,
        dados/integridade/02_mandatos.md (toda checagem, com o que passou e o que falhou)
Uso: python -I scripts/02_mandatos.py
"""
import csv
import hashlib
import os
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(BASE_DIR, "dados", "brutos", "tse")
DADOS = os.path.join(BASE_DIR, "dados")
CICLOS = (2000, 2004, 2008, 2012, 2016, 2020, 2024)
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}
URL_IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/13/municipios"

checagens = []  # (ok: bool, descrição)
alertas = []    # casos para verificação humana


def chk(ok, desc):
    checagens.append((bool(ok), desc))
    return ok


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("'", " ").replace("-", " ").split())


def ler(arq):
    with open(os.path.join(TSE, arq), encoding="latin1", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def dt(s):
    return datetime.strptime(s, "%d/%m/%Y").date()


def pid(titulo):
    return hashlib.sha1(titulo.encode()).hexdigest()[:10]


def gravar(nome, linhas, campos):
    with open(os.path.join(DADOS, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(linhas)


def main():
    os.makedirs(os.path.join(DADOS, "integridade"), exist_ok=True)

    # --- municípios: TSE (SG_UE) -> IBGE ---
    ibge = {norm(m["nome"]): (m["id"], m["nome"]) for m in rede.get_json(URL_IBGE)}
    chk(len(ibge) == 62, f"IBGE lista 62 municípios no AM (achou {len(ibge)})")
    ue = defaultdict(set)  # o TSE muda a grafia entre anos (ex.: 02976 "BOA VISTA DE RAMOS" em 2000)
    for a in CICLOS:
        for r in ler(f"consulta_cand_{a}_AM.csv"):
            ue[r["SG_UE"]].add(r["NM_UE"])
    mun = {}
    for sg, nomes in ue.items():
        par = {ibge[norm(n)] for n in nomes if norm(n) in ibge}
        if len(par) == 1:
            mun[sg] = (*par.pop(), sg)
        else:
            alertas.append(f"UE do TSE sem par único no IBGE: {sg} {sorted(nomes)} -> {par}")
    chk(len(mun) == 62 and len({m[0] for m in mun.values()}) == 62,
        f"cada um dos 62 municípios do IBGE tem exatamente um código do TSE (pareados {len(mun)} de {len(ue)} UEs)")
    gravar("municipios.csv", [{"cod_ibge": c, "municipio": n, "cod_tse": s} for c, n, s in sorted(mun.values(), key=lambda x: x[1])],
           ["cod_ibge", "municipio", "cod_tse"])

    candidaturas, mandatos = [], []
    pessoas = {}
    nasc_por_pessoa = defaultdict(set)
    # nome -> pessoas (todas as candidaturas a prefeito/vice), para ligar quem só aparece no arquivo de votação
    por_nome = defaultdict(set)
    for a in CICLOS:
        for r in ler(f"consulta_cand_{a}_AM.csv"):
            if r["DS_CARGO"] in ("PREFEITO", "VICE-PREFEITO"):
                por_nome[norm(r["NM_CANDIDATO"])].add(pid(r["NR_TITULO_ELEITORAL_CANDIDATO"]))
    for ciclo in CICLOS:
        cand = [r for r in ler(f"consulta_cand_{ciclo}_AM.csv") if r["DS_CARGO"] in ("PREFEITO", "VICE-PREFEITO")]
        votos, meta = Counter(), {}
        for r in ler(f"votacao_candidato_munzona_{ciclo}_AM.csv"):
            if r["DS_CARGO"].upper() == "PREFEITO":  # 2000 grava "Prefeito"
                # 2000 grava os votos só em QT_VOTOS_NOMINAIS_VALIDOS (QT_VOTOS_NOMINAIS = 0); usa o maior dos dois.
                # SQ_CANDIDATO só é único dentro do município em 2000/2004, por isso a chave leva SG_UE.
                v = max(int(r["QT_VOTOS_NOMINAIS"] or 0), int(r.get("QT_VOTOS_NOMINAIS_VALIDOS") or 0))
                votos[(r["CD_ELEICAO"], r["NR_TURNO"], r["SG_UE"], r["SQ_CANDIDATO"])] += v
                meta.setdefault((r["CD_ELEICAO"], r["NR_TURNO"], r["SG_UE"], r["SQ_CANDIDATO"]), r)
        prefs = [r for r in cand if r["DS_CARGO"] == "PREFEITO"]
        chaves = {(r["SG_UE"], r["SQ_CANDIDATO"]) for r in prefs}
        # o arquivo de candidatos do TSE é incompleto (ex.: suplementares de 2008 em Anamã, Coari e Tefé só estão na
        # votação). Quem só existe na votação entra com os campos que ela tem e origem marcada.
        orfaos = [k for k in meta if k[2:] not in chaves]
        for k in orfaos:
            r = {c: " ".join(v.split()) if isinstance(v, str) else v for c, v in meta[k].items()}  # 2004 vem com espaços
            nome = norm(r["NM_CANDIDATO"])
            ids = por_nome.get(nome, set())
            r.update({"_origem": "só no arquivo de votação", "DS_CARGO": "PREFEITO",
                      "_pid": next(iter(ids)) if len(ids) == 1 else pid("nome:" + nome),
                      "DS_SITUACAO_CANDIDATURA": "(não consta no arquivo de candidatos)"})
            alertas.append(f"{ciclo} {r['NM_UE'].title()}: {r['NM_CANDIDATO'].title()} ({r['DS_ELEICAO'].title()}, "
                           f"{r['DS_SIT_TOT_TURNO']}) só existe no arquivo de votação; pessoa ligada "
                           + ("pelo nome (único)" if len(ids) == 1 else "sem título — código provisório pelo nome"))
            prefs.append(r)
        chk(True, f"{ciclo}: {len(orfaos)} candidatura(s) recuperada(s) do arquivo de votação")
        disputaram = [r for r in prefs if r["DS_SIT_TOT_TURNO"] in ELEITO | {"NÃO ELEITO", "2º TURNO"}]
        com_voto = sum(1 for r in disputaram if votos.get((r["CD_ELEICAO"], r["NR_TURNO"], r["SG_UE"], r["SQ_CANDIDATO"])))
        chk(com_voto >= 0.95 * len(disputaram),
            f"{ciclo}: votos encontrados para {com_voto} de {len(disputaram)} candidatos que disputaram (mínimo 95%)")
        total = Counter()
        for (el, t, sg, _), v in votos.items():
            total[(el, t, sg)] += v
        # chapa: a partir de 2004 o vice usa o número do prefeito; em 2000 tinha número próprio (partido do vice + "1"),
        # então liga pela coligação (SQ_COLIGACAO) e, para partido isolado (-1), pelo número do prefeito + "1"
        vices = {}
        for r in cand:
            if r["DS_CARGO"] == "VICE-PREFEITO":
                vices[("nr", r["CD_ELEICAO"], r["SG_UE"], r["NR_CANDIDATO"])] = r
                if r["SQ_COLIGACAO"] not in ("-1", "", "#NULO#"):
                    vices[("col", r["CD_ELEICAO"], r["SG_UE"], r["SQ_COLIGACAO"])] = r

        # uma linha por candidato a prefeito em cada turno
        eleitos = defaultdict(list)  # (sg_ue) -> [(data, tipo, linha)]
        for r in prefs:
            k = (r["CD_ELEICAO"], r["NR_TURNO"], r["SG_UE"], r["SQ_CANDIDATO"])
            p = r.get("_pid") or pid(r["NR_TITULO_ELEITORAL_CANDIDATO"])
            # resultado: arquivo de candidatos; se vier nulo, o do arquivo de votação (e diverência vira alerta)
            res_v = meta.get(k, {}).get("DS_SIT_TOT_TURNO", "")
            res = r["DS_SIT_TOT_TURNO"]
            if res.startswith("#NULO") and res_v and not res_v.startswith("#"):
                res = res_v
            elif res_v and not res_v.startswith("#") and res_v.upper() != res.upper():
                alertas.append(f"{ciclo} {mun[r['SG_UE']][1]}: {r['NM_CANDIDATO'].title()} — resultado diverge entre "
                               f"candidatos ({res}) e votação ({res_v})")
            r["DS_SIT_TOT_TURNO"] = res.upper()
            if "_pid" in r:
                pessoas.setdefault(p, {"pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nascimento": "", "genero": "",
                                       "uf_nascimento": "", "municipio_nascimento": ""})
            else:
                nasc_por_pessoa[p].add(r["DT_NASCIMENTO"])
                pessoas[p] = {"pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nascimento": r["DT_NASCIMENTO"],
                          "genero": r["DS_GENERO"].title(), "uf_nascimento": r["SG_UF_NASCIMENTO"],
                              "municipio_nascimento": r.get("NM_MUNICIPIO_NASCIMENTO", "").title()}
            v = votos.get(k, 0)
            tot = total.get((r["CD_ELEICAO"], r["NR_TURNO"], r["SG_UE"]), 0)
            vice = (vices.get(("nr", r["CD_ELEICAO"], r["SG_UE"], r["NR_CANDIDATO"]))
                    or vices.get(("col", r["CD_ELEICAO"], r["SG_UE"], r["SQ_COLIGACAO"]))
                    or vices.get(("nr", r["CD_ELEICAO"], r["SG_UE"], r["NR_CANDIDATO"] + "1")))
            if vice:  # o vice também é pessoa da plataforma (contrato §2)
                pv = pid(vice["NR_TITULO_ELEITORAL_CANDIDATO"])
                if pv not in pessoas or not pessoas[pv]["nascimento"]:
                    pessoas[pv] = {"pessoa_id": pv, "nome": vice["NM_CANDIDATO"].title(), "nascimento": vice["DT_NASCIMENTO"],
                                   "genero": vice["DS_GENERO"].title(), "uf_nascimento": vice["SG_UF_NASCIMENTO"],
                                   "municipio_nascimento": vice.get("NM_MUNICIPIO_NASCIMENTO", "").title()}
            linha = {
                "ciclo": ciclo, "cod_ibge": mun[r["SG_UE"]][0], "municipio": mun[r["SG_UE"]][1],
                "tipo_eleicao": "suplementar" if r["CD_TIPO_ELEICAO"] == "1" else "ordinária",
                "cd_eleicao": r["CD_ELEICAO"], "eleicao": r["DS_ELEICAO"], "data_eleicao": dt(r["DT_ELEICAO"]).isoformat(), "turno": r["NR_TURNO"],
                "pessoa_id": p, "nome": r["NM_CANDIDATO"].title(), "nome_urna": r["NM_URNA_CANDIDATO"],
                "numero": r["NR_CANDIDATO"], "partido": r["SG_PARTIDO"], "coligacao": r["NM_COLIGACAO"],
                "composicao_coligacao": r.get("DS_COMPOSICAO_COLIGACAO", ""), "situacao_candidatura": r["DS_SITUACAO_CANDIDATURA"],
                "detalhe_situacao": r.get("DS_DETALHE_SITUACAO_CAND", ""), "resultado": r["DS_SIT_TOT_TURNO"],
                "reeleicao": r.get("ST_REELEICAO", ""), "votos": v, "pct_votos_nominais": round(100 * v / tot, 2) if tot else "",
                "instrucao": r.get("DS_GRAU_INSTRUCAO", "").title(), "ocupacao": r.get("DS_OCUPACAO", "").title(),
                "idade_posse": r.get("NR_IDADE_DATA_POSSE", ""), "despesa_max_campanha": r.get("VR_DESPESA_MAX_CAMPANHA", ""),
                "vice_nome": vice["NM_CANDIDATO"].title() if vice else "", "vice_partido": vice["SG_PARTIDO"] if vice else "",
                "vice_pessoa_id": pid(vice["NR_TITULO_ELEITORAL_CANDIDATO"]) if vice else "",
                "origem_dado": r.get("_origem", "arquivo de candidatos + votação"),
                "fonte": f"TSE consulta_cand_{ciclo} + votacao_candidato_munzona_{ciclo} (SQ_CANDIDATO {r['SQ_CANDIDATO']})",
            }
            candidaturas.append(linha)
            if r["DS_SIT_TOT_TURNO"] in ELEITO:
                eleitos[r["SG_UE"]].append(linha)
                if "_origem" in r:  # recuperado da votação: o vice também não está no arquivo de candidatos
                    alertas.append(f"{ciclo} {linha['municipio']}: vice de {linha['nome']} não identificado (fora do arquivo de candidatos)")
                elif not chk(vice, f"{ciclo} {linha['municipio']}: eleito {linha['nome']} tem vice no TSE"):
                    alertas.append(f"{ciclo} {linha['municipio']}: eleito sem vice localizado")

        # checagens do resultado: eleito = mais votado entre os de candidatura deferida, por eleição/turno
        por_disputa = defaultdict(list)
        for c in candidaturas:
            if c["ciclo"] == ciclo:
                por_disputa[(c["cd_eleicao"], c["data_eleicao"], c["turno"], c["cod_ibge"])].append(c)
        for (el, de, t, cod), cs in por_disputa.items():
            el_ = [c for c in cs if c["resultado"] in ELEITO]
            vot = [c for c in cs if c["resultado"] in ELEITO | {"NÃO ELEITO", "2º TURNO"}]
            if el_ and vot and max(c["votos"] for c in vot) > el_[0]["votos"]:
                alertas.append(f"{ciclo} {cs[0]['municipio']} ({el}, turno {t}): eleito {el_[0]['nome']} "
                               f"({el_[0]['votos']} votos) não é o mais votado no arquivo de votação")
            if el_ and el_[0]["votos"] == 0:
                alertas.append(f"{ciclo} {cs[0]['municipio']}: eleito {el_[0]['nome']} sem votos no arquivo de votação")

        # mandatos do ciclo
        inicio_ciclo, fim_ciclo = date(ciclo + 1, 1, 1), date(ciclo + 4, 12, 31)
        for sg, (cod, nome_mun, _) in sorted(mun.items(), key=lambda x: x[1][1]):
            lst = sorted(eleitos.get(sg, []), key=lambda c: c["data_eleicao"])
            ordi = [c for c in lst if c["tipo_eleicao"] == "ordinária"]
            sup = [c for c in lst if c["tipo_eleicao"] == "suplementar"]
            chk(len(ordi) <= 1, f"{ciclo} {nome_mun}: no máximo um eleito na eleição ordinária")
            supl_todas = sorted({(c["data_eleicao"], c["eleicao"]) for c in candidaturas
                                 if c["ciclo"] == ciclo and c["cod_ibge"] == cod and c["tipo_eleicao"] == "suplementar"})
            if not ordi:
                alertas.append(f"{ciclo} {nome_mun}: ninguém consta como ELEITO na ordinária (candidatura cassada/indeferida?)"
                               + (f"; suplementar em {', '.join(d for d, _ in supl_todas)}" if supl_todas else
                                  "; NENHUMA suplementar no TSE — verificar quem governou"))
            if len(supl_todas) and not sup:
                alertas.append(f"{ciclo} {nome_mun}: houve suplementar mas ninguém consta como ELEITO nela")
            seq = ordi + sup
            # suplementar antes de 1º/jan (ex.: Boca do Acre, 05/12/2004): a eleição ordinária foi anulada e o mandato dela não começou
            while len(seq) > 1 and date.fromisoformat(seq[1]["data_eleicao"]) <= inicio_ciclo:
                alertas.append(f"{ciclo} {nome_mun}: eleição de {seq[0]['data_eleicao']} ({seq[0]['nome']}) substituída por "
                               f"suplementar em {seq[1]['data_eleicao']}, antes da posse")
                seq = seq[1:]
            for i, c in enumerate(seq):
                ini = inicio_ciclo if c["tipo_eleicao"] == "ordinária" else max(date.fromisoformat(c["data_eleicao"]), inicio_ciclo)
                fim = date.fromisoformat(seq[i + 1]["data_eleicao"]) if i + 1 < len(seq) else fim_ciclo
                mandatos.append({
                    "ciclo": ciclo, "periodo": f"{ciclo + 1}-{ciclo + 4}", "cod_ibge": cod, "municipio": nome_mun,
                    "pessoa_id": c["pessoa_id"], "prefeito": c["nome"], "nome_urna": c["nome_urna"], "partido": c["partido"],
                    "vice": c["vice_nome"], "vice_partido": c["vice_partido"], "vice_pessoa_id": c["vice_pessoa_id"],
                    "origem": c["tipo_eleicao"], "data_eleicao": c["data_eleicao"], "votos": c["votos"],
                    "pct_votos_nominais": c["pct_votos_nominais"], "reeleicao": c["reeleicao"],
                    "inicio": ini.isoformat(), "inicio_aproximado": "não" if ini == inicio_ciclo else "sim (data da eleição)",
                    "fim_previsto": fim.isoformat(),
                    "observacao": ("mandato interrompido; sucessor por eleição suplementar" if i + 1 < len(seq) else ""),
                    "fonte": c["fonte"],
                })
            if seq and seq[0]["tipo_eleicao"] == "suplementar" and seq[0]["data_eleicao"] > inicio_ciclo.isoformat():
                mandatos.append({"ciclo": ciclo, "periodo": f"{ciclo + 1}-{ciclo + 4}", "cod_ibge": cod, "municipio": nome_mun,
                                 "prefeito": "(interino — não consta no TSE)", "origem": "lacuna", "inicio": inicio_ciclo.isoformat(),
                                 "fim_previsto": seq[0]["data_eleicao"], "observacao": "sem eleito na ordinária; verificar quem governou",
                                 "fonte": "inferido da ausência de ELEITO na ordinária"})
            if not seq:
                mandatos.append({"ciclo": ciclo, "periodo": f"{ciclo + 1}-{ciclo + 4}", "cod_ibge": cod, "municipio": nome_mun,
                                 "prefeito": "(não identificado no TSE)", "origem": "lacuna", "inicio": inicio_ciclo.isoformat(),
                                 "fim_previsto": fim_ciclo.isoformat(), "observacao": "sem ELEITO na ordinária nem em suplementar",
                                 "fonte": "TSE"})
        for m in mandatos:
            if m["ciclo"] == ciclo:
                chk(m["inicio"] <= m["fim_previsto"], f"{ciclo} {m['municipio']} {m['prefeito']}: início {m['inicio']} ≤ fim {m['fim_previsto']}")
        cobertos = {m["cod_ibge"] for m in mandatos if m["ciclo"] == ciclo}
        chk(len(cobertos) == 62, f"{ciclo}: os 62 municípios têm ao menos uma linha de mandato ({len(cobertos)})")

    # mesma pessoa com datas de nascimento diferentes = título reaproveitado ou erro no TSE
    for p, ds in nasc_por_pessoa.items():
        if len(ds) > 1:
            alertas.append(f"pessoa {p} ({pessoas[p]['nome']}) com datas de nascimento divergentes no TSE: {sorted(ds)}")
    # mesmo nome + nascimento com títulos diferentes = a mesma pessoa pode estar partida em dois códigos
    chave = defaultdict(set)
    for c in candidaturas:
        chave[(norm(c["nome"]), pessoas[c["pessoa_id"]]["nascimento"])].add(c["pessoa_id"])
    for (n, d), ids in chave.items():
        if len(ids) > 1:
            alertas.append(f"{n} ({d}) aparece com {len(ids)} títulos diferentes: {sorted(ids)}")

    # mandato consecutivo calculado (o TSE só informa ST_REELEICAO até 2016)
    anteriores = {(m["cod_ibge"], m["ciclo"], m.get("pessoa_id")) for m in mandatos}
    for m in mandatos:
        m["mandato_seguido"] = "sim" if m.get("pessoa_id") and (m["cod_ibge"], m["ciclo"] - 4, m["pessoa_id"]) in anteriores else "não"
    campos_c = list(candidaturas[0].keys())
    gravar("candidaturas_prefeito.csv", candidaturas, campos_c)
    campos_m = ["ciclo", "periodo", "cod_ibge", "municipio", "pessoa_id", "prefeito", "nome_urna", "partido", "vice", "vice_partido",
                "vice_pessoa_id", "origem", "data_eleicao", "votos", "pct_votos_nominais", "reeleicao", "mandato_seguido", "inicio", "inicio_aproximado",
                "fim_previsto", "observacao", "fonte"]
    gravar("mandatos.csv", mandatos, campos_m)
    gravar("pessoas.csv", sorted(pessoas.values(), key=lambda x: x["nome"]), list(next(iter(pessoas.values())).keys()))

    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "02_mandatos.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — mandatos de prefeito (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n")
        f.write(f"- Candidaturas a prefeito (linhas por turno): {len(candidaturas)}\n- Linhas de mandato: {len(mandatos)}\n"
                f"- Pessoas distintas: {len(pessoas)}\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        falhas = [d for o, d in checagens if not o]
        f.write("## Checagens que falharam\n\n" + ("\n".join(f"- ❌ {d}" for d in falhas) or "- nenhuma") + "\n\n")
        f.write("## Alertas para verificação humana\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n\n")
        f.write("## Todas as checagens\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n")
    print(f"candidaturas={len(candidaturas)} mandatos={len(mandatos)} pessoas={len(pessoas)} "
          f"checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
