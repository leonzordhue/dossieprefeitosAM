"""Bens declarados ao TSE pelos candidatos a prefeito, vice-prefeito e vereador do AM (eleições 2008-2024).

Fonte: TSE bem_candidato_<ano>_AM.csv (Lei 9.504/1997, art. 11, § 1º, IV: declaração de bens no registro), baixado por
01_tse_baixar.py. Não existe para 2000 e 2004. Ligação à pessoa: (ano, SG_UE, SQ_CANDIDATO) -> título no consulta_cand.
Valores são os DECLARADOS pelo candidato (em geral valor histórico de aquisição, não de mercado): variação entre
eleições não prova enriquecimento, só aponta onde olhar.

Saídas: dados/bens.csv (um bem por linha), dados/bens_resumo.csv (total por candidatura),
        dados/integridade/06_bens.md
Uso: python -I scripts/06_bens.py
"""
import csv
import hashlib
import os
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSE = os.path.join(BASE_DIR, "dados", "brutos", "tse")
DADOS = os.path.join(BASE_DIR, "dados")
ANOS = (2008, 2012, 2016, 2020, 2024)
CARGOS = {"PREFEITO": "prefeito", "VICE-PREFEITO": "vice-prefeito", "VEREADOR": "vereador"}
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "MÉDIA"}


def ler(arq):
    with open(os.path.join(TSE, arq), encoding="latin1", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def valor(s):
    return float(s.replace(".", "").replace(",", ".")) if s and not s.startswith("#") else None


def gravar(nome, linhas, campos):
    with open(os.path.join(DADOS, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def main():
    mun = {m["cod_tse"]: m for m in csv.DictReader(open(os.path.join(DADOS, "municipios.csv"), encoding="utf-8"))}
    checagens, alertas = [], []
    bens, resumo = [], []
    for ano in ANOS:
        cand = {}
        for r in ler(f"consulta_cand_{ano}_AM.csv"):
            if r["DS_CARGO"].upper() in CARGOS:
                cand[(r["SG_UE"], r["SQ_CANDIDATO"])] = r
        sem_par, invalidos, n = 0, 0, 0
        soma = defaultdict(float)
        qtd = defaultdict(int)
        for b in ler(f"bem_candidato_{ano}_AM.csv"):
            c = cand.get((b["SG_UE"], b["SQ_CANDIDATO"]))
            if c is None:
                sem_par += 1  # bem de candidato a outro cargo (não há outro cargo em eleição municipal) ou registro órfão
                continue
            v = valor(b["VR_BEM_CANDIDATO"])
            if v is None or v < 0:
                invalidos += 1
                alertas.append(f"{ano} SQ {b['SQ_CANDIDATO']}: valor inválido '{b['VR_BEM_CANDIDATO']}'")
                continue
            n += 1
            p = hashlib.sha1(c["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10]
            k = (b["SG_UE"], b["SQ_CANDIDATO"])
            soma[k] += v
            qtd[k] += 1
            bens.append({"pessoa_id": p, "ano": ano, "cargo": CARGOS[c["DS_CARGO"].upper()], "cod_ibge": mun[b["SG_UE"]]["cod_ibge"],
                         "ordem": b.get("NR_ORDEM_BEM_CANDIDATO") or b.get("NR_ORDEM_CANDIDATO", ""),  # nome muda em 2020
                         "tipo": b["DS_TIPO_BEM_CANDIDATO"], "descricao": b["DS_BEM_CANDIDATO"],
                         "valor": round(v, 2), "fonte": f"TSE bem_candidato_{ano} (SQ_CANDIDATO {b['SQ_CANDIDATO']})"})
        for k, c in cand.items():
            resumo.append({"pessoa_id": hashlib.sha1(c["NR_TITULO_ELEITORAL_CANDIDATO"].encode()).hexdigest()[:10], "ano": ano,
                           "cargo": CARGOS[c["DS_CARGO"].upper()], "cod_ibge": mun[k[0]]["cod_ibge"], "municipio": mun[k[0]]["municipio"],
                           "nome": c["NM_CANDIDATO"].title(), "resultado": c["DS_SIT_TOT_TURNO"].upper(),
                           "declarou_bens": c.get("ST_DECLARAR_BENS", ""), "n_bens": qtd.get(k, 0),
                           "patrimonio_declarado": round(soma.get(k, 0.0), 2),
                           "fonte": f"TSE bem_candidato_{ano} + consulta_cand_{ano} (SQ_CANDIDATO {k[1]})"})
        checagens.append((sem_par == 0, f"{ano}: {n} bens ligados a candidatos; {sem_par} sem candidato correspondente; {invalidos} valores inválidos"))
        # quem disse que declarava bens (ST_DECLARAR_BENS=S) e não tem nenhum no arquivo
        faltam = [c for k, c in cand.items() if c.get("ST_DECLARAR_BENS") == "S" and not qtd.get(k)]
        checagens.append((len(faltam) <= 0.02 * len(cand),
                          f"{ano}: {len(faltam)} candidatos marcados 'declara bens' sem bem no arquivo (tolerância 2% de {len(cand)})"))

    # variação do patrimônio de quem foi eleito prefeito e voltou a concorrer (só sinaliza; ver docstring)
    por_pessoa = defaultdict(dict)
    for r in resumo:
        if r["cargo"] == "prefeito":
            por_pessoa[r["pessoa_id"]][r["ano"]] = r
    variacoes = []
    for p, anos in por_pessoa.items():
        seq = sorted(anos)
        for a, b in zip(seq, seq[1:]):
            ra, rb = anos[a], anos[b]
            if ra["resultado"] in ELEITO and ra["patrimonio_declarado"] > 0 and rb["patrimonio_declarado"] >= 5 * ra["patrimonio_declarado"] \
                    and rb["patrimonio_declarado"] - ra["patrimonio_declarado"] >= 1_000_000:
                variacoes.append(f"{rb['nome']} ({rb['municipio']}): R$ {ra['patrimonio_declarado']:,.2f} em {a} (eleito) → "
                                 f"R$ {rb['patrimonio_declarado']:,.2f} em {b}")

    gravar("bens.csv", bens, ["pessoa_id", "ano", "cargo", "cod_ibge", "ordem", "tipo", "descricao", "valor", "fonte"])
    gravar("bens_resumo.csv", resumo, ["pessoa_id", "ano", "cargo", "cod_ibge", "municipio", "nome", "resultado", "declarou_bens",
                                       "n_bens", "patrimonio_declarado", "fonte"])
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "06_bens.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — bens declarados (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Bens: {len(bens)}; candidaturas resumidas: {len(resumo)}\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n")
        f.write("\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n\n")
        f.write("## Prefeitos eleitos cujo patrimônio declarado cresceu 5× ou mais (e ≥ R$ 1 milhão) na eleição seguinte\n\n"
                "Valores declarados pelo próprio candidato; não é prova de irregularidade.\n\n"
                + ("\n".join(f"- {v}" for v in variacoes) or "- nenhum") + "\n\n")
        f.write("## Alertas\n\n" + ("\n".join(f"- ⚠️ {a}" for a in alertas[:200]) or "- nenhum") + "\n")
    print(f"bens={len(bens)} resumo={len(resumo)} checagens={ok}/{len(checagens)} variacoes={len(variacoes)} alertas={len(alertas)}")


if __name__ == "__main__":
    main()
