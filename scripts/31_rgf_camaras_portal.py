"""Despesa com pessoal das Câmaras (RGF Anexo I do Poder Legislativo) pelo Portal de Transparência dos Municípios da AAM,
onde o SICONFI não tem o RGF do Legislativo (2013–2017 e buracos isolados).

Fonte: https://transparenciamunicipalaam.org.br/camaras → /p/<camara>/t/informacoes-financeiras → "Relatorio De Gestao Fiscal"
       → <ano> → último período do ano (2º semestre ou 3º quadrimestre) → PDF do demonstrativo da despesa com pessoal
       (lista de arquivos por POST /get-files-list, com o token da página).
Método: no texto do PDF, "TOTAL DA DESPESA COM PESSOAL PARA FINS DE APURAÇÃO DO LIMITE – TDP (III) = (I – II)" seguido do
valor liquidado e dos restos a pagar não processados (no fim do ano os dois contam, LRF art. 18 § 2º; nota do próprio anexo).
Só 2013–2017: de 2018 em diante o anexo tem uma coluna por mês e o SICONFI tem os números. Valor maior que a despesa da
função Legislativa do ano (a folha é parte dela) é descartado como leitura errada.
O % sobre a RCL vem zerado em muitos relatórios de Câmara: é recalculado com a RCL do município (dados/indicadores/financas.csv)
e marcado como calculado.
Conferência: onde o SICONFI também tem o valor, os dois devem bater (±2%).

Saídas: dados/indicadores/camaras_rgf_portal.csv, dados/integridade/31_rgf_camaras_portal.md
Uso: python -I scripts/31_rgf_camaras_portal.py
"""
import csv
import http.cookiejar
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
SITE = "https://transparenciamunicipalaam.org.br"
UA = {"User-Agent": "Mozilla/5.0 (pesquisa dossieprefeitosAM)"}
# modelo antigo: "TOTAL DA DESPESA COM PESSOAL PARA FINS DE APURAÇÃO DO LIMITE – TDP (III) = (I – II)";
# modelo do MDF 6ª ed. em diante: "DESPESA TOTAL COM PESSOAL - DTP (III) = (I + II)" (a 2ª coluna, RAP não processados, pode faltar)
# modelo de 2016: "DESPESA LÍQUIDA COM PESSOAL (III) = (I – II)" (o DTP vira a linha V, em %)
TDP = re.compile(r"(?:TOTAL DA DESPESA COM PESSOAL PARA FINS DE APURA\S+O DO LIMITE|DESPESA TOTAL COM PESSOAL\s*\S?\s*DTP|DESPESA L\S+QUIDA COM PESSOAL).{0,40}?"
                 r"\(III\)\s*=\s*\(I\s*\S\s*II\)\s*([\d.]+,\d{2})\s+([\d.]+,\d{2})?", re.I)


