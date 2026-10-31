# Reporting Plan

## Objetivo

Transformar o modulo de relatorios do FLORA em um fluxo de publicacao:

1. `HTML` como formato canonico, editavel e visualizavel no navegador.
2. `PDF` como artefato derivado para submissao, compartilhamento e arquivamento.
3. Mesmo backend servindo preview, exportacao e reprodutibilidade do conteudo analitico.

## Abordagem recomendada

### 1. Fonte unica do relatorio

- Gerar um `report.html` autocontido com metricas, tabelas, figuras Plotly e notas metodologicas.
- Tratar esse HTML como a versao editavel e revisavel do documento.
- Incluir `print CSS` para que o mesmo artefato possa ser exportado por navegador ou pipeline automatizado.

### 2. Exportacao para PDF

- Manter o `HTML` como obrigatorio.
- Gerar `PDF` apenas como etapa complementar.
- Usar `WeasyPrint` no backend quando a dependencia estiver disponivel.
- Quando o exportador nao estiver instalado, retornar aviso claro sem falhar a geracao do HTML.

### 3. Preview integrado na UI

- Expor endpoint de preview para carregar o relatorio dentro da interface.
- Permitir abrir em nova aba para revisao, impressao e compartilhamento.
- Mostrar warnings de seções puladas por falta de dados, em vez de falhas silenciosas.

### 4. Estrutura editorial sugerida

- Resumo executivo do dataset e do estado da analise.
- Checklist de cobertura analitica.
- Qualidade e composicao do dataset.
- Diversidade alfa e beta.
- Estrutura da comunidade com PCoA.
- Taxonomia agregada e heatmap.
- Notas metodologicas, limitacoes e exportacao.

### 5. Evolucao posterior

- Adicionar template tematico institucional para relatorios PIBIC, artigo e suplementar.
- Permitir blocos editaveis de texto no frontend com persistencia em JSON/YAML.
- Versionar relatorios com manifesto da execucao, parametros e hashes dos artefatos.
- Incluir anexos exportaveis: CSV de metricas, SVG/PNG de figuras e bundle ZIP do estudo.
