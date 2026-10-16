"""Atividade legislativa das Câmaras Municipais do AM que publicam o SAPL (Interlegis): vereadores, projetos e demais
matérias com autoria, normas (leis, resoluções, decretos legislativos), votações e votos nominais, Mesa Diretora.

Fonte: API REST pública do SAPL de cada Câmara — https://sapl.<municipio>.am.leg.br/api/ (Manaus: https://sapl.cmm.am.gov.br/api/).
       Levantamento de 16/10/2026: 27 Câmaras têm SAPL; 12 têm matérias cadastradas (lista CASAS). As demais estão vazias.
Só são lidos nomes e dados legislativos; telefone, e-mail, endereço e biografia dos parlamentares não são usados.
O que cada Câmara cadastrou varia muito (ex.: votos nominais só em algumas; Manaus registra o resultado, não o voto de
cada vereador). Ausência no SAPL não prova que o vereador não apresentou projeto ou não votou.
Ligação do parlamentar a pessoa_id: nome completo (ou nome parlamentar = nome de urna) igual, a menos de grafia, ao de
UM candidato a vereador/prefeito/vice do mesmo município no TSE; nome que casa com mais de uma pessoa fica sem ligação.

Saídas (dados/camaras/): parlamentares.csv, materias.csv, autorias.csv, normas.csv, votacoes.csv, votos.csv, mesa.csv;
        integridade em dados/integridade/20_sapl.md
Uso: python -I scripts/20_sapl.py            (respostas em dados/brutos/cache_http)
     python -I scripts/20_sapl.py --novo     (baixa de novo as páginas, para atualizar)
"""
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

decl = import_module("18_prefeito_declarado")  # mesmo(), palavras()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
SAIDA = os.path.join(DADOS, "camaras")
CASAS = {"1300680": "boavistadoramos", "1300805": "borba", "1301209": "coari", "1301308": "codajas", "1301506": "envira",
         "1301852": "iranduba", "1302504": "manacapuru", "1302603": "CMM", "1302702": "manicore", "1303205": "novoairao",
         "1303403": "parintins", "1304203": "tefe"}
NOVO = "--novo" in sys.argv


def base(h):
    return "https://sapl.cmm.am.gov.br" if h == "CMM" else f"https://sapl.{h}.am.leg.br"


def todos(h, ep):
    """Todas as páginas de um endpoint (100 por página)."""
    out, pag = [], 1
    while True:
        url = f"{base(h)}/api/{ep}/?page_size=100&page={pag}"
        if NOVO:
            rede.esquecer(url)
        if not rede.em_cache(url):
            time.sleep(0.3)
        try:
            d = rede.get_json(url)
        except Exception:  # endpoint ausente nesta versão do SAPL
            return out
        out += d.get("results", [])
        if not d.get("pagination", {}).get("next_page"):
            return out
        pag += 1


