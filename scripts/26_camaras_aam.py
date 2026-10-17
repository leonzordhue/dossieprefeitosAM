"""O que as 61 Câmaras Municipais do interior publicam no Diário Oficial dos Municípios (AAM/SIGPub): a fonte para as
Câmaras que não têm SAPL (script 20 cobre 12) e para a posse de suplentes, que o TSE não registra.

Fonte: Diário Oficial dos Municípios do Amazonas (AAM/SIGPub), https://www.diariomunicipal.com.br/aam/
       entidades "Câmara Municipal de X"; lista por ano (pesquisar) e texto integral de cada matéria (materia/<código>).
Método:
  - todas as matérias de cada Câmara, ano a ano (2009 em diante);
  - texto integral das que interessam ao mandato (termo de posse, convocação, ata de sessão, projeto, lei, resolução,
    decreto legislativo, ato e portaria da Mesa); extratos, avisos de licitação e erratas ficam só na lista;
  - posse/convocação de suplente: matéria com "suplente" e "posse"/"convoca"/"empossad"; nomes em maiúsculas ou depois de
    "Vereador(a)/Senhor(a)" ligados (grafia estrita, regra do script 24) a candidato a vereador do município no TSE;
    papel "suplente" quando a pessoa não foi eleita no ciclo vigente; o motivo (falecimento, licença, renúncia, cassação,
    afastamento, secretaria) é o que o próprio ato diz;
  - autoria: "de autoria do(a) Vereador(a) NOME" em projetos, leis, resoluções e atas.
O resultado é sinal com o link do ato oficial: assinar ou ser citado não prova o exercício.

Saídas: dados/camaras_aam_materias.csv, dados/vereadores_suplentes_posse.csv, dados/camaras_aam_autorias.csv,
        dados/integridade/26_camaras_aam.md
Uso: python -I scripts/26_camaras_aam.py   (~1 consulta/s; respostas em dados/brutos/cache_http, retoma)
"""
import csv
import html
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

aam = import_module("24_prefeito_atos_aam")  # busca(), estrito(), NOME
decl = import_module("18_prefeito_declarado")  # palavras()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
COM_TEXTO = re.compile(r"TERMO|POSSE|CONVOCA|ATA\b|PROJETO|\bLEI\b|RESOLU|DECRETO|\bATO\b|PORTARIA", re.I)
SEM_TEXTO = re.compile(r"REGISTRO DE PRE|EXTRATO|AVISO|ERRATA|LICITA|PREG[ÃA]O|CONTRAT", re.I)
MISTO = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçü]+(?:\s+(?:d[aeo]s?|[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçü]+)){1,6}"
MOTIVOS = ("falecimento", "licença", "licenca", "renúncia", "renuncia", "cassação", "cassacao", "afastamento", "secretári", "vacância", "perda do mandato", "extinção")


