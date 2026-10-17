"""Despesa com pessoal das Câmaras (RGF do Legislativo) pela análise técnica do TCE-AM nas prestações de contas anuais,
onde o SICONFI não tem números (2013–2017: a Câmara entregou o RGF ao Tesouro só em PDF).

Fonte: consulta pública de processos do TCE-AM (DEC) — https://dec-api.tceam.tc.br/api/v1/consultas-publicas/processos
       (unidade gestora "Câmara Municipal de X", natureza "Prestação de Contas Anual") → url-visualizador → visualizador
       público do processo (https://spede-api-visualizador.tce.am.gov.br/api/v2/visualizador/, com a sessão que o próprio
       DEC entrega) → documentos da análise da DICAR ("Relatório de Gestão Fiscal relativo ao assunto Despesa com pessoal").
Método: na análise, o "Quadro – Dados de Gastos com Pessoal (GEFIS)" traz, por quadrimestre ou semestre, a RCL dos últimos 12
meses, a "XII - Despesa Líquida com Pessoal" e o "XIII - % ... sobre a RCL", com os dados que a Câmara enviou ao TCE (GEFIS).
O último período do ano (3º quadrimestre ou 2º semestre) é o ano inteiro. O valor é o do RGF enviado; a mesma análise compara com
a prestação de contas e aponta diferença quando há (vira alerta).

Saídas: dados/indicadores/camaras_rgf_tce.csv, dados/integridade/32_rgf_camaras_tce.md
Uso: python -I scripts/32_rgf_camaras_tce.py   (texto das páginas guardado em dados/brutos/tce_rgf/, retoma)
"""
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pymupdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
CACHE = os.path.join(DADOS, "brutos", "tce_rgf")
DEC = "https://dec-api.tceam.tc.br/api/v1/consultas-publicas/"
VIS = "https://spede-api-visualizador.tce.am.gov.br/api/v2/visualizador/"
APP_ID = "gzEU54acvOrUN3K63jHyQKXFsBpDsamJSfVMxocdFYk9LNyAUWMRlOSf7OFkhOu7"  # cabeçalho fixo do visualizador público
ANOS = range(2013, 2018)
DOC = re.compile(r"(?i)gest.o fiscal|pessoal|laudo|relat.rio (?:t.cnico|conclusivo|de an.lise)|informa..o t.cnica|an.lise")
NUM = r"-?\d[\d.]*,\d{2}"  # aceita milhar malformado ("1672.620,07")
# a fórmula "= VI+VII+VIII+IX+X–XI" aparece em uns modelos e não em outros (Anamã 2016: "XII - Despesa Líquida com Pessoal 658.539,82 687.809,35")
# variações: com ou sem a fórmula "= VI+...–XI", "(R$)" no rótulo, "R$" antes de cada valor
LINHA_XII = re.compile(r"XII\s*-\s*Despesa L.quida com Pessoal(?:\s*=\s*VI[^0-9]{0,40}?XI)?\s*(?:\(R\$\))?\s*((?:(?:R\$\s*)?" + NUM + r"\s*)+)", re.I)
LINHA_XIII = re.compile(r"XIII\s*-\s*%.{0,100}?(?:\*\s*100|RCL)\s*((?:\d{1,3},\d{2}\s*%?\s*)+)", re.I)  # "... = IX/I*100 3,31 3,64 3,35" ou "4,97% 4,40%"
LINHA_I = re.compile(r"\bI\s*-\s*Receita Corrente L.quida.{0,40}?meses\s*(?:\(R\$\))?\s*((?:(?:R\$\s*)?" + NUM + r"\s*)+)", re.I)  # "... - Últimos 12 meses 213.088.532,83 ..."


def chave(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


def num(s):
    return float(s.replace(".", "").replace(",", "."))


def get(url, h=None, tentativas=3):
    for i in range(tentativas):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=dict({"User-Agent": "Mozilla/5.0 (pesquisa dossieprefeitosAM)"}, **(h or {}))), timeout=120).read()
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(4 * (i + 1))


def dec(path):
    return json.loads(get(DEC + path, {"Accept": "application/json"}))


