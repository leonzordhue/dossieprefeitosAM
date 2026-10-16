"""Contas julgadas irregulares pelo TCE-AM antes de 2022: relações antigas recuperadas do Internet Archive (Wayback Machine).

Por que: o portal atual do TCE-AM só traz as relações de 2022 em diante (script 17) e o TRE-AM bloqueia acesso
automatizado (403). As relações antigas que o TCE-AM e o TRE-AM publicaram ficaram arquivadas no Wayback Machine.
Fonte: cópias arquivadas em https://web.archive.org/ (endereço original + data da captura em dados/brutos/tce_listas_wayback/
_origem.json; o arquivo começa com a data da captura). Relações lidas:
  - "Processos julgados irregulares 2006/2014", entregue ao TRE-AM para a eleição de 2014 (TRE-AM e TCE-AM);
  - "Gestores com contas reprovadas (2004-2011)" (nome, processo, ano);
  - relações mensais do TCE-AM de set/2016, 2018, 2019 e 2020 (gestor, órgão, processo);
  - relações para o TRE-AM de 2020 e 2022 ("com glosa"), e de 2024, com CPF, processo, exercício, julgamento e acórdão.
  - "Gestores excluídos após revisão" (24/09/2020): tira da relação de 2020 quem teve recurso admitido.
Ligação à pessoa (só prefeitos, vices e vereadores do dossiê; CPF nunca é publicado):
  - relação com CPF: CPF idêntico ao do registro de candidatura no TSE + mesmo nome (regra do script 17);
  - sem CPF, órgão municipal: nome idêntico (sem acento) ao de um candidato do mesmo município do órgão;
  - sem CPF e sem município: nome completo (3+ palavras) que só existe uma vez entre os candidatos municipais do AM.
    Essa ligação é mais fraca e sai marcada "a conferir".
Conta julgada irregular não é inelegibilidade automática (LC 64/1990, art. 1º, I, g).

Saídas: dados/indicadores/tceam_listas_antigas.csv, dados/integridade/23_tceam_listas_antigas.md
Uso: python -I scripts/23_tceam_listas_antigas.py
"""
import csv
import glob
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from importlib import import_module

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tcu = import_module("13_tcu")  # sem_acento, so_digitos, ANOS_CPF
t17 = import_module("17_tceam")  # mesmo_nome

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
PASTA = os.path.join(DADOS, "brutos", "tce_listas_wayback")
TSE = os.path.join(DADOS, "brutos", "tse")
# cabeçalho (sem acento) -> campo
# ("Nº" vira "NO" sem acento; "NOME_ÓRGÃO" é o órgão, não o gestor)
CAMPOS = (("NOMEORGAO", "orgao"), ("NOMEDOORGAO", "orgao"), ("REQUERIDO", "nome"), ("RESPONSAVEL", "nome"), ("NOMEDOGESTOR", "nome"),
          ("GESTOR", "nome"), ("NOME", "nome"), ("CPF", "cpf"), ("ORGAO", "orgao"), ("NATUREZA", "natureza"), ("NOPROCESSO", "processo"),
          ("NPROCESSO", "processo"), ("NUMPROCESSO", "processo"), ("PROCESSO", "processo"), ("ANO", "ano"),
          ("EXERCICIO", "exercicio"), ("DATADOJULGAMENTO", "data"), ("DTJULGAMENTO", "data"), ("DATADEPUBLICACAO", "data"),
          ("NUMERODOACORDAO", "acordao"), ("ACORDAO", "acordao"), ("DATADOTRANSITO", "transito"), ("DTTRANSITO", "transito"),
          ("ESFERA", "esfera"))


def iso(t):
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", t or "")
    return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""


# cabeçalho inteiro numa célula só (relações de set/2016 por Câmaras, Prefeituras e Interior)
ROTULOS = ((r"DATA\s+(DO\s+)?JULGAMENTO", "data"), (r"PROCESSO", "processo"), (r"GESTOR|REQUERIDO", "nome"), (r"[ÓO]RG[ÃA]O", "orgao"),
           (r"ESFERA", "esfera"), (r"RECURSO", "recurso"), (r"JULGAMENTO|DELIBERA", "julgamento"))


