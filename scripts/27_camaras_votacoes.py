"""Votações das Câmaras do interior tiradas das atas de sessão publicadas no Diário Oficial dos Municípios (AAM/SIGPub):
o que foi votado, o resultado, o autor e quem votou contra, quando a ata diz. Complementa o SAPL (script 20, 12 Câmaras).

Fonte: atas listadas pelo script 26 (dados/camaras_aam_materias.csv), texto integral em
       https://www.diariomunicipal.com.br/aam/materia/<código> (cache em dados/brutos/cache_http).
Método (texto da própria ata):
  - deliberação: "colocou em votação o/a <Requerimento|Projeto de Lei|Projeto de Resolução|Indicação|Moção|Veto|...>"
    seguido, na mesma passagem, de "aprovado/rejeitado" e, se houver, "por unanimidade" ou "N votos favoráveis/contrários";
  - autor: "autoria do(a) Vereador(a) NOME" ou "defesa do(a) Vereador(a) NOME" logo antes da votação;
  - contra: "votaram contra os Vereadores A, B" / "voto contrário do(a) Vereador(a) NOME";
  - nomes ligados (grafia estrita, regra do script 24) a candidato a vereador do município no TSE.
A ata resume a sessão: votação que ela não registra não aparece. O resultado é o que a ata diz, com o link.

Saídas: dados/camaras_aam_votacoes.csv, dados/integridade/27_camaras_votacoes.md
Uso: python -I scripts/27_camaras_votacoes.py   (depois do 26; lê o cache, quase sem rede)
"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from importlib import import_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
c26 = import_module("26_camaras_aam")  # corpo(), MISTO, aam (estrito, NOME)
aam = c26.aam

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(BASE_DIR, "dados")
NOMEV = "(" + c26.MISTO + "|" + aam.NOME + ")"
MATERIA = (r"(?i:(?:colocou|p[ôo]s|submeteu|levou)\s+(?:em|a|à)\s+(?:vota[çc][ãa]o|aprecia[çc][ãa]o)\s+(?:d?[oa]s?\s+)?)"
           r"(?i:(requerimento|projeto\s+de\s+lei(?:\s+complementar)?|projeto\s+de\s+resolu[çc][ãa]o|projeto\s+de\s+decreto\s+legislativo|"
           r"indica[çc][ãa]o|mo[çc][ãa]o|veto|emenda|parecer|presta[çc][ãa]o\s+de\s+contas|contas))"
           r"((?:\s+(?:n[º°o.]*|n[úu]mero)\s*[\d./-]+)?)")
RESULTADO = re.compile(r"(?i)\b(aprovad[oa]s?|rejeitad[oa]s?)\b(.{0,120})")
UNANIME = re.compile(r"(?i)unanimidade|un[âa]nime")
RESULTADO_VOTO = re.compile(r"(?i)\b(aprovad[oa]s?|rejeitad[oa]s?)\b(?=[^.]{0,160}?(?:unanimidade|un[âa]nime|votos?|maioria|vota[çc][ãa]o))"
                            r"|(?<=vota[çc][ãa]o)[^.]{0,120}?\b(aprovad[oa]s?|rejeitad[oa]s?)\b")
MATERIA_CITADA = (r"(?i:(requerimento|projeto\s+de\s+lei(?:\s+complementar)?|projeto\s+de\s+resolu[çc][ãa]o|projeto\s+de\s+decreto\s+legislativo|"
                  r"indica[çc][ãa]o|mo[çc][ãa]o|veto|emenda|parecer|presta[çc][ãa]o\s+de\s+contas))((?:\s+(?:n[º°o.]*|n[úu]mero)\s*[\d./-]+)?)")
PLACAR_UM = re.compile(r"(?i)(\d{1,2}|um|dois|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze)\s+votos?\s+(?:favor[áa]veis|a\s+favor)")
PLACAR = re.compile(r"(?i)(\d{1,2})\s*(?:\([a-zç ]+\)\s*)?votos?\s+(?:favor[áa]veis|a\s+favor|sim)[^.]{0,60}?(\d{1,2})\s*(?:\([a-zç ]+\)\s*)?votos?\s+(?:contr[áa]rios?|contra|n[ãa]o)")
AUTOR = re.compile(r"(?i:(?:autoria|defesa)\s+d[oa]s?\s+(?:nobre\s+)?(?:vereador(?:a)?|edil|ver\.))\s+" + NOMEV)
CONTRA = re.compile(r"(?i:votaram\s+contr[áa]ri(?:o|amente)|votaram\s+contra|voto\s+contr[áa]rio\s+d[oa]s?)\s+(?:(?i:os?|as?)\s+)?(?:(?i:vereador(?:a|es|as)?)\s+)?"
                    r"([^.;]{3,200})")


def votacoes(a, t, ligar):
    """Deliberações no texto de uma ata. a: cod_ibge, data, titulo, fonte; ligar(cod, nome) -> pessoa_id.
    Também usada pelo script 28 (edições completas do diário)."""
    out = []
    achou, vistos = 0, set()
    # âncora no resultado de votação ("aprovado por unanimidade", "rejeitado por 5 votos", "foi aprovado o Projeto ... com 6 votos");
    # "lida e aprovada" (a própria ata) e "para que seja aprovado" (pedido) não contam
    for r in RESULTADO_VOTO.finditer(t):
        ctx_antes, ctx_depois = t[max(0, r.start() - 260):r.start()], t[r.start():r.end() + 160]
        if re.search(r"(?i)lida\s+e\s*$|seja\s*$|sejam\s*$|ser\s*$|j[áa]\s+foi\s*$", ctx_antes):
            continue
        mats = list(re.finditer(MATERIA_CITADA, ctx_antes)) or list(re.finditer(MATERIA_CITADA, ctx_depois[:120]))
        if not mats:
            continue
        m = mats[-1]
        chave = (" ".join(m.group(1).split()).lower(), " ".join(m.group(2).split()), r.start() // 400)
        if chave in vistos:
            continue
        vistos.add(chave)
        achou += 1
        autores = AUTOR.findall(t[max(0, r.start() - 500):r.end() + 120])
        autor = autores[-1] if autores else ""
        pl = PLACAR.search(ctx_depois) or PLACAR_UM.search(ctx_depois)
        contra = CONTRA.search(ctx_depois)
        contra_pids = []
        if contra:
            for n in re.split(r",|\se\s", contra.group(1)):
                n = n.strip(" -–")
                p = ligar(a["cod_ibge"], n) if len(n.split()) >= 2 else ""
                if p:
                    contra_pids.append(p)
        out.append({"cod_ibge": a["cod_ibge"], "data_ata": a["data"], "materia": " ".join(m.group(1).split()).capitalize(),
                       "numero": " ".join(m.group(2).split()), "resultado": "aprovado" if (r.group(1) or r.group(2)).lower().startswith("aprov") else "rejeitado",
                       "unanimidade": "sim" if UNANIME.search(ctx_depois[:120]) else "",
                       "votos_favor": pl.group(1) if pl else "", "votos_contra": (pl.group(2) if pl and pl.re is PLACAR else "") if pl else "",
                       "autor_no_ato": autor, "autor_pessoa_id": ligar(a["cod_ibge"], autor) if autor else "",
                       "contra_pessoa_ids": " ".join(dict.fromkeys(contra_pids)), "titulo_ata": a["titulo"], "fonte": a["fonte"]})
    return out


def main():
    cand = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(DADOS, "candidaturas_vereador.csv"), encoding="utf-8")):
        cand[r["cod_ibge"]].append((r["pessoa_id"], r["nome"], r["nome_urna"]))

    def ligar(cod, n):
        return next((p for p, nm, urna in cand[cod] if aam.estrito(n, nm) or (urna and len(urna.split()) >= 2 and aam.estrito(n, urna))), "")

    atas = [r for r in csv.DictReader(open(os.path.join(DADOS, "camaras_aam_materias.csv"), encoding="utf-8"))
            if re.match(r"ATA\b", r["titulo"].upper()) and not re.search(r"REGISTRO\s+DE\s+PRE|PREG[ÃA]O|LICITA", r["titulo"].upper())]
    linhas, lidas, sem_votacao = [], 0, 0
    for a in atas:
        try:
            t = c26.corpo(a["codigo"])
        except Exception:
            continue
        lidas += 1
        novas = votacoes(a, t, ligar)
        linhas += novas
        achou = len(novas)
        sem_votacao += not achou
    checagens = [(lidas >= 0.97 * len(atas), f"atas lidas: {lidas} de {len(atas)}"),
                 (len(linhas) >= 300, f"deliberações extraídas: {len(linhas)} em {len({x['cod_ibge'] for x in linhas})} Câmaras "
                                      f"({sem_votacao} atas sem votação reconhecida)"),
                 (sum(1 for x in linhas if x["autor_pessoa_id"]) >= 100, f"com autor ligado ao TSE: {sum(1 for x in linhas if x['autor_pessoa_id'])}")]
    with open(os.path.join(DADOS, "camaras_aam_votacoes.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(linhas[0].keys()) if linhas else ["cod_ibge"])
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda x: (x["cod_ibge"], x["data_ata"])))
    res = Counter((x["resultado"], x["unanimidade"]) for x in linhas)
    ok = sum(1 for o, _ in checagens if o)
    with open(os.path.join(DADOS, "integridade", "27_camaras_votacoes.md"), "w", encoding="utf-8") as f:
        f.write(f"# Integridade — votações nas atas das Câmaras (AAM/SIGPub) (gerado em {datetime.now():%d/%m/%Y %H:%M})\n\n"
                f"- Deliberações: {len(linhas)}; resultados: {dict(res)}\n- Matérias: {dict(Counter(x['materia'] for x in linhas).most_common(8))}\n"
                f"- Com voto contrário nominal: {sum(1 for x in linhas if x['contra_pessoa_ids'])}\n- Checagens: **{ok} de {len(checagens)} passaram**\n\n"
                + "\n".join(f"- {'✅' if o else '❌'} {d}" for o, d in checagens) + "\n")
    print(f"atas={lidas} deliberacoes={len(linhas)} checagens={ok}/{len(checagens)} {dict(res)}")


if __name__ == "__main__":
    if "--teste" in sys.argv:
        t = ("Após a defesa da Vereadora Miriam de Castro Gomes o senhor presidente colocou em votação o Requerimento nº 12/2025 onde foi "
             "aprovado por Unanimidade de votos. Em seguida colocou em votação o Projeto de Lei nº 5/2025, que foi rejeitado por 5 votos "
             "favoráveis e 4 votos contrários; votaram contra os Vereadores Igo Campos, Edgar Litaiff.")
        ms = list(re.finditer(MATERIA, t))
        assert [m.group(1) for m in ms] == ["Requerimento", "Projeto de Lei"], [m.group(1) for m in ms]
        assert RESULTADO.search(t[ms[0].end():]).group(1) == "aprovado"
        assert AUTOR.findall(t[:ms[0].start()]) == ["Miriam de Castro Gomes"]
        assert PLACAR.search(t[ms[1].end():]).groups() == ("5", "4")
        assert CONTRA.search(t[ms[1].end():]).group(1).startswith("Igo Campos")
        print("ok")
    else:
        main()
