"""Quem assinou os atos da prefeitura, trimestre a trimestre (2009 em diante): sinal de interinos, vices no exercício e
sucessões que o TSE não registra. Complementa o script 18 (SIOPE).

Fonte: Diário Oficial dos Municípios do Amazonas (AAM/SIGPub), busca pública
       https://www.diariomunicipal.com.br/aam/pesquisar (matérias desde 2009; 61 municípios; Manaus publica em diário próprio).
Método:
  - amostra: para cada município e trimestre, os 25 primeiros atos com "DECRETO" no título e "prefeito" no texto.
    O trecho de cada ato traz quem o expede ("O Prefeito de Envira, IVON RATES DA SILVA, no exercício...") ou a
    assinatura ("NOME, Prefeito(a) Municipal ... em exercício").
  - alvos: buscas inteiras por "prefeito interino", "prefeita interina", "presidente da Câmara" + "cargo de prefeito" e
    cassação/perda/extinção de mandato de prefeito.
  - O nome só é aceito quando casa (a menos de grafia, regra do script 18) com um candidato a prefeito, vice ou vereador
    do mesmo município no TSE; o papel é comparado com o mandato vigente na data (titular, vice, outro).
O trecho é recortado pelo SIGPub: ato sem nome no trecho não entra. Assinar um ato não prova a titularidade (o vice assina
quando o titular viaja): o resultado é sinal a conferir, com o link do ato oficial.

Saídas: dados/prefeito_atos_aam.csv, dados/integridade/24_prefeito_atos_aam.md
Uso: python -I scripts/24_prefeito_atos_aam.py   (~1 consulta/s, respostas em dados/brutos/cache_http)
"""
import csv
import html
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from importlib import import_module
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

decl = import_module("18_prefeito_declarado")  # mesmo(), palavras()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
SIGPUB = "https://www.diariomunicipal.com.br/aam/"
ALVOS = ('"prefeito interino"', '"prefeita interina"', '"presidente da câmara" "cargo de prefeito"',
         '"cassação" "mandato" prefeito', '"perda do mandato" prefeito', '"extinção do mandato" prefeito')
# sem a partícula "E": em listas de assinatura ("FULANO E BELTRANO") ela juntaria duas pessoas
NOME = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇÜ][A-ZÁÉÍÓÚÂÊÔÃÕÇÜ'.]+(?:\s+(?:D[AEO]S?|[A-ZÁÉÍÓÚÂÊÔÃÕÇÜ][A-ZÁÉÍÓÚÂÊÔÃÕÇÜ'.]+)){1,7}"
CONDICAO = re.compile(r"em\s+exerc[ií]cio|interin[oa]|no\s+exerc[ií]cio\s+do\s+cargo\s+de\s+prefeit", re.I)


def busca(texto="", titulo="", entidade="", ini="2009-01-01", fim=None, pagina=1, ordem="antiga"):
    q = {"busca_avancada[texto]": texto, "busca_avancada[titulo]": titulo, "busca_avancada[entidade]": entidade,
         "busca_avancada[orgao]": "", "busca_avancada[dataInicio]": ini, "busca_avancada[dataFim]": fim or date.today().isoformat(),
         "busca_avancada[ordenacao]": ordem, "busca_avancada[Enviar]": "", "busca_avancada[pagina]": str(pagina)}
    url = SIGPUB + "pesquisar?" + urlencode(q)
    if not rede.em_cache(url):
        time.sleep(1)
    b = rede.get(url).decode("utf-8", "replace")
    tot = re.search(r"de\s*<strong>([\d.]+)</strong>\s*mat", b)
    cards = []
    for c in re.findall(r'<li class="materia-card">(.*?)</li>\s*(?=<li class="materia-card">|</ul>)', b, re.S):
        g = lambda rx: html.unescape(re.sub(r"<[^>]+>", "", (re.search(rx, c, re.S) or [None, ""])[1])).strip()  # noqa: E731
        cards.append({"codigo": g(r"<code>([0-9A-F]+)</code>"), "titulo": g(r'materia-card__titulo">(.*?)</h2>'),
                      "entidade": g(r'materia-card__entidade">(.*?)</span>'), "trecho": " ".join(g(r'materia-card__trecho">(.*?)</p>').split()),
                      "data": g(r"Circula\S*</dt>\s*<dd>(.*?)</dd>")})
    return cards, int(tot[1].replace(".", "")) if tot else 0


