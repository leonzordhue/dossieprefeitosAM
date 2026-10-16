"""Quem assinou os atos da Prefeitura de Manaus, edição a edição do Diário Oficial do Município (2000 em diante).
Complementa o script 24 (AAM/SIGPub, que não tem Manaus): mesmas colunas, mesma regra de ligação.

Fonte: Querido Diário (Open Knowledge Brasil), texto integral do DOM Manaus em pacotes anuais
       https://queridodiario.ok.org.br/api/aggregates/AM -> data.queridodiario.ok.org.br/aggregates/AM/AM_<ano>.zip
       (baixados em dados/brutos/querido_diario/, MD5 conferido com o hash_info da API). Cada edição traz a URL do PDF original
       em dom.manaus.am.gov.br, que vai como fonte.
Por que os pacotes: a API de busca do Querido Diário devolve 503 quando sobrecarregada; os pacotes anuais saem do
armazenamento de arquivos, sem passar por ela.
Método: em cada edição, nomes em maiúsculas junto de "Prefeito(a)" (função nomes_no_trecho do script 24), ligados a
candidato a prefeito, vice ou vereador de Manaus no TSE; o papel é comparado com o mandato vigente na data.

Saídas: dados/prefeito_atos_manaus.csv, dados/integridade/25_prefeito_atos_manaus.md
Uso: python -I scripts/25_prefeito_atos_manaus.py
"""
import csv
import glob
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
decl = import_module("18_prefeito_declarado")  # mesmo()
aam = import_module("24_prefeito_atos_aam")  # nomes_no_trecho()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
PASTA = os.path.join(DADOS, "brutos", "querido_diario")
COD = "1302603"


