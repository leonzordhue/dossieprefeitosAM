# Dossiê dos Prefeitos e Vereadores do Amazonas (2001–2028)

Compilação, a partir de fontes públicas oficiais, de quem governou e legislou nos **62 municípios do Amazonas** desde as eleições de 2000. O objetivo é avaliar cada gestão: eleição, gastos por área, mínimos legais, pessoal, recursos recebidos, indicadores sociais e patrimônio declarado.

**Para consultar:** https://leonzordhue.github.io/politicosAM/ (plataforma que junta este repositório com [deputadosfederais](https://github.com/leonzordhue/deputadosfederais) e [senadorAM](https://github.com/leonzordhue/senadorAM)).

> **Integridade em primeiro lugar.** Todo dado traz a fonte (arquivo ou URL oficial). Cada etapa gera um relatório de checagens em `dados/integridade/`. Quando um ponto não pôde ser confirmado, ele aparece como **lacuna** ou **alerta**, nunca como estimativa.

## Situação

| Etapa | Script | Fonte | Estado |
|---|---|---|---|
| Mandatos e eleições de prefeito (2000–2024, com suplementares) | `02_mandatos.py` | TSE | ✅ 1.337 checagens ok |
| Vereadores: candidaturas e eleitos | `05_vereadores.py` | TSE | ✅ 448 checagens ok |
| Patrimônio declarado (2008–2024) | `06_bens.py` | TSE | ✅ |
| Fotos (2004–2024) | `07_fotos.py` | TSE | ✅ |
| Finanças 2000–2012 | `04_finbra.py` | Tesouro (FINBRA) | ✅ |
| Finanças 2014–2025: despesa por função, receita, pessoal/RCL | `03_siconfi.py` | Tesouro (SICONFI) | ✅ |
| Série harmonizada de finanças | `11_financas.py` | FINBRA + SICONFI + IBGE | ✅ (2013 sem fonte) |
| População e PIB | `08_ibge.py` | IBGE (SIDRA) | ✅ |
| IDEB por rede (2005–2023) | `09_ideb.py` | INEP | ✅ |
| Emendas parlamentares pagas às prefeituras (2014+) | `10_emendas.py` | CGU | ✅ |
| Mínimos da educação: MDE 25%, FUNDEB (2017–2025) | `12_siope.py` | SIOPE/FNDE | ✅ |
| Inabilitados pelo TCU (ligação só por CPF) | `13_tcu.py` | TCU | ✅ |
| Mínimo da saúde: % da receita própria em saúde (15%) e R$/hab. (2002–2025) | `14_siops.py` | SIOPS/MS (relatório de indicadores municipais) | ✅ |
| IDHM e dimensões (1991, 2000, 2010) | `15_idhm.py` | Atlas do Desenvolvimento Humano via Ipeadata | ✅ |
| Fundamentos de julgamento da candidatura (indeferimento, cassação) 2016–2024 | `16_julgamentos.py` | TSE motivo_cassacao | ✅ |
| Contas julgadas irregulares pelo TCE-AM (relações 2022–2026; ligação por CPF + nome) | `17_tceam.py` | TCE-AM | ✅ |
| Quem governou de fato: suplementares | `02_mandatos.py` | TSE | ✅ |
| Prefeito declarado pela prefeitura × eleito no TSE (sinal de interino/sucessão), 2008–2026 | `18_prefeito_declarado.py` | SIOPE/FNDE (responsáveis; 2024+ consultado por município) | ✅ sinal a conferir, não prova |
| Decisões do TCE-AM desde 2016 em que prefeito/vice é parte (termos: irregular, multa, alcance, ato ilegal) | `19_tceam_decisoes.py` | API de jurisprudência do TCE-AM | ✅ classificação automática; PDF oficial junto |
| Câmaras no SAPL: vereadores, matérias e autoria, normas, votações, votos nominais, Mesa Diretora (12 Câmaras) | `20_sapl.py` | SAPL/Interlegis de cada Câmara | ✅ |
| Quanto cada prefeito arrecadou e gastou na gestão (R$ corrigidos pelo IPCA) | `21_gestoes.py` | série de `11_financas.py` + IPCA/IBGE | ✅ |
| Gastos das Câmaras: despesa empenhada na função 01 – Legislativa (2002+, FINBRA/DCA; MSC como conferência) e pessoal do Legislativo (RGF, 2014+) | `22_camaras_financas.py` | FINBRA + SICONFI | ✅ 58–62 Câmaras por ano |
| Contas irregulares do TCE-AM de 2006 a 2021 (relações antigas retiradas do portal) | `23_tceam_listas_antigas.py` | TCE-AM, cópias do Internet Archive (Wayback) | ✅ ligação por CPF + nome ou nome + município (órgão, jurisprudência do TCE-AM ou Diário Oficial); 97 só pelo nome, a conferir |
| Quem assinou atos como prefeito(a): interinos, vices em exercício, presidente da Câmara (61 municípios, 2009+) | `24_prefeito_atos_aam.py` | Diário Oficial dos Municípios (AAM/SIGPub) | ✅ sinal a conferir; link do ato junto |
| O mesmo para Manaus (2000+) | `25_prefeito_atos_manaus.py` | DOM Manaus, texto do Querido Diário/OKBR (pacotes anuais) | ✅ de 2009 em diante o nome não está no texto: "em exercício" = vice presumido; sem "em exercício" = titular (296 de 312 meses) |
| Câmaras do interior no Diário Oficial: todas as publicações (61 Câmaras), suplentes em ato de posse/convocação (com o motivo citado) e autoria de projetos | `26_camaras_aam.py` | Diário Oficial dos Municípios (AAM/SIGPub) | ✅ 12.836 matérias; sinal a conferir, link do ato junto |
| Votações registradas nas atas das sessões (matéria, resultado, placar, autor, votos contrários quando a ata cita) | `27_camaras_votacoes.py` | atas do AAM/SIGPub | ✅ só o que a ata registra |

