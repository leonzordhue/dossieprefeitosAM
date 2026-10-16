"""Candidatos do AM com contas julgadas irregulares pelo TCE-AM (relações publicadas pelo tribunal).

Fonte: portal de transparência do TCE-AM, página "Gestores com contas julgadas irregulares"
       (https://transparencia.tce.am.gov.br/?page_id=17767). Cada relação sai em PDF e em planilha (.xlsx/.xls) com
       responsável, CPF, órgão, natureza, processo, exercício, data da sessão, órgão julgador, acórdão e julgamento.
       Só as planilhas são lidas (o PDF é a mesma relação). A relação anual vai ao TRE-AM (Lei 9.504/1997, art. 11, § 5º).
       A página traz as relações de 2022 em diante (sessões de jan/2022 a jun/2026, conferido em 16/10/2026).
Ligação: SÓ por CPF idêntico ao do registro de candidatura no TSE (consulta_cand 2000-2020; em 2024 o TSE mascara o CPF).
Homônimo sem CPF igual não entra; CPF igual com nome diferente também não (erro de digitação na relação) e vai
para a lista de conferência. O CPF não é publicado: a saída traz só o pessoa_id.
Conta julgada irregular não é inelegibilidade automática (LC 64/1990, art. 1º, I, g: exige irregularidade insanável
que configure ato doloso de improbidade, decisão irrecorrível; quem decide é a Justiça Eleitoral).

Saídas: dados/indicadores/tceam_contas_irregulares.csv, dados/integridade/17_tceam.md
Uso: python -I scripts/17_tceam.py
"""
import csv
import hashlib
import html
import io
import os
import re
import sys
from datetime import date, datetime
from difflib import SequenceMatcher

import openpyxl
import xlrd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402
from importlib import import_module  # noqa: E402

tcu = import_module("13_tcu")  # mesma ligação por CPF (so_digitos, sem_acento)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
TSE = os.path.join(DADOS, "brutos", "tse")
PAGINA = "https://transparencia.tce.am.gov.br/?page_id=17767"
BAIXAR = ("https://transparencia.tceam.tc.br/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd&task=file.download"
          "&wpfd_category_id={c}&wpfd_file_id={f}")
# cabeçalho normalizado (sem acento, maiúsculo, só letras) -> campo; casa pelo começo do texto
CAMPOS = (("RESPONSAVEL", "nome_tce"), ("CPF", "cpf"), ("ORGAOJULGADOR", "orgao_julgador"), ("ORGAO", "orgao"),
          ("NATUREZA", "natureza"), ("PROCESSO", "processo"), ("EXERCICIO", "exercicio"), ("DATADASESSAO", "data_sessao"),
          ("DATADEPUBLICACAO", "data_publicacao"), ("NUMERODOACORDAO", "acordao"), ("RECOMENDACAO", "recomendacao_legislativo"),
          ("JULGAMENTO", "julgamento"))


def linhas_planilha(b):
    """Linhas (listas de valores) de .xlsx ou .xls."""
    if b[:2] == b"PK":
        ws = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
        return [list(r) for s in ws.worksheets for r in s.iter_rows(values_only=True)]
    if b[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        wb = xlrd.open_workbook(file_contents=b)
        return [s.row_values(i) for s in wb.sheets() for i in range(s.nrows)]
    return None


def cpf_de(x):
    """CPF (11 dígitos) se a célula for um CPF: formatado 000.000.000-00 ou só dígitos (a planilha às vezes guarda como número)."""
    t = str(x if x is not None else "").strip()
    if isinstance(x, float) and x.is_integer():
        t = str(int(x))
    if re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}", t) or re.fullmatch(r"\d{8,11}", t):
        return re.sub(r"\D", "", t).zfill(11)
    return None


