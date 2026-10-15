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
| Mínimo da saúde (15%) | — | SIOPS | ⏳ sem API aberta localizada |
| Contas julgadas pelo TCE-AM, cassações, quem governou de fato | — | TCE-AM, TRE-AM, Câmaras | ⏳ |
| IDHM | — | Atlas Brasil | ⏳ |

## Dados (`dados/`)

- `municipios.csv`, `pessoas.csv` (o `pessoa_id` é o sha1 do título de eleitor, 10 caracteres; título e CPF não são publicados).
- `candidaturas_prefeito.csv`, `mandatos.csv`, `candidaturas_vereador.csv`, `mandatos_vereador.csv`.
- `bens.csv` (um bem por linha) e `bens_resumo.csv` (total por candidatura).
- `financas/`: saídas brutas do FINBRA (formato longo) e do SICONFI.
- `indicadores/`: `financas.csv`, `ibge.csv`, `ideb.csv`, `emendas_recebidas.csv`, `siope.csv`, `tcu_inabilitados.csv`.
- `integridade/`: um relatório por script, com checagens, lacunas e alertas para verificação humana.
- `../fotos/<pessoa_id>.jpg` (240 px).

## Limitações conhecidas

- **O TSE não registra quem governou de fato.** Afastamentos, cassações pela Câmara, mortes, renúncias e posse de suplente de vereador não estão capturados. Esses casos serão completados com fontes citadas.
- O arquivo de candidatos do TSE é incompleto. Algumas candidaturas existem só no arquivo de votação e foram recuperadas de lá, com `origem_dado` marcada. Em Novo Airão (2008), o resultado de vereador é `#NULO` nos dois arquivos, e por isso fica como lacuna.
- O início de mandato por eleição suplementar usa a data da eleição (`inicio_aproximado = sim`).
- Finanças: o que a prefeitura declarou ao Tesouro. Ano em branco significa que não declarou. Saltos bruscos aparecem como alerta, porque costumam ser declaração incompleta.
- Participação de saúde e educação na despesa **não** é o cálculo dos mínimos constitucionais. Para a educação, use `siope.csv`. Em 2020 e 2021 vale a EC 119/2022.

## Como reproduzir

```
python -I scripts/01_tse_baixar.py && python -I scripts/02_mandatos.py && python -I scripts/05_vereadores.py && python -I scripts/07_fotos.py
python -I scripts/03_siconfi.py && python -I scripts/04_finbra.py && python -I scripts/08_ibge.py && python -I scripts/11_financas.py
python -I scripts/06_bens.py && python -I scripts/09_ideb.py && python -I scripts/10_emendas.py && python -I scripts/12_siope.py && python -I scripts/13_tcu.py
```
A ordem 02 → 05 → 07 importa, porque os três escrevem em `pessoas.csv`. Requer Python 3.12, `truststore`, `Pillow`, `openpyxl` e, para o FINBRA, `pyodbc` com o driver do Access.
