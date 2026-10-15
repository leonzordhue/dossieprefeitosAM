# Dossiê dos Prefeitos do Amazonas (2001–2028)

Compilação, a partir de fontes públicas oficiais, de quem governou cada um dos **62 municípios do Amazonas** desde as eleições de 2000. O objetivo é avaliar o desempenho de cada gestão. Para cada mandato, o projeto reúne eleição, gastos por área, cumprimento dos mínimos legais, recursos recebidos, indicadores sociais e patrimônio declarado.

> **Integridade em primeiro lugar.** Todo dado traz a fonte (arquivo ou URL oficial). Cada etapa gera um relatório de checagens em `dados/integridade/`. Quando um ponto não pôde ser confirmado, ele aparece como **lacuna** ou **alerta**, nunca como estimativa.

## Situação

| Etapa | Fonte | Estado |
|---|---|---|
| 1. Mandatos e eleições (2000–2024, com suplementares) | TSE — Dados Abertos | ✅ pronto, 1.337 checagens ok |
| 2. Finanças municipais: receita, despesa por função, pessoal/RCL, saúde, educação | Tesouro — SICONFI (2014+) e FINBRA (2000–2013) | ⏳ |
| 3. Transferências federais, convênios e emendas recebidas | Portal da Transparência / Transferegov | ⏳ |
| 4. Indicadores: população, PIB, IDEB, IDHM | IBGE, INEP, Atlas Brasil | ⏳ |
| 5. Patrimônio declarado e contas de campanha | TSE | ⏳ |
| 6. Dossiês: por município, por mandato (cada 4 anos) e por prefeito | gerados dos dados acima | ⏳ |
| 7. Contas julgadas, rejeições e improbidade | TCE-AM, TSE (inelegíveis), CNJ | ⏳ |

## Dados prontos (`dados/`)

- `municipios.csv`: os 62 municípios, com código IBGE e código TSE.
- `candidaturas_prefeito.csv`: cada candidatura a prefeito por turno, com partido, coligação, vice, situação, resultado, votos e % dos votos nominais.
- `mandatos.csv`: quem governou cada município em cada ciclo, incluindo mandatos completados por eleição suplementar e **lacunas** explícitas.
- `pessoas.csv`: candidatos (nome, nascimento, gênero, naturalidade). O `pessoa_id` é derivado do título de eleitor (sha1, 10 caracteres). Nem título nem CPF são publicados.
- `integridade/02_mandatos.md`: todas as checagens e os alertas para verificação humana.

## Limitações conhecidas (etapa 1)

- **O TSE não registra quem governou de fato.** O projeto não captura afastamentos, cassações pela Câmara, mortes ou renúncias seguidas de posse do vice ou do presidente da Câmara sem nova eleição. Esses casos serão completados com fontes citadas (TRE-AM, Diário Oficial, Câmaras).
- O arquivo de candidatos do TSE é incompleto. Algumas candidaturas existem só no arquivo de votação, como as suplementares de 2008 em Anamã, Coari e Tefé, e foram recuperadas de lá, com a coluna `origem_dado` marcada.
- O início dos mandatos de eleição suplementar usa a data da eleição (`inicio_aproximado = sim`), porque a data de posse não está no TSE.

## Como reproduzir

```
python -I scripts/01_tse_baixar.py   # baixa os zips do TSE e guarda só os CSVs do AM (com sha256 em _proveniencia.json)
python -I scripts/02_mandatos.py     # gera mandatos, candidaturas e o relatório de integridade
```
Requer Python 3.12 e `truststore`.
