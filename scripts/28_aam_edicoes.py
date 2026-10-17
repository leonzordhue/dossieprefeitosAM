"""Edições completas do Diário Oficial dos Municípios do AM (AAM/SIGPub), dia a dia: cobre o período que a busca do
SIGPub não indexa (de meados de 2020 ao fim de 2024 a busca volta vazia, mas as edições em PDF estão publicadas).

Fonte: calendário de edições do SIGPub (POST https://www.diariomunicipal.com.br/aam/materia/calendario) e o PDF de cada
       edição em https://www-storage.voxtecnologia.com.br/?m=sigpub.publicacao&f=251&i=<arquivo>.pdf
Método:
  - texto de cada edição (pymupdf), guardado em dados/brutos/aam_edicoes/AAAA-MM-DD.txt.gz (o PDF não é guardado);
  - a edição é cortada em atos pelo rodapé "Código Identificador: XXXX"; cada ato começa com a entidade
    ("PREFEITURA MUNICIPAL DE X", "CÂMARA MUNICIPAL DE X", "MUNICÍPIO DE X");
  - atos da prefeitura: quem assina como prefeito(a) (nomes_no_trecho do script 24, mesma ligação ao TSE);
  - atos da Câmara: suplentes e autorias (analisa() do script 26) e votações das atas (votacoes() do script 27).
O link de cada linha é o PDF da edição + o código identificador do ato.

Saídas: dados/prefeito_atos_aam_edicoes.csv, dados/camaras_edicoes_{suplentes,autorias,votacoes}.csv,
        dados/integridade/28_aam_edicoes.md
Uso: python -I scripts/28_aam_edicoes.py [ini fim ...]   (padrão 2009-01-01 a 2011-06-30 e 2020-06-01 a 2024-12-31; retoma)
"""
import csv
import gzip
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from importlib import import_module

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
aam = import_module("24_prefeito_atos_aam")
c26 = import_module("26_camaras_aam")
c27 = import_module("27_camaras_votacoes")
decl = aam.decl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
PASTA = os.path.join(DADOS, "brutos", "aam_edicoes")
CAL = "https://www.diariomunicipal.com.br/aam/materia/calendario"
UA = {"User-Agent": "Mozilla/5.0 (pesquisa dossieprefeitosAM)"}
ENTIDADE = re.compile(r"^(PREFEITURA MUNICIPAL DE|C[ÂA]MARA MUNICIPAL DE|MUNIC[ÍI]PIO DE)\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ' \-]+)$", re.M)


class Calendario:
    """Sessão com o token do formulário do calendário (o SIGPub recusa POST sem ele)."""
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        b = self.op.open(urllib.request.Request("https://www.diariomunicipal.com.br/aam/", headers=UA), timeout=60).read().decode("utf-8", "replace")
        self.token = (re.search(r'name="calendar\[_token\]"[^>]*value="([^"]*)"', b) or re.search(r'value="([^"]*)"[^>]*name="calendar\[_token\]"', b)).group(1)

    def edicoes(self, d):
        dados = urllib.parse.urlencode({"calendar[_token]": self.token, "calendar[day]": d.day, "calendar[month]": d.month, "calendar[year]": d.year}).encode()
        h = dict(UA, **{"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://www.diariomunicipal.com.br/aam/"})
        r = json.loads(self.op.open(urllib.request.Request(CAL, data=dados, headers=h), timeout=60).read())
        return [(e["url_arquivo"] + e["link_diario"] + ("" if e["link_diario"].endswith(".pdf") else ".pdf"), e.get("numero_edicao") or "")
                for e in r.get("edicao") or [] if e.get("link_diario")]


def texto_pdf(url):
    for i in range(4):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
            if b[:4] == b"%PDF":
                d = pymupdf.open(stream=b, filetype="pdf")
                linhas, ant = [], None
                for p in d:
                    for ln in p.get_text().splitlines():
                        ln = ln.strip()
                        if ln and ln != ant:  # o PDF repete cada linha em negrito
                            linhas.append(ln)
                        ant = ln
                return "\n".join(linhas)
            return ""
        except Exception:
            time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def baixa(ini, fim):
    os.makedirs(PASTA, exist_ok=True)
    cal, d, falhas = Calendario(), ini, []
    while d <= fim:
        arq = os.path.join(PASTA, f"{d.isoformat()}.txt.gz")
        if not os.path.exists(arq):
            try:
                eds = cal.edicoes(d)
                partes = []
                for url, num in eds:
                    partes.append(f"@@EDICAO {num} {url}\n" + texto_pdf(url))
                with gzip.open(arq + ".tmp", "wt", encoding="utf-8") as f:
                    f.write("\n".join(partes))
                os.replace(arq + ".tmp", arq)
                time.sleep(0.5)
            except Exception as e:
                falhas.append(f"{d}: {e.__class__.__name__} {str(e)[:80]}")
                cal = Calendario()  # token pode ter expirado
        if d.day == 1:
            print("baixado", d, flush=True)
        d += timedelta(days=1)
    return falhas