def paginas(id_proc):
    """Texto das páginas dos documentos de análise do processo: [(descrição, nº da página, texto, url)]."""
    sid = re.search(r"sessionId=([0-9a-f]+)", get(DEC + f"url-visualizador/{id_proc}").decode()).group(1)
    h = {"Authorization": "Bearer " + sid, "app-id": APP_ID, "Referer": "https://visualizador-spede2.tce.am.gov.br/", "Accept": "application/json, text/plain, */*"}
    hier = json.loads(get(VIS + f"hierarquiaPaginacaoEscrito/{id_proc}", h))
    docs = []

    def anda(lista):
        for x in lista:
            docs.append(x)
            anda(x.get("listaHierarquia") or [])
    for topo in hier["listaHierarquiaPrincipal"]:
        anda(topo["data"].get("listaHierarquia") or [])
    alvo = sorted([d for d in docs if DOC.search(d.get("descricao") or "")], key=lambda d: (not re.search(r"(?i)gest.o fiscal|pessoal", d["descricao"]), d["paginaInicial"]))
    for d in alvo:
        for pg in range(1, (d.get("numeroPaginas") or 0) + 1):
            arq = os.path.join(CACHE, f"{d['idEscrito']}_{pg}.txt")
            url = VIS + f"obterArquivo/{d['idEscrito']}/tipo/1/temp/1/pg/{pg}?user=Consulta%20p%C3%BAblica%20de%20processos"
            if os.path.exists(arq):
                t = open(arq, encoding="utf-8").read()
            else:
                try:
                    t = " ".join("".join(p.get_text() for p in pymupdf.open(stream=get(url, h), filetype="pdf")).split())
                except Exception:
                    continue
                with open(arq, "w", encoding="utf-8") as f:
                    f.write(t)
            yield d["descricao"].strip(), d["paginaInicial"] + pg - 1, t, url


