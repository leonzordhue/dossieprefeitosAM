"""Decisões do TCE-AM (acórdãos, decisões e pareceres prévios desde 2016) em que prefeitos e vices do AM são parte.
Complementa 17_tceam.py, cujas relações de contas irregulares só existem em planilha a partir de 2022.

Fonte: API pública da jurisprudência do TCE-AM — https://jurisprudencia-api.tce.am.gov.br/decisorios/byManyFields
       (a mesma do site https://jurisprudencia.tce.am.gov.br; busca no texto integral, limite de 1.000 resultados por
       consulta, decisórios a partir de 2016). Cada decisão traz órgão, partes, natureza, relator e o PDF assinado.
Ligação: busca pelo nome completo de quem teve mandato de prefeito ou vice (dados/mandatos.csv); a decisão só entra quando
o nome confere com um dos nomes em "partes" E o órgão é do município onde a pessoa teve mandato (evita homônimos).
Resultado: termos da parte dispositiva marcados automaticamente ("julgar irregular", "desaprovação", "multa",
"alcance"/débito, "julgar ilegal" (atos de pessoal), "regular com ressalvas", "regular"). É classificação por texto: a decisão pode tratar de mais de um
responsável e cabe recurso. O PDF oficial vai junto para leitura. Decisões anteriores a 2016 não estão na base.

Saídas: dados/indicadores/tceam_decisoes.csv, dados/integridade/19_tceam_decisoes.md
Uso: python -I scripts/19_tceam_decisoes.py   (~1 consulta/s; respostas em dados/brutos/cache_http)
"""
import csv
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from importlib import import_module
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

decl = import_module("18_prefeito_declarado")  # mesmo(): nomes iguais a menos de grafia

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
API = "https://jurisprudencia-api.tce.am.gov.br/decisorios/byManyFields?"
VAZIOS = ("strAnoProcesso", "strNumeroProcesso", "strAnoDecisorio", "strNumeroDecisorio", "strRelatorDecisorio", "strOrgaoJulgador",
          "strDataSessaoInicio", "strDataSessaoFim", "strNatureza")
# (rótulo, padrão no texto sem acento, em maiúsculas); a ordem é a de gravidade
TERMOS = (("contas irregulares", r"JULGA\w*\s+(?:AS\s+CONTAS\s+)?IRREGULAR"),
          ("ato julgado ilegal", r"(?:JULGA|CONSIDERA)\w*\s+ILEGA"),  # ex.: admissão de pessoal sem concurso; não é conta irregular
          ("parecer pela desaprovação", r"DESAPROVA[CÇ]|PELA\s+REJEI[CÇ]|NAO\s+APROVA"),
          ("alcance/débito", r"\bALCANCE\b|\bGLOSA\b|RESSARC|DEVOLU[CÇ]AO\s+DE|IMPUTA[CÇ]AO\s+DE\s+DEBITO"),
          ("multa", r"\bMULTA\b"),
          ("regular com ressalvas", r"REGULAR(?:ES)?\s+COM\s+RESSALVA"),
          ("parecer pela aprovação", r"PELA\s+APROVA[CÇ]|RECOMENDANDO\s+(?:A\s+)?(?:CAMARA\s+)?(?:MUNICIPAL\s+)?(?:DE\s+\w+\s+)?A\s+APROVA[CÇ]"))


def norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def dispositivo(texto):
    """Trecho da decisão depois de ACORDAM/DECIDEM (a parte dispositiva); sem ele, o texto todo."""
    t = norm(texto)
    m = re.search(r"\b(ACORDAM|DECIDEM|RESOLVE)\b", t)
    return t[m.start():] if m else t