def corpo(codigo):
    m = rede.get(aam.SIGPUB + "materia/" + codigo).decode("utf-8", "replace")
    i = m.find(">", m.find("documento__corpo")) + 1
    j = m.find("<footer", i)
    t = re.sub(r"<style.*?</style>|[a-z.]+\s*\{[^}]*\}", " ", m[i:j if j > 0 else None], flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


def nomes(t):
    """Nomes em maiúsculas (3+ palavras) e nomes em caixa mista logo depois de Vereador(a)/Senhor(a)/Sr(a)."""
    out = [g for g in re.findall(aam.NOME, t) if len(decl.palavras(g)) >= 3]
    out += re.findall(r"(?:Vereador(?:a|es|as)?|Senhor(?:a)?|Sr\.?|Sra\.?|Edil)\s+(" + MISTO + ")", t)
    return out


def analisa(x, t, cand):
    """Suplentes (posse/convocação) e autorias no texto de uma matéria da Câmara. x: cod_ibge, data, titulo, codigo, fonte, tipo.
    Também usada pelo script 28 (edições completas do diário)."""
    sup, aut = [], []
    cod, iso = x["cod_ibge"], x["data"]
    ciclo = max((c for c in range(2000, 2030, 4) if f"{c + 1}-01-01" <= iso), default=None)
    ligar = lambda n: next((c for c in cand[cod] if aam.estrito(n, c[1]) or (c[2] and len(decl.palavras(c[2])) >= 3 and aam.estrito(n, c[2]))), None)  # noqa: E731
    low = t.lower()
    if "suplente" in low and re.search(r"posse|empossad|convoca", low):
        rotulo = {"licenca": "licença", "renuncia": "renúncia", "cassacao": "cassação", "secretári": "titular nomeado secretário(a)"}
        motivo = ", ".join(sorted({rotulo.get(m, m) for m in MOTIVOS if m in low}))
        for n in dict.fromkeys(nomes(t)):
            c = ligar(n)
            if not c:
                continue
            eleito_ciclo = any(k[0] == c[0] and k[3] == ciclo and k[4].startswith(("ELEITO", "MÉDIA", "QP")) for k in cand[cod])
            suplente_ciclo = any(k[0] == c[0] and k[3] == ciclo for k in cand[cod]) and not eleito_ciclo
            sup.append({"cod_ibge": cod, "data": iso, "nome_no_ato": n.title(), "pessoa_id": c[0], "nome_tse": c[1], "ciclo": ciclo or "",
                              "papel": "suplente no ciclo" if suplente_ciclo else "eleito no ciclo" if eleito_ciclo else "outro ciclo",
                              "motivo_no_ato": motivo, "titulo": x["titulo"], "codigo": x["codigo"], "fonte": x["fonte"]})
    # "Autoria do Vereador X", "autoria da vereadora X", "Autor: Ver. X", "proposto pelo Vereador X" (só o prefixo ignora caixa)
    for n in re.findall(r"(?i:(?:autoria\s+d[oae]s?|autor[a]?\s*:|propost[oa]\s+pel[oa]|de\s+iniciativa\s+d[oa])\s+(?:nobre\s+)?"
                        r"(?:vereador(?:a)?|edil|ver\.)(?:\s+d[oa]\s+vereador(?:a)?)?)\s+(" + MISTO + "|" + aam.NOME + ")", t):
        c = ligar(n)
        if c:
            aut.append({"cod_ibge": cod, "data": iso, "nome_no_ato": n.title(), "pessoa_id": c[0], "nome_tse": c[1], "tipo": x["tipo"],
                             "titulo": x["titulo"], "codigo": x["codigo"], "fonte": x["fonte"]})
    return sup, aut


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    por_nome = {" ".join(decl.palavras(m["municipio"])): m for m in muns}
    cand = defaultdict(list)  # cod -> [(pessoa_id, nome, nome_urna, ciclo, resultado)]
    for r in csv.DictReader(open(os.path.join(DADOS, "candidaturas_vereador.csv"), encoding="utf-8")):
        cand[r["cod_ibge"]].append((r["pessoa_id"], r["nome"], r["nome_urna"], int(r["ciclo"]), r["resultado"].upper()))
    b = rede.get(aam.SIGPUB + "pesquisar").decode("utf-8", "replace")
    sel = re.search(r'name="busca_avancada\[entidade\]".*?</select>', b, re.S).group(0)
    camaras = {}
    for v, t in re.findall(r'<option value="([^"]*)"[^>]*>([^<]+)</option>', sel):
        t = html.unescape(t).strip()
        if t.startswith("Câmara Municipal de "):
            m = por_nome.get(" ".join(decl.palavras(t[len("Câmara Municipal de "):])))
            if m:
                camaras[m["cod_ibge"]] = v
    checagens, alertas = [(len(camaras) >= 60, f"{len(camaras)} Câmaras com entidade no SIGPub/AAM")], []

    # 1) lista de todas as matérias, ano a ano (o SIGPub corta em 10.000 por busca)
    materias, totais = [], {}
    hoje = date.today()
    for cod, ent in sorted(camaras.items()):
        _, totais[cod] = aam.busca(entidade=ent, ini="2009-01-01")
        for ano in range(2009, hoje.year + 1):
            pag = 1
            while True:
                try:
                    cards, tot = aam.busca(entidade=ent, ini=f"{ano}-01-01", fim=min(f"{ano}-12-31", hoje.isoformat()), pagina=pag)  # data futura: o SIGPub devolve vazio
                except Exception as e:
                    alertas.append(f"{cod} {ano} página {pag}: {e.__class__.__name__}")
                    break
                for c in cards:
                    d = c["data"]
                    materias.append({"cod_ibge": cod, "data": f"{d[6:10]}-{d[3:5]}-{d[0:2]}" if re.fullmatch(r"\d{2}/\d{2}/\d{4}", d) else "",
                                     "tipo": re.split(r"[\s\-–Nº°0-9/]+", c["titulo"].upper().strip() + " ")[0], "titulo": c["titulo"][:200],
                                     "codigo": c["codigo"], "fonte": f"{aam.SIGPUB}materia/{c['codigo']}"})
                if not cards or pag * 25 >= tot:
                    break
                pag += 1
        print(cod, len(materias), flush=True)
    vistos = set()
    materias = [x for x in materias if not (x["codigo"] in vistos or vistos.add(x["codigo"]))]
    lidas = sum(1 for x in materias if x["cod_ibge"] in totais)
    checagens.append((lidas >= 0.98 * sum(totais.values()), f"matérias listadas: {lidas} de {sum(totais.values())} anunciadas pelo SIGPub"))

    # 2) texto integral do que interessa ao mandato
    suplentes, autorias, com_texto, falhas = [], [], 0, 0
    for x in materias:
        if not COM_TEXTO.search(x["titulo"]) or SEM_TEXTO.search(x["titulo"]):
            continue
        url = aam.SIGPUB + "materia/" + x["codigo"]
        if not rede.em_cache(url):
            time.sleep(0.5)
        try:
            t = corpo(x["codigo"])
        except Exception as e:
            falhas += 1
            alertas.append(f"{x['codigo']}: {e.__class__.__name__}")
            continue
        com_texto += 1
        x["texto"] = t
        sup, aut = analisa(x, t, cand)
        suplentes += sup
        autorias += aut
        if com_texto % 200 == 0:
            print("texto", com_texto, len(suplentes), len(autorias), flush=True)
    alvo = sum(1 for x in materias if COM_TEXTO.search(x["titulo"]) and not SEM_TEXTO.search(x["titulo"]))
    checagens.append((com_texto >= 0.97 * alvo, f"texto integral lido: {com_texto} de {alvo} matérias de mandato ({falhas} falhas)"))
    vistos = set()
    suplentes = [s for s in suplentes if not ((s["codigo"], s["pessoa_id"]) in vistos or vistos.add((s["codigo"], s["pessoa_id"])))]
    autorias = [s for s in autorias if not ((s["codigo"], s["pessoa_id"]) in vistos or vistos.add((s["codigo"], s["pessoa_id"])))]
    checagens.append((sum(s["papel"] == "suplente no ciclo" for s in suplentes) >= 30, f"suplentes do ciclo em atos de posse/convocação: "
                      f"{len({(s['cod_ibge'], s['pessoa_id']) for s in suplentes if s['papel'] == 'suplente no ciclo'})} pessoas"))
    checagens.append((len({s["cod_ibge"] for s in autorias}) >= 20, f"autorias de vereador: {len(autorias)} em {len({s['cod_ibge'] for s in autorias})} Câmaras"))

    def grava(nome, linhas, campos):
        with open(os.path.join(DADOS, nome), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(linhas, key=lambda r: (r["cod_ibge"], r["data"])))
    grava("camaras_aam_materias.csv", materias, ["cod_ibge", "data", "tipo", "titulo", "codigo", "fonte"])
    grava("vereadores_suplentes_posse.csv", suplentes, ["cod_ibge", "data", "nome_no_ato", "pessoa_id", "nome_tse", "ciclo", "papel", "motivo_no_ato", "titulo", "codigo", "fonte"])
    grava("camaras_aam_autorias.csv", autorias, ["cod_ibge", "data", "nome_no_ato", "pessoa_id", "nome_tse", "tipo", "titulo", "codigo", "fonte"])
    muni = {m["cod_ibge"]: m["municipio"] for m in muns}
    for s in suplentes:
        if s["papel"] == "suplente no ciclo":
            alertas.append(f"{muni[s['cod_ibge']]} {s['data']}: suplente {s['nome_tse']} ({s['pessoa_id']}) em ato de posse/convocação"
                           f"{' — ' + s['motivo_no_ato'] if s['motivo_no_ato'] else ''} ({s['fonte']})")
    tipos = Counter(x["tipo"] for x in materias)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "26_camaras_aam.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — Câmaras no Diário Oficial dos Municípios (AAM/SIGPub) (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Matérias: {len(materias)}; tipos mais comuns: {', '.join(f'{k} {v}' for k, v in tipos.most_common(12))}\n"
                f"- Posse/convocação ligadas: {len(suplentes)}; autorias: {len(autorias)}\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Conferir\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas[:400]) or "- nenhum") + "\n")
    print(f"materias={len(materias)} suplentes={len(suplentes)} autorias={len(autorias)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        t = corpo("62B057F7")
        print(len(t), t[:200])
        assert nomes("compareceu o Senhor SINEY DA MATA DOS SANTOS, diplomado") == ["SINEY DA MATA DOS SANTOS"]
        assert "Francisco Raimundo Gomes Pereira" in nomes("e Membro o Vereador Francisco Raimundo Gomes Pereira e para")
        print("ok")
    else:
        main()