def main():
    meta = {a["year"]: a for a in json.load(open(os.path.join(PASTA, "_aggregates_AM.json"), encoding="utf-8"))["aggregates"]}
    cand = {}
    for arq in ("candidaturas_prefeito.csv", "candidaturas_vereador.csv"):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            if r["cod_ibge"] == COD:
                cand[r["pessoa_id"]] = r["nome"]
    mand = [r for r in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")) if r["cod_ibge"] == COD]
    # Manaus tem ~10 mil candidatos: compara só com quem tem o mesmo primeiro ou último nome
    por_ponta = defaultdict(set)
    for p, n in cand.items():
        w = decl.palavras(n)
        if w:
            por_ponta[w[0]].add(p)
            por_ponta[w[-1]].add(p)
    linhas, vistos, edicoes, anos_ok = [], set(), 0, 0
    cache_nome = {}
    for arq in sorted(glob.glob(os.path.join(PASTA, "AM_*.zip"))):
        z = zipfile.ZipFile(arq)
        xml = z.read(z.namelist()[0]).decode("utf-8", "replace")
        anos_ok += 1
        for d in re.finditer(r"<diario>(.*?)</diario>", xml, re.S):
            bloco = d.group(1)
            data = re.search(r"<data_publicacao>(\d{2})/(\d{2})/(\d{4})</data_publicacao>", bloco)
            url = (re.search(r"<url_arquivo_original>(.*?)</url_arquivo_original>", bloco) or [None, ""])[1]
            if not data:
                continue
            iso = f"{data[3]}-{data[2]}-{data[1]}"
            edicoes += 1
            texto = " ".join((re.search(r"<conteudo>(.*?)</conteudo>", bloco, re.S) or [None, ""])[1].split())
            vig = next((x for x in mand if x["inicio"] <= iso <= x["fim_previsto"]), None)
            # de 2009 em diante a assinatura é digital e o nome não está no texto; "O PREFEITO DE MANAUS, EM EXERCÍCIO" indica o
            # substituto legal, que é o vice do mandato vigente (Lei Orgânica de Manaus); o presidente da Câmara aparece por extenso
            subst = re.search(r"PREFEIT[OA]\s+(?:MUNICIPAL\s+)?DE\s+MANAUS,?\s+EM\s+EXERC[IÍ]CIO", texto, re.I)
            camara = re.search(r"PRESIDENTE\s+DA\s+C[AÂ]MARA\s+MUNICIPAL[^.]{0,80}NO\s+EXERC[IÍ]CIO\s+DO\s+CARGO\s+DE\s+PREFEIT", texto, re.I)
            for achou, papel, pid in ((subst, "vice (presumido: substituto legal)", vig and vig["vice_pessoa_id"]),
                                      (camara, "presidente da Câmara no exercício do cargo", "")):
                if achou and (iso, papel) not in vistos:
                    vistos.add((iso, papel))
                    linhas.append({"cod_ibge": COD, "data": iso, "nome_no_ato": "", "condicao": "em exercício", "papel": papel,
                                   "pessoa_id": pid or "", "titular_tse": vig["prefeito"] if vig else "", "titulo": f"DOM Manaus de {data[1]}/{data[2]}/{data[3]}",
                                   "codigo": "", "origem": "Querido Diário (DOM Manaus)", "trecho": texto[max(0, achou.start() - 150):achou.end() + 150],
                                   "fonte": f"Diário Oficial do Município de Manaus ({url}), texto do Querido Diário/OKBR "
                                            f"(https://data.queridodiario.ok.org.br/aggregates/AM/{os.path.basename(arq)})"})
            for nome, cond in aam.nomes_no_trecho(texto):
                # titular/vice do mandato vigente têm preferência (mesma pessoa com dois pessoa_id, um por título)
                if vig and decl.mesmo(nome, vig["prefeito"]):
                    cache_nome[nome] = vig["pessoa_id"]
                elif vig and vig["vice"] and decl.mesmo(nome, vig["vice"]):
                    cache_nome[nome] = vig["vice_pessoa_id"]
                elif nome not in cache_nome:
                    w = decl.palavras(nome)
                    perto = (por_ponta.get(w[0], set()) | por_ponta.get(w[-1], set())) if w else set()
                    cache_nome[nome] = next((p for p in sorted(perto) if decl.mesmo(nome, cand[p])), "")
                pid = cache_nome[nome]
                if not pid or (iso, pid, cond) in vistos:
                    continue
                vistos.add((iso, pid, cond))
                papel = "titular" if vig and pid == vig["pessoa_id"] else "vice" if vig and pid == vig["vice_pessoa_id"] else "outro"
                linhas.append({"cod_ibge": COD, "data": iso, "nome_no_ato": nome.title(), "condicao": cond, "papel": papel, "pessoa_id": pid,
                               "titular_tse": vig["prefeito"] if vig else "", "titulo": f"DOM Manaus de {data[1]}/{data[2]}/{data[3]}",
                               "codigo": "", "origem": "Querido Diário (DOM Manaus)",
                               "fonte": f"Diário Oficial do Município de Manaus ({url}), texto do Querido Diário/OKBR "
                                        f"(https://data.queridodiario.ok.org.br/aggregates/AM/{os.path.basename(arq)})"})
        print(os.path.basename(arq), len(linhas), flush=True)
    linhas.sort(key=lambda x: (x["data"], x["pessoa_id"]))
    with open(os.path.join(DADOS, "prefeito_atos_manaus.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "data", "nome_no_ato", "condicao", "papel", "pessoa_id", "titular_tse", "titulo", "codigo", "origem", "fonte"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    papeis = Counter(x["papel"] for x in linhas)
    meses = {x["data"][:7] for x in linhas}
    checagens = [(anos_ok == len(meta), f"{anos_ok} pacotes anuais lidos de {len(meta)} listados pela API"),
                 (edicoes > 3000, f"{edicoes} edições do DOM lidas"),
                 (len(meses) >= 0.8 * 12 * anos_ok, f"meses com quem exerceu a prefeitura identificado: {len(meses)} de {12 * anos_ok}")]
    alertas = []
    outros = defaultdict(list)
    for x in linhas:
        if x["papel"] != "titular":
            outros[(x["papel"], x["nome_no_ato"], x["pessoa_id"], x["condicao"])].append(x["data"])
    for (papel, nome, pid, cond), ds in sorted(outros.items(), key=lambda k: min(k[1])):
        alertas.append(f"{papel}: {nome or '(nome fora do texto)'} ({pid or 'sem ligação'}) {cond or 'sem condição'}: {len(ds)} edição(ões), {min(ds)} a {max(ds)}")
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "25_prefeito_atos_manaus.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — quem assina os atos da Prefeitura de Manaus (DOM, Querido Diário) (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Linhas: {len(linhas)} ({dict(papeis)})\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Quem assinou como prefeito(a) sem ser o titular do TSE (conferir)\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} edicoes={edicoes} checagens={ok}/{len(checagens)} {dict(papeis)}")


if __name__ == "__main__":
    main()