def chave(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


def num(s):
    return float(s.replace(".", "").replace(",", ".")) if s else 0.0


class Portal:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(self, url, dados=None, ref=None):
        h = dict(UA, **({"X-Requested-With": "XMLHttpRequest", "Referer": ref} if dados else {}))
        for i in range(3):
            try:
                return self.op.open(urllib.request.Request(url, data=dados, headers=h), timeout=90).read()
            except Exception:
                time.sleep(3 * (i + 1))
        raise RuntimeError(url)

    def periodos_rgf(self, slug):
        """{ano: [(rótulo do período, data-path)]} e o token da página."""
        url = f"{SITE}/p/{slug}/t/informacoes-financeiras"
        p = self.get(url).decode("utf-8", "replace")
        tok = re.search(r'_token:\s*"([^"]+)"', p)
        i = p.find("Relatorio De Gestao Fiscal")
        if i < 0 or not tok:
            return {}, None, url
        fim = min([j for j in (p.find("Relatorio Resumido", i), p.find("Balanco", i), p.find("Lei De", i)) if j > 0] or [len(p)])
        anos, atual = {}, None
        for path, rot in re.findall(r'<label data-path="([^"]+)" for="[^"]+">([^<]+)</label>', p[i:fim]):
            rot = " ".join(rot.split())
            if re.fullmatch(r"\d{4}", rot):
                atual = int(rot)
                anos[atual] = []
            elif atual:
                anos[atual].append((rot, urllib.parse.unquote(path)))
        return anos, tok.group(1), url

    def arquivos(self, path, tok, ref):
        r = self.get(f"{SITE}/get-files-list", urllib.parse.urlencode({"path": path, "_token": tok}).encode(), ref)
        return json.loads(r).get("data") or []


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    por_chave = {chave(m["municipio"]): m for m in muns}
    fin = {(r["cod_ibge"], int(r["ano"])): r for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "financas.csv"), encoding="utf-8"))}
    sic = {(r["cod_ibge"], int(r["ano"])): float(r["camara_pessoal"]) for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "camaras_financas.csv"), encoding="utf-8"))
           if r["camara_pessoal"] not in ("", None) and "rgf?" in r["fonte_rgf"]}
    pt = Portal()
    pagina = pt.get(f"{SITE}/camaras").decode("utf-8", "replace")
    slugs = sorted(set(re.findall(r'href="https://transparenciamunicipalaam.org.br/p/([a-z0-9\-]+-camara)"', pagina)))
    linhas, alertas, sem_rgf = [], [], []
    for slug in slugs:
        m = por_chave.get(chave(slug[:-len("-camara")]))
        if not m:
            alertas.append(f"{slug}: município não reconhecido")
            continue
        try:
            anos, tok, ref = pt.periodos_rgf(slug)
        except Exception as e:
            alertas.append(f"{slug}: {e.__class__.__name__}")
            continue
        if not anos:
            sem_rgf.append(m["municipio"])
        for ano, pers in sorted(anos.items()):
            if ano > 2017:  # de 2018 em diante o anexo traz uma coluna por mês (o regex leria um mês) e o SICONFI já tem os números
                continue
            fim_ano = [p for p in pers if re.match(r"0?2\s*Semestre|0?3\s*Quadrimestre", p[0], re.I)]
            achou, tentou = False, False
            for rotulo, path in fim_ano:  # pode haver "02 Semestre" vazio e "03 Quadrimestre" com o arquivo (Coari 2016)
                try:
                    arqs = pt.arquivos(path, tok, ref)
                except Exception as e:
                    alertas.append(f"{m['municipio']} {ano} {rotulo}: lista de arquivos falhou ({e.__class__.__name__})")
                    continue
                arqs = sorted([a for a in arqs if a["arquivo"].lower().endswith(".pdf")], key=lambda a: ("PESSOAL" not in a["arquivo"].upper(), a["arquivo"]))
                tentou = tentou or bool(arqs)
                for a in arqs[:5]:
                    url = SITE + urllib.parse.quote(a["path"])
                    try:
                        b = rede.get(url)
                        t = " ".join("".join(pg.get_text() for pg in pymupdf.open(stream=b, filetype="pdf")).split())
                    except Exception:
                        continue
                    g = TDP.search(t)
                    if not g:
                        continue
                    dtp = num(g.group(1)) + num(g.group(2))
                    leg = fin.get((m["cod_ibge"], ano), {}).get("desp_legislativa")
                    if leg and dtp > float(leg) * 1.02:  # a folha é parte da despesa da Câmara: maior que ela é leitura errada
                        alertas.append(f"{m['municipio']} {ano}: pessoal lido R$ {dtp:,.2f} > despesa da função Legislativa R$ {float(leg):,.2f}; descartado")
                        continue
                    rcl = fin.get((m["cod_ibge"], ano), {}).get("rcl")
                    rcl = float(rcl) if rcl else None
                    linhas.append({"cod_ibge": m["cod_ibge"], "municipio": m["municipio"], "ano": ano, "periodo": rotulo,
                                   "camara_pessoal": round(dtp, 2), "rcl_municipio": rcl or "", "pct_rcl_calculado": round(100 * dtp / rcl, 2) if rcl else "",
                                   "arquivo": a["arquivo"], "fonte": f"Portal de Transparência dos Municípios (AAM), RGF da Câmara {ano} {rotulo}: {url}"})
                    achou = True
                    break
                if achou:
                    break
            if tentou and not achou:
                alertas.append(f"{m['municipio']} {ano}: há PDFs no fim do ano, mas o total da despesa com pessoal não foi lido")
        print(slug, len(linhas), flush=True)
    bate = [(x, sic[(x["cod_ibge"], x["ano"])]) for x in linhas if (x["cod_ibge"], x["ano"]) in sic]
    ok_b = [x for x, s in bate if s and abs(x["camara_pessoal"] - s) / s <= 0.02]
    for x, s in bate:
        if s and abs(x["camara_pessoal"] - s) / s > 0.02:
            alertas.append(f"{x['municipio']} {x['ano']}: portal R$ {x['camara_pessoal']:,.2f} × SICONFI R$ {s:,.2f}")
    novos = [x for x in linhas if (x["cod_ibge"], x["ano"]) not in sic]
    checagens = [(len(slugs) >= 30, f"Câmaras no portal da AAM: {len(slugs)}"),
                 (not bate or len(ok_b) >= 0.8 * len(bate), f"portal = SICONFI (±2%) onde os dois existem: {len(ok_b)} de {len(bate)}"),
                 (len(novos) > 0, f"Câmara-anos que o SICONFI não tem e o portal tem: {len(novos)}")]
    with open(os.path.join(DADOS, "indicadores", "camaras_rgf_portal.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "municipio", "ano", "periodo", "camara_pessoal", "rcl_municipio", "pct_rcl_calculado", "arquivo", "fonte"])
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda x: (x["cod_ibge"], x["ano"])))
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "31_rgf_camaras_portal.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — RGF das Câmaras pelo portal da AAM (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + f"\n\nCâmaras sem pasta de RGF no portal: {', '.join(sem_rgf) or 'nenhuma'}\n\n## Alertas\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in alertas[:300]) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} novos={len(novos)} confere={len(ok_b)}/{len(bate)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        t = "TOTAL DA DESPESA COM PESSOAL PARA FINS DE APURAÇÃO DO LIMITE – TDP (III) = (I – II) 532.566,26 0,00 RECEITA"
        g = TDP.search(t)
        assert g and num(g.group(1)) == 532566.26 and num(g.group(2)) == 0, g
        assert chave("atalaiadonorte") == chave("Atalaia do Norte")
        print("ok")
    else:
        main()
