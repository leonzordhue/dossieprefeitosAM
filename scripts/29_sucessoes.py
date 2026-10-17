"""Quem governa de fato: aplica a mandatos.csv as sucessões verificadas (renúncia, cassação, morte, afastamento) que o TSE
não registra, e a mandatos_vereador.csv os suplentes chamados a assumir.

Entradas:
  - dados/sucessoes_verificadas.csv: uma linha por sucessão, conferida em documento oficial (ata da Câmara, Diário Oficial),
    com data, quem sai, quem entra, papel de quem entra (vice, presidente da Câmara, eleito em suplementar), fonte e trecho.
  - dados/vereadores_suplentes_posse.csv (26) e dados/camaras_edicoes_suplentes.csv (28): suplente do ciclo em ato de posse
    ou convocação, com o motivo citado no ato.
Regras:
  - mandatos.csv: o mandato de quem sai ganha fim_real (data) e a observação com o evento e a fonte; quem entra ganha uma
    linha própria (origem "posse de vice" / "posse do presidente da Câmara" / "eleição suplementar"), do dia até o fim previsto.
  - mandatos_vereador.csv: o suplente ganha uma linha (origem "posse de suplente"), da primeira data do ato de posse até o fim
    do mandato; a data é a do ato, e o fim não é inventado (fica o fim previsto, com a observação "pode ter devolvido a vaga").
  - Idempotente: linhas e fim_real que este script criou são refeitos a cada rodada (rodar depois de 02 e 05).
Saídas: dados/mandatos.csv e dados/mandatos_vereador.csv (atualizados), dados/integridade/29_sucessoes.md
Uso: python -I scripts/29_sucessoes.py
"""
import csv
import re
import os
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
ORIGENS = {"vice": "posse de vice", "presidente da Câmara": "posse do presidente da Câmara", "eleito em suplementar": "eleição suplementar"}
MARCA = "[29]"  # marca o que este script escreveu, para refazer sem duplicar


def ler(nome):
    p = os.path.join(DADOS, nome)
    if not os.path.exists(p):
        return [], []
    with open(p, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames)


