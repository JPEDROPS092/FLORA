# 1 · Ingestão

Reconcilia três arquivos: **metadados**, **tabela de ASVs** e **taxonomia**.

## Pré-visualização

Antes de gravar, o *Pipeline Studio* compara metadados e tabela e classifica cada amostra:

| Status | Quando |
|---|---|
| `pass` | está nos dois arquivos, tem leituras suficientes e grupo definido |
| `warn` | profundidade abaixo do limiar ou sem grupo |
| `fail` | ausente de um dos arquivos ou com zero leituras |

O limiar é a **profundidade de rarefação** configurada na etapa de normalização.

## Formatos

- ASVs em TSV **largo** (amostras × ASVs) ou **longo** (`sample_id`, `feature_id`, `abundance`), ou BIOM.
- Colunas extras dos metadados ficam disponíveis como grupos de comparação.

> A importação de FASTQ, remoção de primers e denoise (QIIME2/DADA2) acontecem **fora** do FLORA.