def main():
    muns = {m["cod_ibge"]: m["municipio"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    alvo = defaultdict(set)  # pessoa_id -> {cod_ibge}
    nome = {}
    for m in csv.DictReader(open(os.path.join(DADOS, "mandatos.csv"), encoding="utf-8")):
        for pid, n in ((m["pessoa_id"], m["prefeito"]), (m["vice_pessoa_id"], m["vice"])):
            if pid and n and not n.startswith("("):
                alvo[pid].add(m["cod_ibge"])
                nome[pid] = n
    checagens, alertas, linhas, vistos = [], [], [], set()
    n_consultas = n_bruto = n_homonimo = 0
    for pid in sorted(alvo):
        p = {"strConteudo": f'"{nome[pid]}"', **{k: "null" for k in VAZIOS}}
        url = API + urlencode(p, quote_via=quote)
        if not rede.em_cache(url):
            time.sleep(1)
        try:
            itens = rede.get_json(url)
        except Exception as e:
            alertas.append(f"{nome[pid]}: consulta falhou ({e.__class__.__name__})")
            continue
        n_consultas += 1
        n_bruto += len(itens)
        if len(itens) >= 1000:
            alertas.append(f"{nome[pid]}: 1.000 resultados (limite da API); pode faltar decisão")
        for x in itens:
            partes = [s.strip() for s in re.split(r"[;,\n]| E ", x.get("partes") or "") if s.strip()]
            orgao = x.get("orgao") or ""
            cod = next((c for c in alvo[pid] if norm(muns[c]) in norm(orgao)), None)
            if not any(decl.mesmo(nome[pid], s) for s in partes) or not cod:
                n_homonimo += 1  # nome citado no texto, mas não como parte, ou órgão de outro município
                continue
            k = (pid, x.get("caminhoArquivo") or x.get("nomeDoArquivo"))
            if k in vistos:
                continue
            vistos.add(k)
            disp = dispositivo(x.get("conteudo") or "")
            termos = [r for r, rx in TERMOS if re.search(rx, disp)]
            if "contas irregulares" in termos or "parecer pela desaprovação" in termos:
                termos = [t for t in termos if t not in ("regular com ressalvas", "parecer pela aprovação")]
            dec = f"{(x.get('tipo') or '').strip().title()} nº {x.get('numeroDecisorio')}/{x.get('anoDecisorio')}" if x.get("anoDecisorio") else ""
            m_data = re.match(r"(\d{2})-(\d{2})-0?(\d{4})", x.get("dataArquivo") or "")
            arq = x.get("caminhoArquivo") or ""
            if arq and not arq.lower().endswith(".pdf") and x.get("nomeDoArquivo"):
                arq = arq.rsplit("/", 1)[0] + "/" + x["nomeDoArquivo"]  # o caminho vem truncado; o nome do arquivo é o completo
            arq = quote(arq, safe=":/")  # há nomes com espaço ("PARECER PREVIO")
            linhas.append({"pessoa_id": pid, "cod_ibge": cod, "orgao": orgao.strip(), "natureza": (x.get("natureza") or "").strip(),
                           "processo": f"{x.get('numeroProcesso')}/{x.get('anoProcesso')}", "decisorio": dec,
                           "data_arquivo": f"{m_data[3]}-{m_data[2]}-{m_data[1]}" if m_data else "",
                           "objeto": re.sub(r"\s+", " ", x.get("objeto") or "").strip()[:200], "relator": (x.get("relator") or "").strip(),
                           "termos": "; ".join(termos), "arquivo": arq,
                           "fonte": f"TCE-AM, jurisprudência ({API}strConteudo=...); decisório {x.get('nomeDoArquivo')}"})
    checagens.append((n_consultas == len(alvo), f"{n_consultas} de {len(alvo)} prefeitos/vices consultados"))
    checagens.append((True, f"{n_bruto} resultados brutos; {n_homonimo} descartados (nome não está nas partes ou órgão de outro município); "
                            f"{len(linhas)} decisões ligadas a {len({x['pessoa_id'] for x in linhas})} pessoas"))
    sem_pdf = [x for x in linhas if not x["arquivo"].startswith("https://")]
    checagens.append((not sem_pdf, f"toda decisão ligada tem o PDF oficial: {len(linhas) - len(sem_pdf)} de {len(linhas)}"))
    linhas.sort(key=lambda x: (x["pessoa_id"], x["data_arquivo"]))
    with open(os.path.join(DADOS, "indicadores", "tceam_decisoes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["pessoa_id", "cod_ibge", "orgao", "natureza", "processo", "decisorio", "data_arquivo", "objeto", "relator",
                               "termos", "arquivo", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    cont = defaultdict(int)
    for x in linhas:
        for t in (x["termos"].split("; ") if x["termos"] else ["(sem termo identificado)"]):
            cont[t] += 1
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "19_tceam_decisoes.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — decisões do TCE-AM (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Termos encontrados na parte dispositiva\n\n" + "\n".join(f"- {t}: {n}" for t, n in sorted(cont.items(), key=lambda z: -z[1]))
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"pessoas={len(alvo)} consultas={n_consultas} brutos={n_bruto} ligadas={len(linhas)} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
