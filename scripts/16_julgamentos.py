"""Fundamentos de julgamento das candidaturas municipais do AM pela Justiça Eleitoral (indeferimento, cassação de registro
ou diploma), eleições 2012-2024, e ligação aos mandatos de prefeito interrompidos.

Fonte: TSE motivo_cassacao_<ano>_AM.csv (https://cdn.tse.jus.br/estatistica/sead/odsele/motivo_cassacao/), que só existe
a partir de 2012 (o de 2012 vem vazio para o AM, conferido em 16/10/2026). As colunas mudam:
DS_MOTIVO_CASSACAO em 2016, DS_TP_MOTIVO + DS_MOTIVO em 2020, + NR_PROCESSO em 2024. Ligação à pessoa: (SG_UE, SQ_CANDIDATO) -> título no consulta_cand do mesmo ano (pessoa_id = sha1 do título).
Categoria "inelegibilidade ou ilícito eleitoral": Ficha Limpa (LC 64/1990), abuso de poder (LC 64/1990, art. 22),
compra de voto (Lei 9.504/1997, art. 41-A), conduta vedada (art. 73), gasto ilícito (art. 30-A). Os demais
("ausência de requisito de registro", "indeferimento de partido ou coligação") são falhas formais do registro (categoria "requisito formal").
O arquivo traz o fundamento, não o processo nem a data da decisão; quem governou depois vem de 02_mandatos.py
(eleição suplementar). Interinos (presidente da Câmara) não constam no TSE.

Saídas: dados/julgamentos.csv (pessoa_id, ano, cargo, cod_ibge, municipio, nome, resultado, tipo_motivo, motivo, categoria, fonte),
        dados/integridade/16_julgamentos.md
Uso: python -I scripts/16_julgamentos.py
"""
import csv
import hashlib
import io
import os
import sys
import zipfile
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/motivo_cassacao/motivo_cassacao_{a}.zip"
ANOS = (2012, 2016, 2020, 2024)
CARGOS = {"PREFEITO": "prefeito", "VICE-PREFEITO": "vice-prefeito", "VEREADOR": "vereador"}
GRAVES = ("FICHA LIMPA", "INELEGIBILIDADE", "ABUSO", "COMPRA DE VOTO", "CONDUTA VEDADA", "GASTO IL", "CAPTA")


def main():
    mun = {m["cod_tse"]: m for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, alertas, linhas = [], [], []
    for a in ANOS:
        cand = {}
        with open(os.path.join(DADOS, "brutos", "tse", f"consulta_cand_{a}_AM.csv"), encoding="latin1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r["DS_CARGO"].upper() in CARGOS:
                    cand[(r["SG_UE"], r["SQ_CANDIDATO"])] = r
        z = zipfile.ZipFile(io.BytesIO(rede.get(URL.format(a=a))))
        mot = list(csv.DictReader(io.TextIOWrapper(z.open(f"motivo_cassacao_{a}_AM.csv"), encoding="latin1"), delimiter=";"))
        orfaos, vistos = 0, set()
        for x in mot:
            c = cand.get((x["SG_UE"], x["SQ_CANDIDATO"]))
            if c is None:
                orfaos += 1
                continue
            motivo = (x.get("DS_MOTIVO") or x.get("DS_MOTIVO_CASSACAO") or "").strip().rstrip(".").strip()
            k = (x["SG_UE"], x["SQ_CANDIDATO"], motivo)
            if k in vistos:  # o arquivo repete o motivo por turno/eleição
                continue
            vistos.add(k)
            linhas.append({"pessoa_id": hashlib.sha1(c["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10], "ano": a,
                           "cargo": CARGOS[c["DS_CARGO"].upper()], "cod_ibge": mun[x["SG_UE"]]["cod_ibge"],
                           "municipio": mun[x["SG_UE"]]["municipio"], "nome": c["NM_CANDIDATO"].title(),
                           "resultado": c["DS_SIT_TOT_TURNO"].upper(), "tipo_motivo": x.get("DS_TP_MOTIVO", "Fundamentos legais de julgamento").strip(), "motivo": motivo,
                           "categoria": "inelegibilidade ou ilícito eleitoral" if any(g in motivo.upper() for g in GRAVES) else "requisito formal",
                           "fonte": f"TSE motivo_cassacao_{a} + consulta_cand_{a} (SQ_CANDIDATO {x['SQ_CANDIDATO']}; {x['DS_ELEICAO'].strip()}"
                                     + (f"; processo {x['NR_PROCESSO']}" if x.get("NR_PROCESSO") else "") + ")"})
        checagens.append((orfaos <= 0.01 * max(len(mot), 1) and (bool(mot) or a == 2012), f"{a}: {len(mot)} registros; {orfaos} sem candidato municipal correspondente (tolerância 1%)"
                          + (" — arquivo do TSE vazio para o AM" if not mot else "")))

    # prefeitos com mandato interrompido por suplementar: há fundamento de julgamento no TSE?
    mand = list(csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")))
    por = defaultdict(list)
    for j in linhas:
        por[(j["pessoa_id"], j["ano"])].append(j["motivo"])
    interrompidos = [m for m in mand if "interrompido" in m["observacao"] and int(m["ciclo"]) in ANOS]
    sem = [m for m in interrompidos if not por.get((m["pessoa_id"], int(m["ciclo"])))]
    checagens.append((True, f"mandatos de prefeito interrompidos (2012-2024): {len(interrompidos)}; com fundamento no TSE: "
                            f"{len(interrompidos) - len(sem)} (cassação depois da diplomação pode não aparecer neste arquivo)"))
    for m in sem:
        alertas.append(f"{m['ciclo']} {m['municipio']}: {m['prefeito']} teve o mandato interrompido e não há fundamento no "
                       "arquivo do TSE; motivo a confirmar no processo")
    with open(os.path.join(DADOS, "julgamentos.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["pessoa_id", "ano", "cargo", "cod_ibge", "municipio", "nome", "resultado", "tipo_motivo", "motivo",
                               "categoria", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    graves = [j for j in linhas if j["categoria"] != "requisito formal" and j["cargo"] != "vereador"]
    with open(os.path.join(DADOS, "integridade", "16_julgamentos.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — julgamentos da Justiça Eleitoral (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Linhas: {len(linhas)}\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + f"\n\n## Prefeito/vice com inelegibilidade ou ilícito eleitoral ({len(graves)})\n\n"
                + ("\n".join(f"- {j['ano']} {j['municipio']}: {j['nome']} ({j['cargo']}, {j['resultado'].lower()}) — {j['motivo']}"
                             for j in graves) or "- nenhum")
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} inelegib_prefeito_vice={len(graves)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