def cabecalho(linha):
    cheias = [c for c in linha if c]
    if len(cheias) == 1 and "PROCESSO" in cheias[0].upper() and re.search("GESTOR|REQUERIDO", cheias[0].upper()):
        achados, resto = [], cheias[0].upper()
        while resto.strip():
            m = min(((re.match(r"\s*(" + rx + ")", resto), v) for rx, v in ROTULOS), key=lambda x: 0 if x[0] else 1)
            if not m[0]:
                break
            achados.append(m[1])
            resto = resto[m[0].end():]
        if len(achados) == len(linha):
            return dict(enumerate(achados))
    col = {}
    for i, c in enumerate(linha):
        k = tcu.sem_acento(c or "")
        campo = next((v for p, v in CAMPOS if k.startswith(p) and v not in col.values()), None)
        if campo and k:
            col[i] = campo
    return col if "nome" in col.values() and ("processo" in col.values() or "orgao" in col.values()) else None


def ler_pdf(arq):
    """Linhas (dict campo->texto) de todas as tabelas do PDF. O cabeçalho da 1ª página vale para as seguintes."""
    out, col = [], None
    with pdfplumber.open(arq) as pdf:
        for pg in pdf.pages:
            for tab in pg.extract_tables():
                for bruta in tab:
                    r = [" ".join((c or "").split()) for c in bruta]
                    h = cabecalho(r)
                    if h:
                        col = h
                        continue
                    if not col:
                        continue
                    # várias decisões na mesma linha, uma por quebra de linha (relações de set/2016)
                    i_proc = next((i for i, v in col.items() if v == "processo"), None)
                    n = len(re.findall(r"\d+/\d{2,4}", bruta[i_proc] or "")) if i_proc is not None and i_proc < len(bruta) else 0
                    partes = [(c or "").split("\n") for c in bruta]
                    if n > 1 and all(len(x) == n for x, (i, v) in ((partes[i], (i, v)) for i, v in col.items() if v in ("nome", "orgao", "processo") and i < len(partes))):
                        for j in range(n):
                            out.append({v: partes[i][j].strip() for i, v in col.items() if i < len(partes) and len(partes[i]) == n})
                        continue
                    # linhas com uma coluna vazia a mais à esquerda (relação de 2024): alinha pelo fim
                    desl = len(r) - (max(col) + 1) if len(r) > max(col) + 1 else 0
                    d = {}
                    for i, campo in col.items():
                        j = i + desl
                        # cabeçalho mesclado uma coluna ao lado dos dados (relações de 2018 e jun/2020): usa a vizinha vazia de cabeçalho
                        for k in (j, j - 1, j + 1):
                            if 0 <= k < len(r) and r[k] and (k == j or k - desl not in col):
                                d[campo] = r[k]
                                break
                    if len(tcu.sem_acento(d.get("nome", ""))) >= 6:
                        out.append(d)
    return out


def processo(d):
    p = d.get("processo", "").replace(".", "").replace(" ", "")
    if re.fullmatch(r"\d+", p) and re.fullmatch(r"\d{4}", d.get("ano", "")):
        p = f"{p}/{d['ano']}"
    if m := re.fullmatch(r"(\d+)/(\d{2})", p):  # ano com 2 dígitos (relações de 2016): 05 -> 2005, 98 -> 1998
        p = f"{m[1]}/{'20' if int(m[2]) <= 30 else '19'}{m[2]}"
    return p if re.fullmatch(r"\d+/\d{4}", p) else ""