def gravar(nome, linhas, campos):
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def main():
    os.makedirs(SAIDA, exist_ok=True)
    muns = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    cand = defaultdict(dict)  # cod -> pessoa_id -> (nome, nome_urna)
    for arq in ("candidaturas_vereador.csv", "candidaturas_prefeito.csv"):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            cand[r["cod_ibge"]][r["pessoa_id"]] = (r["nome"], r["nome_urna"])
    P, M, A, N, V, VO, ME = [], [], [], [], [], [], []
    checagens, alertas = [], []
    for cod, h in CASAS.items():
        b, mun = base(h), muns[cod]
        fonte = f"SAPL da Câmara Municipal de {mun} ({b}/api/)"
        parl = todos(h, "parlamentares/parlamentar")
        ligados = 0
        for p in parl:
            nc, np_ = p.get("nome_completo") or "", p.get("nome_parlamentar") or ""
            c = [pid for pid, (n, u) in cand[cod].items() if decl.mesmo(nc, n)] if len(decl.palavras(nc)) >= 2 else []
            if len(set(c)) != 1:
                c = [pid for pid, (n, u) in cand[cod].items() if u and decl.palavras(np_) == decl.palavras(u)]
            pid = c[0] if len(set(c)) == 1 else ""
            ligados += bool(pid)
            P.append({"cod_ibge": cod, "sapl_id": p["id"], "nome_parlamentar": np_, "nome_completo": nc, "pessoa_id": pid,
                      "ligacao": "nome" if pid else ("ambíguo" if len(set(c)) > 1 else ""), "url": f"{b}/parlamentar/{p['id']}", "fonte": fonte})
        tipos = {t["id"]: t for t in todos(h, "materia/tipomaterialegislativa")}
        for x in todos(h, "materia/materialegislativa"):
            t = tipos.get(x.get("tipo"), {})
            M.append({"cod_ibge": cod, "sapl_id": x["id"], "tipo": t.get("descricao", ""), "sigla": t.get("sigla", ""), "numero": x.get("numero"),
                      "ano": x.get("ano"), "data_apresentacao": x.get("data_apresentacao") or "", "ementa": " ".join((x.get("ementa") or "").split())[:400],
                      "em_tramitacao": x.get("em_tramitacao"), "url": f"{b}/materia/{x['id']}", "fonte": fonte})
        autores = {a["id"]: a for a in todos(h, "base/autor")}
        tipo_autor = {t["id"]: t.get("descricao", "") for t in todos(h, "base/tipoautor")}
        for x in todos(h, "materia/autoria"):
            a = autores.get(x.get("autor"), {})
            eh_parl = "parlamentar" in tipo_autor.get(a.get("tipo"), "").lower()
            A.append({"cod_ibge": cod, "materia_id": x.get("materia"), "autor_nome": a.get("nome", ""), "autor_tipo": tipo_autor.get(a.get("tipo"), ""),
                      "sapl_parlamentar_id": a.get("object_id") if eh_parl else "", "primeiro_autor": x.get("primeiro_autor")})
        tnorma = {t["id"]: t for t in todos(h, "norma/tiponormajuridica")}
        for x in todos(h, "norma/normajuridica"):
            N.append({"cod_ibge": cod, "sapl_id": x["id"], "tipo": tnorma.get(x.get("tipo"), {}).get("descricao", ""), "numero": x.get("numero"),
                      "ano": x.get("ano"), "data": x.get("data") or "", "ementa": " ".join((x.get("ementa") or "").split())[:400],
                      "materia_id": x.get("materia") or "", "url": f"{b}/norma/{x['id']}", "fonte": fonte})
        tres = {t["id"]: t.get("nome", "") for t in todos(h, "sessao/tiporesultadovotacao")}
        for x in todos(h, "sessao/registrovotacao"):
            V.append({"cod_ibge": cod, "votacao_id": x["id"], "materia_id": x.get("materia") or "", "data": (x.get("data_hora") or "")[:10],
                      "sim": x.get("numero_votos_sim"), "nao": x.get("numero_votos_nao"), "abstencoes": x.get("numero_abstencoes"),
                      "resultado": tres.get(x.get("tipo_resultado_votacao"), ""), "fonte": fonte})
        for x in todos(h, "sessao/votoparlamentar"):
            VO.append({"cod_ibge": cod, "votacao_id": x.get("votacao") or "", "sapl_parlamentar_id": x.get("parlamentar"), "voto": x.get("voto"),
                       "data": (x.get("data_hora") or "")[:10]})
        cargos = {c["id"]: c.get("descricao", "") for c in todos(h, "parlamentares/cargomesa")}
        mesas = {m["id"]: m for m in todos(h, "parlamentares/mesadiretora")}
        sessoes = {s["id"]: s for s in todos(h, "parlamentares/sessaolegislativa")}
        for x in todos(h, "parlamentares/composicaomesa"):
            md = mesas.get(x.get("mesa_diretora"), {})
            sl = sessoes.get(md.get("sessao_legislativa"), {})
            ME.append({"cod_ibge": cod, "sapl_parlamentar_id": x.get("parlamentar"), "cargo": cargos.get(x.get("cargo"), ""),
                       "inicio": md.get("data_inicio") or sl.get("data_inicio") or "", "fim": md.get("data_fim") or sl.get("data_fim") or "",
                       "fonte": fonte})
        n_m = sum(1 for x in M if x["cod_ibge"] == cod)
        checagens.append((bool(parl) and n_m > 0, f"{mun}: {len(parl)} parlamentares ({ligados} ligados ao TSE), {n_m} matérias, "
                                                  f"{sum(1 for x in N if x['cod_ibge'] == cod)} normas, {sum(1 for x in V if x['cod_ibge'] == cod)} votações, "
                                                  f"{sum(1 for x in VO if x['cod_ibge'] == cod)} votos nominais"))
        print(mun, "ok", flush=True)
    # integridade referencial: autoria e voto apontam para matéria/parlamentar/votação existentes
    ids_m = {(x["cod_ibge"], x["sapl_id"]) for x in M}
    ids_p = {(x["cod_ibge"], x["sapl_id"]) for x in P}
    ids_v = {(x["cod_ibge"], x["votacao_id"]) for x in V}
    orf_a = sum(1 for x in A if (x["cod_ibge"], x["materia_id"]) not in ids_m)
    orf_vo = sum(1 for x in VO if (x["cod_ibge"], x["votacao_id"]) not in ids_v or (x["cod_ibge"], x["sapl_parlamentar_id"]) not in ids_p)
    checagens.append((orf_a <= 0.01 * len(A), f"autorias sem matéria correspondente: {orf_a} de {len(A)} (tolerância 1%)"))
    checagens.append((orf_vo <= 0.01 * max(len(VO), 1), f"votos sem votação ou parlamentar correspondente: {orf_vo} de {len(VO)} (tolerância 1%)"))
    gravar("parlamentares.csv", P, ["cod_ibge", "sapl_id", "nome_parlamentar", "nome_completo", "pessoa_id", "ligacao", "url", "fonte"])
    gravar("materias.csv", M, ["cod_ibge", "sapl_id", "tipo", "sigla", "numero", "ano", "data_apresentacao", "ementa", "em_tramitacao", "url", "fonte"])
    gravar("autorias.csv", A, ["cod_ibge", "materia_id", "autor_nome", "autor_tipo", "sapl_parlamentar_id", "primeiro_autor"])
    gravar("normas.csv", N, ["cod_ibge", "sapl_id", "tipo", "numero", "ano", "data", "ementa", "materia_id", "url", "fonte"])
    gravar("votacoes.csv", V, ["cod_ibge", "votacao_id", "materia_id", "data", "sim", "nao", "abstencoes", "resultado", "fonte"])
    gravar("votos.csv", VO, ["cod_ibge", "votacao_id", "sapl_parlamentar_id", "voto", "data"])
    gravar("mesa.csv", ME, ["cod_ibge", "sapl_parlamentar_id", "cargo", "inicio", "fim", "fonte"])
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "20_sapl.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — Câmaras Municipais no SAPL (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Parlamentares sem ligação ao TSE\n\n"
                + ("\n".join(f"- {muns[x['cod_ibge']]}: {x['nome_completo'] or x['nome_parlamentar']} ({x['ligacao'] or 'nenhum candidato com o nome'})"
                             for x in P if not x["pessoa_id"]) or "- nenhum")
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"parlamentares={len(P)} materias={len(M)} autorias={len(A)} normas={len(N)} votacoes={len(V)} votos={len(VO)} mesa={len(ME)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