## Dados (`dados/`)

- `municipios.csv`, `pessoas.csv` (o `pessoa_id` é o sha1 do título de eleitor, 10 caracteres; título e CPF não são publicados).
- `candidaturas_prefeito.csv`, `mandatos.csv`, `candidaturas_vereador.csv`, `mandatos_vereador.csv`.
- `bens.csv` (um bem por linha) e `bens_resumo.csv` (total por candidatura).
- `financas/`: saídas brutas do FINBRA (formato longo) e do SICONFI.
- `indicadores/`: `financas.csv`, `ibge.csv`, `ideb.csv`, `emendas_recebidas.csv`, `siope.csv`, `tcu_inabilitados.csv`.
- `integridade/`: um relatório por script, com checagens, lacunas e alertas para verificação humana.
- `../fotos/<pessoa_id>.jpg` (240 px).

## Limitações conhecidas

- **O TSE não registra quem governou de fato.** Os scripts 18, 24 e 25 dão sinais (prefeito declarado ao FNDE; quem assina atos no Diário Oficial), cada um com a fonte, mas a ligação do nome do ato ao candidato do TSE é por grafia e precisa de conferência humana. Posse de suplente de vereador vem dos atos das Câmaras no Diário Oficial (script 26), só onde a Câmara publicou.
- O arquivo de candidatos do TSE é incompleto. Algumas candidaturas existem só no arquivo de votação e foram recuperadas de lá, com `origem_dado` marcada. Em Novo Airão (2008), o resultado de vereador é `#NULO` nos dois arquivos, e por isso fica como lacuna.
- O início de mandato por eleição suplementar usa a data da eleição (`inicio_aproximado = sim`).
- Finanças: o que a prefeitura declarou ao Tesouro. Ano em branco significa que não declarou. Saltos bruscos aparecem como alerta, porque costumam ser declaração incompleta.
- Participação de saúde e educação na despesa **não** é o cálculo dos mínimos constitucionais. Para a educação, use `siope.csv`. Em 2020 e 2021 vale a EC 119/2022.

## Como reproduzir

```
python -I scripts/01_tse_baixar.py && python -I scripts/02_mandatos.py && python -I scripts/05_vereadores.py && python -I scripts/07_fotos.py
python -I scripts/03_siconfi.py && python -I scripts/04_finbra.py && python -I scripts/08_ibge.py && python -I scripts/11_financas.py
python -I scripts/06_bens.py && python -I scripts/09_ideb.py && python -I scripts/10_emendas.py && python -I scripts/12_siope.py && python -I scripts/13_tcu.py && python -I scripts/14_siops.py && python -I scripts/15_idhm.py && python -I scripts/16_julgamentos.py && python -I scripts/17_tceam.py && python -I scripts/18_prefeito_declarado.py && python -I scripts/19_tceam_decisoes.py && python -I scripts/20_sapl.py && python -I scripts/21_gestoes.py && python -I scripts/22_camaras_financas.py
python -I scripts/23_tceam_listas_antigas.py && python -I scripts/24_prefeito_atos_aam.py && python -I scripts/25_prefeito_atos_manaus.py && python -I scripts/26_camaras_aam.py && python -I scripts/27_camaras_votacoes.py
```
A ordem 02 → 05 → 07 importa, porque os três escrevem em `pessoas.csv`. Requer Python 3.12, `truststore`, `Pillow`, `openpyxl` e, para o FINBRA, `pyodbc` com o driver do Access.