def main():
    os.makedirs(CACHE, exist_ok=True)
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    por_chave = {chave(m["municipio"]): m for m in muns}
    ugs = dec("unidades-gestoras")
    camaras = {}
    for u in ugs:
        n = u["nome"]
        if re.match(r"(?i)c.mara municipal de ", n):
            m = por_chave.get(chave(re.sub(r"(?i)^c.mara municipal de ", "", n)))
            if m:
                camaras[m["cod_ibge"]] = (u["id"], m["municipio"])
    nat = next(x["idCategoria"] for x in dec("naturezas") if x["descricao"] == "Prestação de Contas Anual")
    linhas, alertas, sem_quadro, achados = [], [], [], []
    def camara(cod, ug, nome):
        try:
            procs = dec("processos?" + urllib.parse.urlencode({"idOrgao": ug, "idNatureza": nat, "itens": 100}))["content"]
        except Exception as e:
            alertas.append(f"{nome}: lista de processos falhou ({e.__class__.__name__})")
            return
        for p in procs:
            ex = re.search(r"EXERC.CIO\D{0,8}(\d{4})", p.get("objeto") or "", re.I)
            if not ex or int(ex.group(1)) not in ANOS or not p.get("isEletronico"):
                continue
            ano = int(ex.group(1))
            if any(x["cod_ibge"] == cod and x["ano"] == ano for x in linhas):
                continue
            achados.append(1)
            try:
                for desc, pagina, t, url in paginas(p["idProcesso"]):
                    g = LINHA_XII.search(t)
                    if not g:
                        continue
                    vals = re.findall(NUM, g.group(1))
                    pct = LINHA_XIII.search(t)
                    rcl = LINHA_I.search(t)
                    dlp = num(vals[-1]) if len(vals) <= 3 else num(vals[len(vals) // 2 - 1])  # com a coluna "prestação de contas" ao lado, fica a do GEFIS
                    linhas.append({"cod_ibge": cod, "municipio": nome, "ano": ano, "processo": p["codigoProcesso"], "camara_pessoal": dlp,
                                   "pct_rcl": num(re.findall(r"\d{1,3},\d{2}", pct.group(1))[-1]) if pct else "",
                                   "rcl": num(re.findall(NUM, rcl.group(1))[-1]) if rcl else "", "documento": desc, "pagina": pagina,
                                   "fonte": f"TCE-AM, processo {p['codigoProcesso']} (prestação de contas anual {ano}), {desc} p. {pagina}, "
                                            f"análise técnica — Dados de Gastos com Pessoal (GEFIS), último período do ano; "
                                            f"consulta pública: https://dec.tceam.tc.br/publico/processo/consulta"})
                    if re.search(r"(?i)diferen.a entre os valores apresentados ao GEFIS", t):
                        alertas.append(f"{nome} {ano}: a análise do TCE aponta diferença entre o RGF (GEFIS) e a prestação de contas (proc. {p['codigoProcesso']})")
                    break
                else:
                    sem_quadro.append(f"{nome} {ano} (proc. {p['codigoProcesso']})")
            except Exception as e:
                alertas.append(f"{nome} {ano}: visualizador falhou ({e.__class__.__name__})")
        print(nome, len(linhas), flush=True)

    with ThreadPoolExecutor(4) as pool:  # 4 Câmaras ao mesmo tempo (cada página leva ~1 s)
        list(pool.map(lambda kv: camara(kv[0], *kv[1]), sorted(camaras.items())))
    achados = len(achados)
    sic = {(r["cod_ibge"], int(r["ano"])): float(r["camara_pessoal"]) for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "camaras_financas.csv"), encoding="utf-8"))
           if r["camara_pessoal"] not in ("", None) and "rgf?" in r["fonte_rgf"]}
    bate = [(x, sic[(x["cod_ibge"], x["ano"])]) for x in linhas if (x["cod_ibge"], x["ano"]) in sic]
    # SICONFI e GEFIS (TCE) são duas remessas da própria Câmara e podem divergir; ±5% conta como coerente
    ok_b = [1 for x, s in bate if s and abs(x["camara_pessoal"] - s) / s <= 0.05]
    for x, s in bate:
        if s and abs(x["camara_pessoal"] - s) / s > 0.05:
            alertas.append(f"{x['municipio']} {x['ano']}: TCE R$ {x['camara_pessoal']:,.2f} × SICONFI R$ {s:,.2f}")
    # piso de 20% contra quebra do leitor: muitas análises antigas não trazem o quadro (lista em "Sem o quadro")
    checagens = [(len(camaras) >= 55, f"Câmaras com unidade gestora no TCE-AM: {len(camaras)}"),
                 (len(linhas) >= 0.2 * achados, f"quadro de gastos com pessoal lido em {len(linhas)} de {achados} prestações de contas eletrônicas 2013–2017"),
                 (not bate or len(ok_b) >= 0.6 * len(bate), f"TCE (GEFIS) ≈ SICONFI (±5%) onde os dois existem: {len(ok_b)} de {len(bate)}; o 22 só usa o TCE onde o SICONFI falta, com travas")]
    with open(os.path.join(DADOS, "indicadores", "camaras_rgf_tce.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "municipio", "ano", "processo", "camara_pessoal", "pct_rcl", "rcl", "documento", "pagina", "fonte"])
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda x: (x["cod_ibge"], x["ano"])))
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "32_rgf_camaras_tce.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — pessoal das Câmaras pela análise do TCE-AM (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Sem o quadro de gastos com pessoal na análise\n\n" + ("\n".join(f"- {s}" for s in sem_quadro) or "- nenhum")
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas[:300]) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} processos={achados} confere={len(ok_b)}/{len(bate)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        t = ("I - Receita Corrente Líquida - Últimos 12 meses 213.088.532,83 206.895.383,70 207.488.460,87 II - Limite "
             "XII - Despesa Líquida com Pessoal = VI+VII+VIII+IX+X–XI 7.050.253,78 7.532.499,51 6.945.857,42 XIII - % da Despesa Total com Pessoal sobre a RCL = IX/I*100 3,31 3,64 3,35 Item")
        g = LINHA_XII.search(t)
        assert g and num(re.findall(NUM, g.group(1))[-1]) == 6945857.42, g
        assert num(re.findall(r"\d{1,3},\d{2}", LINHA_XIII.search(t).group(1))[-1]) == 3.35
        assert num(re.findall(NUM, LINHA_I.search(t).group(1))[-1]) == 207488460.87
        print("ok")
    else:
        main()