def main():
    origem = {}
    for url, ts in json.load(open(os.path.join(PASTA, "_origem.json"), encoding="utf-8")).items():
        origem[ts[:8]] = origem.get(ts[:8], []) + [(url, ts)]
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    norm_mun = sorted(((tcu.sem_acento(m["municipio"]), m["cod_ibge"]) for m in muns), key=lambda x: -len(x[0]))
    # candidatos municipais do dossiê: nome -> {(pessoa_id, cod_ibge)}
    por_nome, nome_pid = defaultdict(set), {}
    for arq in ("candidaturas_prefeito.csv", "candidaturas_vereador.csv"):
        for r in csv.DictReader(open(os.path.join(DADOS, arq), encoding="utf-8")):
            por_nome[tcu.sem_acento(r["nome"])].add((r["pessoa_id"], r["cod_ibge"]))
            nome_pid[r["pessoa_id"]] = r["nome"]
    cpf_pid = {}
    for a in tcu.ANOS_CPF:
        with open(os.path.join(TSE, f"consulta_cand_{a}_AM.csv"), encoding="latin1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                c = tcu.so_digitos(r["NR_CPF_CANDIDATO"])
                p = hashlib.sha1(r["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10]
                if c.strip("0") and not r["NR_CPF_CANDIDATO"].startswith("-") and p in nome_pid:
                    cpf_pid[c] = p if cpf_pid.get(c, p) == p else None

    arquivos = sorted(f for f in glob.glob(os.path.join(PASTA, "**", "*"), recursive=True)
                      if os.path.isfile(f) and "_descartados" not in f and not f.endswith((".json", ".zip"))
                      and "maior_numero" not in f)
    checagens, alertas, excluidos = [], [], set()
    exc = [f for f in arquivos if "excluidos" in f]
    for d in (ler_pdf(exc[0]) if exc else []):
        excluidos.add((tcu.sem_acento(d["nome"]), re.sub(r"\D", "", d.get("processo", ""))))
    registros, cpfs_lidos = {}, set()  # (pessoa_id, processo ou nome+órgão) -> linha
    lidos = 0
    for arq in arquivos:
        if arq in exc:
            continue
        rel = os.path.relpath(arq, PASTA)
        data_cap = rel[:8]
        url, ts = (origem.get(data_cap) or [("", data_cap)])[0]
        if len(origem.get(data_cap, [])) > 1:  # duas capturas no mesmo dia: casa pelo nome do arquivo
            url, ts = next(((u, t) for u, t in origem[data_cap] if tcu.sem_acento(os.path.basename(u))[:20] in tcu.sem_acento(rel)), (url, ts))
        if "set2016" in rel:  # PDFs de dentro do zip de set/2016
            url, ts = next((u, t) for lst in origem.values() for u, t in lst if "setembro2016" in u)
        fonte = f"TCE-AM, relação “{os.path.basename(arq)}” (cópia do Internet Archive: https://web.archive.org/web/{ts}/{url})"
        linhas = ler_pdf(arq)
        lidos += bool(linhas)
        if not linhas:
            alertas.append(f"{rel}: nenhuma tabela de gestores reconhecida")
            continue
        for d in linhas:
            nome, proc = d["nome"], processo(d)
            if data_cap.startswith("2020") and (tcu.sem_acento(nome), re.sub(r"\D", "", d.get("processo", ""))) in excluidos:
                continue
            cpf = tcu.so_digitos(d.get("cpf", "")) if re.sub(r"\D", "", d.get("cpf", "")) else ""
            if cpf:
                cpfs_lidos.update({cpf, d["cpf"]})
            pid, ligacao = None, ""
            if cpf:
                p = cpf_pid.get(cpf)
                if p and t17.mesmo_nome(nome, nome_pid[p]):
                    pid, ligacao = p, "cpf + nome"
            else:
                cands = por_nome.get(tcu.sem_acento(nome), set())
                org = tcu.sem_acento(d.get("orgao", ""))
                cod = next((c for n, c in norm_mun if n in org), None) if org else None
                if cod:
                    ps = {p for p, c in cands if c == cod}
                    if len(ps) == 1:
                        pid, ligacao = ps.pop(), "nome + município do órgão"
                elif not org or not any(n in org for n, _ in norm_mun):
                    ps = {p for p, _ in cands}
                    if len(ps) == 1 and len(nome.split()) >= 3 and not org.startswith(("PREFEITURA", "CAMARA")):
                        pid, ligacao = ps.pop(), "nome único entre candidatos municipais (a conferir)"
            if not pid:
                continue
            k = (pid, proc or tcu.sem_acento(d.get("orgao", "")) + d.get("ano", ""))
            r = registros.get(k)
            if not r:
                r = registros[k] = {"pessoa_id": pid, "nome_tce": nome, "orgao": d.get("orgao", ""), "natureza": d.get("natureza", ""),
                                    "processo": proc, "exercicio": d.get("exercicio", ""), "data_sessao": iso(d.get("data", "")),
                                    "orgao_julgador": "", "data_publicacao": "", "acordao": d.get("acordao", ""),
                                    "recomendacao_legislativo": "", "ligacao": ligacao, "fonte": fonte, "relacoes": []}
            if ligacao == "cpf + nome":  # ligação mais forte prevalece
                r["ligacao"] = ligacao
            for campo in ("orgao", "natureza", "exercicio", "acordao"):
                r[campo] = r[campo] or d.get(campo, "")
            r["data_sessao"] = r["data_sessao"] or iso(d.get("data", ""))
            if data_cap not in r["relacoes"]:
                r["relacoes"].append(data_cap)
    # o que o script 17 (relações de 2022+) já tem não se repete
    ja = {(r["pessoa_id"], r["processo"]) for r in csv.DictReader(open(os.path.join(DADOS, "indicadores", "tceam_contas_irregulares.csv"), encoding="utf-8"))}
    saida = [dict(r, relacoes=" ".join(f"{x[:4]}-{x[4:6]}-{x[6:]}" for x in sorted(r["relacoes"])))
             for r in registros.values() if (r["pessoa_id"], r["processo"]) not in ja]
    saida.sort(key=lambda x: (x["pessoa_id"], x["processo"]))
    checagens.append((lidos >= 15, f"{lidos} relações lidas de {len(arquivos) - len(exc)} arquivos"))
    checagens.append((len(excluidos) > 0, f"{len(excluidos)} gestores excluídos após revisão (24/09/2020) aplicados à relação de 2020"))
    por_lig = defaultdict(int)
    for x in saida:
        por_lig[x["ligacao"]] += 1
    checagens.append((len(saida) > 0, f"{len(saida)} decisões novas ligadas a {len({x['pessoa_id'] for x in saida})} pessoas "
                                      f"(sem repetir as {len(ja)} do script 17): " + "; ".join(f"{k}: {v}" for k, v in sorted(por_lig.items()))))
    sem_proc = [x for x in saida if not x["processo"]]
    checagens.append((len(sem_proc) <= 0.05 * max(len(saida), 1), f"com número de processo: {len(saida) - len(sem_proc)} de {len(saida)}"))
    texto_saida = " ".join(" ".join(x.values()) for x in saida)
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto_saida) and not any(c in texto_saida for c in cpfs_lidos if len(c) >= 11), "CPF na saída"
    campos = ["pessoa_id", "nome_tce", "orgao", "natureza", "processo", "exercicio", "data_sessao", "orgao_julgador", "data_publicacao",
              "acordao", "recomendacao_legislativo", "ligacao", "relacoes", "fonte"]
    with open(os.path.join(DADOS, "indicadores", "tceam_listas_antigas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(saida)
    for x in saida:
        if x["ligacao"].endswith("(a conferir)"):
            alertas.append(f"{x['pessoa_id']} ({nome_pid[x['pessoa_id']].title()}): ligado só pelo nome “{x['nome_tce']}”, processo "
                           f"{x['processo'] or '?'}, órgão “{x['orgao'] or 'não informado'}”")
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "23_tceam_listas_antigas.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — TCE-AM, relações antigas do Internet Archive (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## Alertas (conferir)\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"relacoes={lidos} decisoes={len(saida)} pessoas={len({x['pessoa_id'] for x in saida})} checagens={ok}/{len(checagens)} "
          f"alertas={len(alertas)} " + str(dict(por_lig)))


if __name__ == "__main__":
    main()
