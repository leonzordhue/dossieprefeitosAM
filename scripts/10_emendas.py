"""Emendas parlamentares federais recebidas pelas prefeituras do AM (CGU, Portal da Transparência), 2014 em diante.

Fonte: https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO (download sem chave),
       arquivo EmendasParlamentares_PorFavorecido.csv: cada pagamento por favorecido, mês, autor e tipo de emenda.
Entra o que foi pago a ente municipal do AM (natureza jurídica "Município", "Fundo Público da Administração Direta
Municipal", "Órgão Público do Poder Executivo Municipal"). Pagamento a empresa ou associação no município NÃO entra:
não é recurso que passou pela prefeitura. "Transferência especial" é a emenda Pix (CF art. 166-A, I).

Saídas: dados/indicadores/emendas_recebidas.csv (cod_ibge, ano, autor, tipo_emenda, favorecido, valor_recebido, fonte),
        dados/integridade/10_emendas.md
Uso: python -I scripts/10_emendas.py
"""
import csv
import io
import os
import sys
import unicodedata
import zipfile
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rede  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
ZIP = os.path.join(DADOS, "brutos", "cgu", "EmendasParlamentares.zip")
MUNICIPAL = {"Município", "Fundo Público da Administração Direta Municipal", "Órgão Público do Poder Executivo Municipal"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.upper().replace("'", " ").replace("-", " ").split())


def main():
    os.makedirs(os.path.dirname(ZIP), exist_ok=True)
    if not os.path.exists(ZIP):
        open(ZIP, "wb").write(rede.get(URL, cache=False))
    muns = {norm(m["municipio"]): m["cod_ibge"] for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, alertas = [], []
    soma = defaultdict(float)
    sem_mun = defaultdict(float)
    n_lidas = dup = 0
    vistas = set()
    with zipfile.ZipFile(ZIP) as z:
        rd = csv.DictReader(io.TextIOWrapper(z.open("EmendasParlamentares_PorFavorecido.csv"), encoding="latin-1", newline=""), delimiter=";")
        for r in rd:
            if r["UF Favorecido"] != "AM" or r["Natureza Jurídica"] not in MUNICIPAL:
                continue
            n_lidas += 1
            linha = tuple(r.values())
            dup += linha in vistas  # linha idêntica repetida = pagamento contado duas vezes
            vistas.add(linha)
            v = float(r["Valor Recebido"].replace(".", "").replace(",", "."))
            cod = muns.get(norm(r["Município Favorecido"]))
            if not cod:
                sem_mun[r["Município Favorecido"]] += v
                continue
            k = (cod, r["Ano/Mês"][:4], r["Nome do Autor da Emenda"].title(), r["Tipo de Emenda"], r["Favorecido"].title())
            soma[k] += v
    checagens.append((not sem_mun, f"{n_lidas} pagamentos a entes municipais do AM; município não reconhecido: {dict(sem_mun) or 'nenhum'}"))
    checagens.append((dup == 0, f"linhas idênticas repetidas no arquivo da CGU: {dup}"))
    cods = {k[0] for k in soma}
    checagens.append((len(cods) >= 55, f"{len(cods)} dos 62 municípios receberam emenda paga no período (esperado quase todos)"))
    linhas = [{"cod_ibge": c, "ano": a, "autor": au, "tipo_emenda": t, "favorecido": f, "valor_recebido": round(v, 2),
               "fonte": f"CGU {URL} (EmendasParlamentares_PorFavorecido.csv)"} for (c, a, au, t, f), v in sorted(soma.items())]
    with open(os.path.join(DADOS, "indicadores", "emendas_recebidas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    por_ano = defaultdict(float)
    for x in linhas:
        por_ano[x["ano"]] += x["valor_recebido"]
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "10_emendas.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — emendas recebidas (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n## Total pago a entes municipais do AM por ano\n\n"
                + "\n".join(f"- {a}: R$ {v:,.2f}" for a, v in sorted(por_ano.items())) + "\n\n## Alertas\n\n"
                + ("\n".join(f"- ⚠️ {a}" for a in alertas) or "- nenhum") + "\n")
    print(f"linhas={len(linhas)} municipios={len(cods)} checagens={ok}/{len(checagens)}")


if __name__ == "__main__":
    main()
