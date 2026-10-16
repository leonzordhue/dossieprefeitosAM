"""Mínimo constitucional da saúde nas prefeituras do AM, declarado ao SIOPS (Ministério da Saúde), por ano.

Fonte: SIOPS — relatório "Indicadores Municipais" (http://siops.datasus.gov.br/relindicadoresmun2.php), formulário
       consdetalhereenvio2.php com cmbAno, cmbUF=13, cmbPeriodo=2 (anual até 2012; 6º bimestre = ano fechado a partir de 2013)
       e cmbMunicipio[] = código IBGE de 6 dígitos. A API nova (siops-consulta-publica-api.saude.gov.br) está sem
       documentação publicada (Swagger desligado, conferido em 16/10/2026), por isso o relatório público.
Indicadores usados (numeração do SIOPS):
  3.2  % da receita própria (impostos e transferências constitucionais) aplicada em ações e serviços públicos de saúde
       — mínimo 15% para municípios (CF art. 198, § 2º, III; LC 141/2012, art. 7º; ADCT art. 77, III, desde 2004).
       2000-2003 foram anos de transição da EC 29/2000 (ADCT art. 77, § 1º: pelo menos 7% em 2000, subindo até 15% em 2004):
       ficam sem mínimo marcado.
  2.1  despesa total com saúde sob responsabilidade do município, R$ por habitante
É o que o município declarou; a verificação oficial é do TCE-AM.

Saídas: dados/indicadores/siops.csv (cod_ibge, ano, indicador, valor, minimo, cumpriu, observacao, descricao, fonte),
        dados/integridade/14_siops.md
Uso: python -I scripts/14_siops.py   (~1 requisição/s; respostas em dados/brutos/cache_http)
"""
import csv
import html
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
URL = "http://siops.datasus.gov.br/consdetalhereenvio2.php"
ANOS = range(2000, datetime.now().year)
INDIC = {"3.2": ("asps_pct", lambda a: 15.0 if a >= 2004 else None), "2.1": ("saude_rs_por_habitante", lambda a: None)}


def numero(s):
    return float(s.replace(".", "").replace(",", "."))


def ler(html_txt):
    """{código do indicador: (descrição, valor)} a partir do relatório. Com mais de uma transmissão no ano, vale a última coluna."""
    out = {}
    for tr in re.split(r"(?i)</tr>", html_txt):  # as células de uma linha vêm quebradas em várias linhas do HTML
        linha = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", tr)))
        m = re.match(r"\s*(\d\.\d)\s+(.+?)\s+(?:R\$\s*)?(-?[\d.]*\d,\d+)\s*%?", linha)
        if m and m.group(1) in INDIC:
            vals = re.findall(r"(-?[\d.]*\d,\d+)\s*%?", linha[m.start(3):])
            out[m.group(1)] = (re.sub(r"\s+", " ", m.group(2)).strip(), numero(vals[-1]))
    return out


def main():
    muns = list(csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8")))
    assert len(muns) == 62, "rode 02_mandatos.py antes"
    checagens, alertas, linhas, falta, errados = [], [], [], [], []
    for a in ANOS:
        n = 0
        for m in muns:
            corpo = urlencode({"cmbAno": a, "cmbUF": "13", "cmbPeriodo": "2", "cmbMunicipio[]": m["cod_ibge"][:6],
                               "BtConsultar": "Consultar"}).encode()
            if not rede.em_cache(URL + "\n" + corpo.decode()):
                time.sleep(1)
            h = rede.get(URL, data=corpo).decode("latin1", "replace")
            ind = ler(h)
            if ind and f"{m['cod_ibge'][:6]}-" not in h:  # o relatório traz "código-Nome - AM"; sem isso a resposta é de outro ente
                errados.append((a, m["municipio"]))
                continue
            if "3.2" not in ind:
                falta.append((a, m["municipio"]))
                continue
            n += 1
            fonte = f"SIOPS/MS {URL} (ano {a}, período anual/6º bimestre, município {m['cod_ibge'][:6]})"
            for cod, (desc, val) in ind.items():
                nome, minimo = INDIC[cod]
                mi = minimo(a)
                linhas.append({"cod_ibge": m["cod_ibge"], "ano": a, "indicador": nome, "valor": val, "minimo": "" if mi is None else mi,
                               "cumpriu": "" if mi is None else "sim" if val >= mi else "não",
                               "observacao": "transição da EC 29/2000 (ADCT art. 77, § 1º): mínimo progressivo até 2004"
                               if nome == "asps_pct" and a < 2004 else "",
                               "descricao": desc, "fonte": fonte})
        print(a, n, flush=True)
        if n:
            checagens.append((n >= 50, f"{a}: {n} de 62 municípios com o % aplicado em saúde no SIOPS"))
    checagens.append((not errados, f"respostas do SIOPS de outro município que não o pedido: {len(errados)}"))
    # integridade: percentual entre 0 e 100; zero é declaração incompleta, não aplicação zero
    fora = [x for x in linhas if x["indicador"] == "asps_pct" and not 0 < x["valor"] <= 100]
    for x in fora:  # erro da declaração: fica publicado, marcado e fora da comparação com o mínimo
        x["cumpriu"], x["observacao"] = "", "valor declarado inválido (zero, negativo ou acima de 100%); erro da declaração"
    n_pct = sum(1 for x in linhas if x["indicador"] == "asps_pct")
    checagens.append((len(fora) <= 0.01 * n_pct, f"% aplicado fora de (0, 100]: {len(fora)} de {n_pct} (tolerância 1%; marcados e fora da comparação)"))
    nomes = {m["cod_ibge"]: m["municipio"] for m in muns}
    for x in fora:
        alertas.append(f"{x['ano']} {nomes[x['cod_ibge']]}: % em saúde declarado {x['valor']} — provável declaração incompleta ou erro")
    os.makedirs(os.path.join(DADOS, "indicadores"), exist_ok=True)
    with open(os.path.join(DADOS, "indicadores", "siops.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["cod_ibge", "ano", "indicador", "valor", "minimo", "cumpriu", "observacao", "descricao", "fonte"])
        w.writeheader()
        w.writerows(linhas)
    ok = sum(1 for o, _ in checagens if o)
    abaixo = [x for x in linhas if x["cumpriu"] == "não" and x["valor"] > 0]
    with open(os.path.join(DADOS, "integridade", "14_siops.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — SIOPS (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Linhas: {len(linhas)}\n"
                f"- Checagens: **{ok} de {len(checagens)} passaram**\n\n" + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens)
                + f"\n\n## Declarações abaixo do mínimo de 15% ({len(abaixo)})\n\nValor declarado pelo município; a apuração oficial é do TCE-AM.\n\n"
                + "\n".join(f"- {x['ano']} {nomes[x['cod_ibge']]}: {x['valor']}%" for x in abaixo)
                + f"\n\n## Sem dados no SIOPS ({len(falta)})\n\n" + ", ".join(f"{n} {a}" for a, n in falta)
                + "\n\n## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} checagens={ok}/{len(checagens)} abaixo={len(abaixo)} faltas={len(falta)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