def nomes_no_trecho(t):
    """Nomes (em maiúsculas, 3+ palavras) colados à palavra Prefeito/Prefeita, com a condição (em exercício, interino):
    "O Prefeito de X, NOME, no uso..." (nome até ~40 caracteres depois) ou "NOME, Prefeito Municipal" (assinatura, até ~15 antes).
    Nome solto no texto, longe do cargo, não entra (evita secretários, servidores e cabeçalhos)."""
    out = []
    for m in re.finditer(r"prefeit[oa]", t, re.I):
        cond = CONDICAO.search(t[m.start():m.end() + 60]) or CONDICAO.search(t[max(0, m.start() - 60):m.start()])
        cond = cond.group(0).lower() if cond else ""
        # só o prefixo ignora maiúsculas; o nome tem de vir em maiúsculas
        depois = re.match(r"(?i:(?:\s+municipal)?(?:\s+(?:de|do|da)\s+[^,;:]{2,40}?)?(?:\s+em\s+exerc[ií]cio)?[\s,–\-]*"
                          r"(?:o\s+senhor|a\s+senhora|sr\.?|sra\.?)?)[\s,–\-]*(" + NOME + ")", t[m.end():m.end() + 140])
        antes = re.search("(" + NOME + r")[\s,–\-]{0,4}$", t[max(0, m.start() - 90):m.start()])
        for g in (depois.group(1) if depois else None, antes.group(1) if antes else None):
            if not g:
                continue
            g = re.sub(r"(?:\s+E|\.)$", "", g.strip())
            g = re.sub(r"^(?:(?:NOME|CARGO|FUN[ÇC][ÃA]O|SIMBOLOGIA|ANEXO|MUNICIPAL\.?|ESTADO DO AMAZONAS|AM\.)\s+)+", "", g)  # cabeçalho grudado
            if len(decl.palavras(g)) >= 3 and g.upper() == g:
                out.append((g, cond))
    return out


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    por_nome_mun = {decl.palavras(m["municipio"]) and " ".join(decl.palavras(m["municipio"])): m for m in muns}
    cand = defaultdict(dict)  # cod -> pessoa_id -> nome (prefeito, vice e vereador no TSE)
    for arq in ("candidaturas_prefeito.csv", "candidaturas_vereador.csv"):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            cand[r["cod_ibge"]][r["pessoa_id"]] = r["nome"]
    mand = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")):
        mand[r["cod_ibge"]].append(r)
    # entidades "Município de X" do SIGPub
    b = rede.get(SIGPUB + "pesquisar").decode("utf-8", "replace")
    sel = re.search(r'name="busca_avancada\[entidade\]".*?</select>', b, re.S).group(0)
    entidades = {}
    for v, t in re.findall(r'<option value="([^"]*)"[^>]*>([^<]+)</option>', sel):
        t = html.unescape(t).strip()
        if t.startswith("Município de "):
            m = por_nome_mun.get(" ".join(decl.palavras(t[len("Município de "):])))
            if m:
                entidades[m["cod_ibge"]] = v
    checagens, alertas = [(len(entidades) >= 60, f"{len(entidades)} municípios com entidade no SIGPub/AAM")], []

    linhas, vistos, trimestres_com = [], set(), defaultdict(set)

    def registra(cod, card, origem):
        d = card["data"]
        iso = f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if re.fullmatch(r"\d{2}/\d{2}/\d{4}", d) else ""
        for nome, cond in nomes_no_trecho(card["trecho"]):
            vig = next((x for x in mand[cod] if x["inicio"] <= iso <= x["fim_previsto"]), None)
            # o titular/vice do mandato vigente tem preferência (a mesma pessoa pode ter dois pessoa_id, um por título de eleitor)
            pid = (vig["pessoa_id"] if vig and decl.mesmo(nome, vig["prefeito"]) else vig["vice_pessoa_id"] if vig and vig["vice"] and decl.mesmo(nome, vig["vice"])
                   else next((p for p, n in cand[cod].items() if decl.mesmo(nome, n)), ""))
            if not pid:
                continue
            papel = ("titular" if vig and pid == vig["pessoa_id"] else "vice" if vig and pid == vig["vice_pessoa_id"] else "outro")
            k = (cod, iso, pid, card["codigo"])
            if k in vistos:
                continue
            vistos.add(k)
            trimestres_com[cod].add(iso[:4] + "T" + str((int(iso[5:7]) + 2) // 3))
            linhas.append({"cod_ibge": cod, "data": iso, "nome_no_ato": nome.title(), "condicao": cond, "papel": papel, "pessoa_id": pid,
                           "titular_tse": vig["prefeito"] if vig else "", "titulo": card["titulo"][:160], "codigo": card["codigo"],
                           "origem": origem, "fonte": f"Diário Oficial dos Municípios do AM (AAM/SIGPub), {SIGPUB}materia/{card['codigo']}"})

    hoje = date.today()
    for cod, ent in sorted(entidades.items()):
        for ano in range(2009, hoje.year + 1):
            for t in range(4):
                ini = date(ano, 3 * t + 1, 1)
                if ini > hoje:
                    break
                fim = date(ano + (t == 3), 1 if t == 3 else 3 * t + 4, 1) - timedelta(days=1)
                try:
                    # com a palavra-chave, o trecho do SIGPub se centra em "Prefeito" (sem ela mostra só o começo do ato)
                    cards, _ = busca(texto="prefeito", titulo="DECRETO", entidade=ent, ini=ini.isoformat(), fim=fim.isoformat())
                except Exception as e:
                    alertas.append(f"{cod} {ano}T{t + 1}: {e.__class__.__name__}")
                    continue
                for c in cards:
                    registra(cod, c, "amostra trimestral de decretos")
        print(cod, len(linhas), flush=True)
    for q in ALVOS:
        pag, total = 1, None
        while True:
            try:
                cards, total = busca(texto=q, pagina=pag, ordem="antiga")
            except Exception as e:
                alertas.append(f"busca {q} página {pag}: {e.__class__.__name__}")
                break
            for c in cards:
                m = por_nome_mun.get(" ".join(decl.palavras(c["entidade"].replace("Município de ", "").replace("Câmara Municipal de ", ""))))
                if m:
                    registra(m["cod_ibge"], c, f"busca {q}")
            if not cards or pag * 25 >= min(total or 0, 10000):
                break
            pag += 1
        checagens.append((total is not None, f"busca {q}: {total} matérias"))
    linhas.sort(key=lambda x: (x["cod_ibge"], x["data"]))
    with open(os.path.join(DADOS, "prefeito_atos_aam.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "data", "nome_no_ato", "condicao", "papel", "pessoa_id", "titular_tse", "titulo", "codigo", "origem", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    cobertos = sum(len(v) for v in trimestres_com.values())
    possiveis = len(entidades) * ((hoje.year - 2009) * 4 + (hoje.month + 2) // 3)
    checagens.append((cobertos >= 0.3 * possiveis, f"trimestres com ao menos um assinante identificado: {cobertos} de {possiveis}"))
    outros = defaultdict(list)
    for x in linhas:
        if x["papel"] == "outro":
            outros[(x["cod_ibge"], x["pessoa_id"], x["nome_no_ato"])].append(x["data"])
    muni = {m["cod_ibge"]: m["municipio"] for m in muns}
    for (cod, pid, nome), ds in sorted(outros.items(), key=lambda k: (k[0][0], min(k[1]))):
        alertas.append(f"{muni[cod]}: {nome} ({pid}) assina como prefeito(a) sem ser titular nem vice no TSE: {len(ds)} ato(s), "
                       f"{min(ds)} a {max(ds)}")
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "24_prefeito_atos_aam.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — quem assina os atos da prefeitura (AAM/SIGPub) (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Linhas: {len(linhas)} (titular {sum(x['papel'] == 'titular' for x in linhas)}, vice {sum(x['papel'] == 'vice' for x in linhas)}, "
                f"outro {sum(x['papel'] == 'outro' for x in linhas)})\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Assinaram como prefeito(a) sem ser titular nem vice (conferir)\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:  # amostra pequena para conferir a extração
        cards, tot = busca(titulo="DECRETO", entidade="3197", ini="2021-01-01", fim="2021-03-31")
        print(tot, "matérias")
        for c in cards[:8]:
            print(c["data"], c["codigo"], nomes_no_trecho(c["trecho"]), "|", c["trecho"][:140])
    else:
        main()