def atos(texto):
    """(url da edição, entidade, município, código identificador, texto do ato)."""
    for parte in texto.split("@@EDICAO ")[1:]:
        cab, _, corpo = parte.partition("\n")
        url = cab.split(" ", 1)[1] if " " in cab else cab
        for bloco in re.split(r"C[óo]digo Identificador:\s*", corpo):
            m = ENTIDADE.search(bloco[:600])
            cod_id = re.match(r"([A-Z0-9]{6,12})", bloco)
            if m:
                yield url, m.group(1), m.group(2).strip(), (cod_id.group(1) if cod_id else ""), bloco[m.start():]


def main(periodos):
    falhas = [f for ini, fim in periodos for f in baixa(ini, fim)]
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    por_nome = {" ".join(decl.palavras(m["municipio"])): m["cod_ibge"] for m in muns}
    cand_pref = defaultdict(dict)
    for arq in ("candidaturas_prefeito.csv", "candidaturas_vereador.csv"):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            cand_pref[r["cod_ibge"]][r["pessoa_id"]] = r["nome"]
    cand_ver = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(DADOS, "candidaturas_vereador.csv"), encoding="utf-8")):
        cand_ver[r["cod_ibge"]].append((r["pessoa_id"], r["nome"], r["nome_urna"], int(r["ciclo"]), r["resultado"].upper()))
    mand = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")):
        mand[r["cod_ibge"]].append(r)

    nomes_mun = sorted(((decl.palavras(n), c) for n, c in por_nome.items()), key=lambda x: -len(x[0]))

    def municipio(texto):
        """Município da entidade, tolerando quebra de linha ("SÃO GABRIEL DA") e texto colado ("TAPAUÁ-AM", "BENJAMIN CONSTANT E DÁ...")."""
        w = decl.palavras(texto.replace("-", " "))
        exato = por_nome.get(" ".join(w))
        if exato or not w:
            return exato
        comeca = [c for n, c in nomes_mun if w[:len(n)] == n]  # a entidade começa com o nome do município (o mais longo primeiro)
        if comeca:
            return comeca[0]
        prefixo = {c for n, c in nomes_mun if n[:len(w)] == w}  # nome cortado: só vale se um único município começa assim
        return prefixo.pop() if len(prefixo) == 1 else None

    def ligar_ver(cod, n):
        return next((p for p, nm, urna, *_ in cand_ver[cod] if aam.estrito(n, nm) or (urna and len(urna.split()) >= 2 and aam.estrito(n, urna))), "")

    pref, sup, aut, vot, vistos = [], [], [], [], set()
    n_atos, sem_mun, dias = Counter(), Counter(), 0
    for arq in sorted(os.listdir(PASTA)):
        iso = arq[:10]  # analisa tudo o que já foi baixado (todos os períodos)
        dias += 1
        with gzip.open(os.path.join(PASTA, arq), "rt", encoding="utf-8") as f:
            texto = f.read()
        for url, tipo, mun, cod_id, t in atos(texto):
            cod = municipio(mun)
            if not cod:
                sem_mun[mun] += 1
                continue
            n_atos[tipo[:3]] += 1
            fonte = f"Diário Oficial dos Municípios do AM (AAM/SIGPub), edição de {iso[8:]}/{iso[5:7]}/{iso[:4]}, {url}" + (f", código identificador {cod_id}" if cod_id else "")
            titulo = " ".join(t.split("\n")[1:3])[:160]
            plano = " ".join(t.split())
            if tipo.startswith(("PREF", "MUN")):
                vig = next((x for x in mand[cod] if x["inicio"] <= iso <= x["fim_previsto"]), None)
                for nome, cond in aam.nomes_no_trecho(plano):
                    pid = (vig["pessoa_id"] if vig and decl.mesmo(nome, vig["prefeito"]) else vig["vice_pessoa_id"] if vig and vig["vice"] and decl.mesmo(nome, vig["vice"])
                           else next((p for p, n in cand_pref[cod].items() if aam.estrito(nome, n)), ""))
                    if not pid or (cod, iso, pid, cod_id) in vistos:
                        continue
                    vistos.add((cod, iso, pid, cod_id))
                    papel = "titular" if vig and pid == vig["pessoa_id"] else "vice" if vig and pid == vig["vice_pessoa_id"] else "outro"
                    pref.append({"cod_ibge": cod, "data": iso, "nome_no_ato": nome.title(), "condicao": cond, "papel": papel, "pessoa_id": pid,
                                 "titular_tse": vig["prefeito"] if vig else "", "titulo": titulo, "codigo": cod_id, "origem": "edição completa", "fonte": fonte})
            else:
                x = {"cod_ibge": cod, "data": iso, "titulo": titulo, "codigo": cod_id, "fonte": fonte,
                     "tipo": re.split(r"[\s\-–Nº°0-9/]+", titulo.upper().strip() + " ")[0]}
                s, a = c26.analisa(x, plano, {cod: cand_ver[cod]})
                sup += s
                aut += a
                if re.match(r"ATA\b", titulo.upper()) and not re.search(r"REGISTRO\s+DE\s+PRE|PREG[ÃA]O|LICITA", titulo.upper()):
                    vot += c27.votacoes({"cod_ibge": cod, "data": iso, "titulo": titulo, "fonte": fonte}, plano, ligar_ver)
    previstos = sum((fim - ini).days + 1 for ini, fim in periodos)
    checagens = [(dias >= 0.98 * previstos, f"dias com edição baixada ou conferida: {dias} de {previstos} ({len(falhas)} falhas)"),
                 (len(pref) > 0, f"atos com quem assina como prefeito(a): {len(pref)} em {len({x['cod_ibge'] for x in pref})} municípios"),
                 (sum(n_atos.values()) > 0, f"atos lidos por entidade: {dict(n_atos)}"),
                 (True, f"Câmaras: {len(sup)} menções em posse/convocação de suplente, {len(aut)} autorias, {len(vot)} votações")]

    def grava(nome, linhas, campos):
        with open(os.path.join(DADOS, nome), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, campos, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(linhas, key=lambda r: (r["cod_ibge"], r.get("data") or r.get("data_ata", ""))))
    grava("prefeito_atos_aam_edicoes.csv", pref, ["cod_ibge", "data", "nome_no_ato", "condicao", "papel", "pessoa_id", "titular_tse", "titulo", "codigo", "origem", "fonte"])
    grava("camaras_edicoes_suplentes.csv", sup, ["cod_ibge", "data", "nome_no_ato", "pessoa_id", "nome_tse", "ciclo", "papel", "motivo_no_ato", "titulo", "codigo", "fonte"])
    grava("camaras_edicoes_autorias.csv", aut, ["cod_ibge", "data", "nome_no_ato", "pessoa_id", "nome_tse", "tipo", "titulo", "codigo", "fonte"])
    grava("camaras_edicoes_votacoes.csv", vot, list(vot[0].keys()) if vot else ["cod_ibge", "data_ata"])
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "28_aam_edicoes.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — edições completas do AAM/SIGPub {', '.join(f'{a} a {b}' for a, b in periodos)} (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Entidades sem município reconhecido\n\n" + ("\n".join(f"- {k}: {v}" for k, v in sem_mun.most_common(20)) or "- nenhuma")
                + "\n\n## Falhas de download\n\n" + ("\n".join(f"- {x}" for x in falhas[:100]) or "- nenhuma") + "\n")
    print(f"dias={dias} prefeito={len(pref)} suplentes={len(sup)} autorias={len(aut)} votacoes={len(vot)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        cal = Calendario()
        eds = cal.edicoes(date(2022, 6, 15))
        print(eds)
        t = texto_pdf(eds[0][0])
        n = Counter(a[1][:3] for a in atos("@@EDICAO x " + eds[0][0] + "\n" + t))
        print(len(t), n)
        assert n and sum(n.values()) > 50
        print("ok")
    else:
        a = [date.fromisoformat(x) for x in sys.argv[1:]]
        # padrão: os dois buracos da busca do SIGPub (começo do diário e meados de 2020 a 2024)
        main(list(zip(a[::2], a[1::2])) or [(date(2009, 1, 1), date(2011, 6, 30)), (date(2020, 6, 1), date(2024, 12, 31))])