def grava(nome, linhas, campos):
    with open(os.path.join(DADOS, nome) + ".tmp", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(linhas)
    os.replace(os.path.join(DADOS, nome) + ".tmp", os.path.join(DADOS, nome))


def limpa(linhas):
    """Desfaz o que uma rodada anterior escreveu."""
    out = []
    for r in linhas:
        if MARCA in r.get("observacao", "") and r.get("origem", "").startswith(("posse", "eleição suplementar")):
            continue
        if MARCA in r.get("observacao", ""):
            r["observacao"] = r["observacao"].split(" " + MARCA)[0].split(MARCA)[0].strip()
            r["fim_real"] = ""
        out.append(r)
    return out


def main():
    checagens, alertas = [], []
    pessoas = {p["pessoa_id"]: p["nome"] for p in csv.DictReader(open(os.path.join(DADOS, "pessoas.csv"), encoding="utf-8"))}

    # prefeitos
    mand, campos = ler("mandatos.csv")
    campos = campos + ["fim_real"] if "fim_real" not in campos else campos
    mand = limpa(mand)
    suc, _ = ler("sucessoes_verificadas.csv")
    aplicadas = 0
    for s in suc:
        alvo = next((m for m in mand if m["cod_ibge"] == s["cod_ibge"] and m["inicio"] <= s["data"] <= m["fim_previsto"]
                     and m["pessoa_id"] == s["sai_pessoa_id"]), None)
        if not alvo:
            alertas.append(f"sucessão sem mandato correspondente: {s['cod_ibge']} {s['data']} sai {s['sai_pessoa_id']}")
            continue
        alvo["fim_real"] = s["data"]
        alvo["observacao"] = (alvo["observacao"] + " " if alvo["observacao"] else "") + f"{MARCA} {s['evento']} em {s['data']} ({s['fonte']})"
        nova = dict(alvo, pessoa_id=s["entra_pessoa_id"], prefeito=pessoas.get(s["entra_pessoa_id"], ""), nome_urna="",
                    vice="", vice_partido="", vice_pessoa_id="", origem=ORIGENS.get(s["entra_papel"], s["entra_papel"]),
                    data_eleicao="", votos="", pct_votos_nominais="", reeleicao="", mandato_seguido="", inicio=s["data"],
                    inicio_aproximado="não", fim_real="", fonte=s["fonte"],
                    observacao=f"{MARCA} assumiu por {s['evento']} de {alvo['prefeito']}: “{s['trecho'][:200]}”")
        if s["entra_papel"] == "vice":
            nova["partido"] = alvo["vice_partido"]
        mand.append(nova)
        aplicadas += 1
    mand.sort(key=lambda m: (m["cod_ibge"], m["inicio"]))
    checagens.append((aplicadas == len(suc), f"sucessões verificadas aplicadas a mandatos.csv: {aplicadas} de {len(suc)}"))
    checagens.append((all(s["fonte"].startswith(("Câmara", "Diário", "TSE", "TRE")) or "http" in s["fonte"] for s in suc),
                      "toda sucessão tem fonte oficial com link"))
    grava("mandatos.csv", [{k: m.get(k, "") for k in campos} for m in mand], campos)

    # vereadores: suplentes chamados a assumir
    mv, campos_v = ler("mandatos_vereador.csv")
    mv = limpa(mv)
    sup = [r for nome in ("vereadores_suplentes_posse.csv", "camaras_edicoes_suplentes.csv") for r in ler(nome)[0] if r["papel"] == "suplente no ciclo"]
    # ato de encerramento ("Dispõe sobre o encerramento das atividades de suplente", retorno do titular) dá o fim;
    # os demais (posse, convocação) dão o início
    encerra = lambda r: bool(re.search(r"(?i)encerramento|retorno d[oa] titular|reassun", r["titulo"]))  # noqa: E731
    primeiro, fim = {}, {}
    for r in sorted(sup, key=lambda r: r["data"]):
        k = (r["cod_ibge"], r["pessoa_id"], r["ciclo"])
        if encerra(r):
            fim[k] = r
        else:
            primeiro.setdefault(k, r)
    vigente = {(m["cod_ibge"], m["ciclo"]): m for m in mv}
    novos = 0
    for (cod, pid, ciclo), r in primeiro.items():
        base = vigente.get((cod, ciclo))
        if not base or any(m["cod_ibge"] == cod and m["pessoa_id"] == pid and m["ciclo"] == ciclo for m in mv):
            continue
        f = fim.get((cod, pid, ciclo))
        f = f if f and f["data"] >= r["data"] else None
        mv.append(dict(base, pessoa_id=pid, vereador=r["nome_tse"], nome_urna="", votos="", resultado="SUPLENTE", mandato_seguido="",
                       origem="posse de suplente", inicio=r["data"], fim_previsto=f["data"] if f else base["fim_previsto"],
                       fonte=r["fonte"] + (f"; encerramento: {f['fonte']}" if f else ""),
                       observacao=f"{MARCA} suplente em ato de posse/convocação ({r['motivo_no_ato'] or 'motivo não citado'}); "
                                  + ("encerramento das atividades em ato próprio" if f else
                                     "a data é a do ato; pode ter devolvido a vaga antes do fim do mandato")))
        novos += 1
    mv.sort(key=lambda m: (m["cod_ibge"], m["ciclo"], m["inicio"], m.get("vereador", "")))
    checagens.append((novos > 0, f"suplentes chamados a assumir acrescentados a mandatos_vereador.csv: {novos}"))
    grava("mandatos_vereador.csv", mv, campos_v)

    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "29_sucessoes.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — sucessões e suplentes (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"sucessoes={aplicadas}/{len(suc)} suplentes={novos} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
