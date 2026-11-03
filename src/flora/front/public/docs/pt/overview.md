# Visão geral

O FLORA leva um estudo de amplicons 16S da **tabela de ASVs ao relatório**, em cinco etapas. Cada etapa registra a **proveniência**: parâmetros, versões dos pacotes e seed.

1. **Ingestão** — metadados, tabela de ASVs e taxonomia, com QC por amostra.
2. **Normalização** — rarefação, TSS ou CLR.
3. **Exploração** — diversidade alfa/beta, PCoA e taxonomia.
4. **Modelagem** — Random Forest e XGBoost.
5. **Relatório** — seções editáveis, exportação HTML/PDF.

## Projetos

Cada projeto tem **diretório e banco DuckDB próprios**, então os dados nunca se misturam. Crie um em *Projetos*, instale um exemplo (o sintético funciona offline) e ative-o: todas as telas passam a mostrar os dados do projeto ativo.

## Atalhos

- `Ctrl K` abre a paleta de comandos.
- `Ctrl J` abre o copiloto.