def mesmo_nome(a, b):
    """Mesmo nome a menos de grafia (acento, preposição, letra trocada): semelhança ≥ 0,85 só nas letras."""
    x, y = tcu.sem_acento(a), tcu.sem_acento(b)
    return bool(x and y) and (x == y or SequenceMatcher(None, x, y).ratio() >= 0.85)


def txt(v):
    t = "" if v is None else str(v).strip()
    return "" if t in ("None", "-", "não consta") else t


def iso(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", txt(v))
    return f"{m[3]}-{m[2]}-{m[1]}" if m else txt(v)[:10]


def main():
    cpf_pid, nome_pid = {}, {}
    for a in tcu.ANOS_CPF:
        with open(os.path.join(TSE, f"consulta_cand_{a}_AM.csv"), encoding="latin1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                c = tcu.so_digitos(r["NR_CPF_CANDIDATO"])
                if c.strip("0") and not r["NR_CPF_CANDIDATO"].startswith("-"):
                    p = hashlib.sha1(r["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10]
                    cpf_pid[c] = p if cpf_pid.get(c, p) == p else None  # mesmo CPF com títulos diferentes: ambíguo, não liga
                    nome_pid[p] = r["NM_CANDIDATO"]
    pag = html.unescape(rede.get(PAGINA, cache=False).decode("utf-8", "replace"))
    arquivos = {}
    for m in re.finditer(r'<a[^>]+href="([^"]*wpfd_category_id=(\d+)[^"]*wpfd_file_id=(\d+)[^"]*)"[^>]*>(.*?)</a>', pag, re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", m[4]).strip()
        if t and t.lower() != "baixar" or (m[2], m[3]) not in arquivos:  # cada arquivo tem um link com o nome e outro "Baixar"
            arquivos[(m[2], m[3])] = t
    checagens, alertas = [(len(arquivos) >= 20, f"{len(arquivos)} arquivos listados na página do TCE-AM")], []
    registros, vistos, n_planilhas, n_pdf = [], set(), 0, 0
    for (cat, fid), titulo in sorted(arquivos.items()):
        url = BAIXAR.format(c=cat, f=fid)
        b = rede.get(url)
        tab = linhas_planilha(b)
        if tab is None:
            n_pdf += b[:4] == b"%PDF"
            continue
        n_planilhas += 1
        col = None
        for r in tab:
            cel = [tcu.sem_acento(str(x or "")) for x in r]
            if col is None:
                if any(c == "CPF" for c in cel) and any(c.startswith("RESPONSAVEL") for c in cel):
                    col = {}
                    for i, c in enumerate(cel):
                        # layout antigo: processo em "Número" (+ "Ano"), com "Processo Digital" vazio
                        campo = {"NUMERO": "proc_num", "ANO": "proc_ano"}.get(c) or next((k for p, k in CAMPOS if c.startswith(p) and k not in col), None)
                        if campo:
                            col[campo] = i
                continue
            # as planilhas têm colunas ocultas e linhas desalinhadas: o CPF é procurado na própria linha e o deslocamento
            # em relação ao cabeçalho é aplicado aos demais campos
            achados = [(i, cpf_de(x)) for i, x in enumerate(r) if cpf_de(x)]
            if len(achados) != 1:
                continue
            i_cpf, cpf = achados[0]
            desl = i_cpf - col["cpf"]
            d = {k: (r[i + desl] if 0 <= i + desl < len(r) else "") for k, i in col.items() if k != "nome_tce"}
            if not re.fullmatch(r"\d+/\d{4}", str(d.get("processo") or "").strip()) and d.get("proc_num"):
                num_, ano_ = str(d["proc_num"]).strip().removesuffix(".0"), str(d.get("proc_ano") or "").strip().removesuffix(".0")
                d["processo"] = num_ if "/" in num_ or not ano_ else f"{num_}/{ano_}"
            d["nomes"] = [str(x).strip() for x in r[:i_cpf] if isinstance(x, str) and len(x.split()) >= 2]
            k = (cpf, txt(d.get("processo")), re.sub(r"\W", "", str(d.get("acordao", ""))).upper())
            if k in vistos:  # a mesma decisão volta em várias relações (mensal e anual)
                continue
            vistos.add(k)
            registros.append((cpf, d, titulo, url))
        if col is None:
            alertas.append(f"arquivo {fid} “{titulo}”: planilha sem cabeçalho reconhecido (CPF/Responsável)")
    checagens.append((n_planilhas >= 10 and registros, f"{n_planilhas} planilhas lidas ({n_pdf} PDFs ignorados, mesma relação); "
                                                      f"{len(registros)} decisões distintas"))
    linhas, por_nome = [], []
    for cpf, d, titulo, url in registros:
        p = cpf_pid.get(cpf)
        if not p:
            continue
        nome = next((n for n in d["nomes"] if mesmo_nome(n, nome_pid[p])), None)
        if not nome:  # CPF igual e nome diferente: erro de digitação na relação ou no registro; não liga
            por_nome.append(f"{p} ({nome_pid[p].title()}): o CPF aparece na relação “{titulo}”, processo {d.get('processo')}, "
                            f"com o nome “{' / '.join(d['nomes']) or 'vazio'}”; não ligado")
            continue
        # exercício "1900" = célula de data vazia no Excel
        linhas.append({"pessoa_id": p, "nome_tce": nome, "orgao": txt(d.get("orgao")),
                       "natureza": txt(d.get("natureza")), "processo": txt(d.get("processo")),
                       "exercicio": ex if (ex := txt(d.get("exercicio")).removesuffix(".0")) > "1990" else "", "data_sessao": iso(d.get("data_sessao")),
                       "orgao_julgador": txt(d.get("orgao_julgador")), "data_publicacao": iso(d.get("data_publicacao")),
                       "acordao": re.sub(r"\s+", " ", txt(d.get("acordao"))),
                       "recomendacao_legislativo": txt(d.get("recomendacao_legislativo")), "ligacao": "cpf + nome",
                       "fonte": f"TCE-AM, relação “{titulo}” ({url})"})
    checagens.append((True, f"ligados por CPF e nome: {len(linhas)}; CPF igual com nome diferente (não ligados, ver lista): {len(por_nome)}"))
    ruins = [x for x in linhas if not re.fullmatch(r"\d+(/\d{4})?", x["processo"]) or not re.match(r"\d{4}-\d{2}-\d{2}$", x["data_sessao"])]
    checagens.append((len(ruins) <= 0.02 * max(len(linhas), 1), f"processo e data da sessão em formato válido: {len(linhas) - len(ruins)} de {len(linhas)}"))
    for x in ruins[:30]:
        alertas.append(f"{x['pessoa_id']}: processo “{x['processo']}” / sessão “{x['data_sessao']}” fora do formato ({x['fonte'][:60]})")
    linhas.sort(key=lambda x: (x["pessoa_id"], x["data_sessao"]))
    with open(os.path.join(DADOS, "indicadores", "tceam_contas_irregulares.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["pessoa_id", "nome_tce", "orgao", "natureza", "processo", "exercicio", "data_sessao", "orgao_julgador",
                               "data_publicacao", "acordao", "recomendacao_legislativo", "ligacao", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "17_tceam.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — TCE-AM contas irregulares (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Decisões ligadas a candidatos: {len(linhas)} ({len({x['pessoa_id'] for x in linhas})} pessoas)\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + "\n\n## CPF igual e nome diferente — não ligados (verificar)\n\n" + ("\n".join(f"- ⚠️ {a}" for a in por_nome) or "- nenhuma")
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"arquivos={len(arquivos)} planilhas={n_planilhas} decisoes={len(registros)} ligadas={len(linhas)} "
          f"pessoas={len({x['pessoa_id'] for x in linhas})} checagens={ok}/{len(checagens)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
