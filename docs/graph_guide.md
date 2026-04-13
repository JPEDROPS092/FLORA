# Guia dos Graficos do FLORA

Este documento explica o papel analitico de cada figura gerada pela pipeline EMP e como interpretar os principais sinais biologicos e computacionais.

## Visao Geral

Os graficos do FLORA foram organizados em quatro blocos:

- diversidade beta e ordenacao, para observar separacao estrutural entre amostras;
- diversidade alfa, para resumir riqueza e uniformidade local;
- composicao taxonomica, para mostrar quais grupos biologicos sustentam as diferencas;
- desempenho de modelo, para verificar qualidade preditiva e interpretabilidade.

## PCoA Bray-Curtis

Arquivo: `docs/assets/emp/pcoa_braycurtis.png`

O que mostra:

- cada ponto representa uma amostra;
- a distancia entre pontos reflete dissimilaridade composicional com base em Bray-Curtis;
- a cor representa a classe `empo_3`.

Como interpretar:

- grupos bem separados sugerem assinaturas microbianas distintas entre ambientes;
- sobreposicao ampla indica fronteiras biologicas menos claras;
- outliers podem representar amostras raras, ruído biologico ou problemas de metadado.

No seu caso:

- a separacao visual entre `Plant surface`, `Soil (non-saline)` e `Animal proximal gut` ajuda a justificar o bom `ROC-AUC` do classificador.

## Shannon por Classe

Arquivo: `docs/assets/emp/alpha_shannon.png`

O que mostra:

- distribuicao do indice de Shannon por grupo;
- combina riqueza e equitabilidade.

Como interpretar:

- caixas mais altas indicam comunidades mais diversas e menos dominadas por poucos taxa;
- variancia alta sugere heterogeneidade intra-grupo;
- pontos extremos merecem verificacao porque podem carregar sinal biologico ou artefato.

## Chao1 por Classe

Arquivo: `docs/assets/emp/alpha_chao1.png`

O que mostra:

- estimativa de riqueza, com maior sensibilidade a taxa raros.

Como interpretar:

- valores altos sugerem maior riqueza potencial;
- diferencas entre Shannon e Chao1 ajudam a separar dois fenomenos:
  riqueza total versus distribuicao de abundancias.

## Heatmap de Beta Diversidade

Arquivo: `docs/assets/emp/beta_heatmap.png`

O que mostra:

- matriz de distancias entre todas as amostras;
- blocos frios ou quentes indicam pares mais proximos ou mais distantes.

Como interpretar:

- blocos compactos ao longo da diagonal sugerem subconjuntos coesos;
- transicoes bruscas entre blocos sugerem grupos ecologicos bem definidos;
- linhas muito discrepantes podem indicar amostras atipicas.

## Composicao Taxonomica por Classe

Arquivo: `docs/assets/emp/taxonomy_barplot.png`

O que mostra:

- abundancia relativa agregada por filo;
- comparacao direta entre classes ambientais.

Como interpretar:

- filos dominantes ajudam a explicar separacao de grupos;
- perfis similares entre barras sugerem comunidades proximas;
- a categoria `Other` resume taxa menos frequentes para melhorar leitura.

Uso no relatorio:

- este grafico e o mais util para discutir assinatura ecologica em alto nivel.

## Heatmap Taxonomico

Arquivo: `docs/assets/emp/taxonomy_heatmap.png`

O que mostra:

- abundancia relativa dos generos mais relevantes por amostra;
- permite identificar concentracoes locais de taxa.

Como interpretar:

- faixas verticais fortes indicam generos recorrentes;
- manchas localizadas sugerem associacoes mais especificas a certos subconjuntos;
- combina bem com PCoA para conectar padrao visual e composicao biologica.

## ROC

Arquivo: `docs/assets/emp/roc_curve.png`

O que mostra:

- capacidade do modelo distinguir classes em varios limiares;
- uma curva e desenhada para cada classe, mais a media global.

Como interpretar:

- curvas proximas do canto superior esquerdo indicam classificacao forte;
- linha diagonal representa desempenho aleatorio;
- `AUC` alto com matriz de confusao ainda ruim em uma classe minoritaria pede cautela.

## Matriz de Confusao

Arquivo: `docs/assets/emp/confusion_matrix.png`

O que mostra:

- proporcao de acertos e erros por classe real e prevista.

Como interpretar:

- diagonal principal forte indica bom desempenho;
- erros sistematicos fora da diagonal mostram quais classes se confundem entre si;
- e particularmente importante em datasets desbalanceados como o EMP filtrado.

## Importancia de Features

Arquivo: `docs/assets/emp/feature_importance.png`

O que mostra:

- ranking das ASVs mais utilizadas pelo modelo XGBoost.

Como interpretar:

- features com peso alto influenciam fortemente a decisao;
- importancia alta nao implica causalidade biologica;
- a etapa seguinte e mapear essas ASVs para taxonomia ou contexto ecologico.

## Resumo SHAP

Arquivo: `docs/assets/emp/shap_summary.png`

O que mostra:

- impacto medio absoluto de cada feature na predicao;
- e uma camada de interpretabilidade mais robusta que importancia bruta do modelo.

Como interpretar:

- valores maiores indicam features mais determinantes para a fronteira de decisao;
- se uma feature aparece tanto no ranking de importancia quanto no SHAP, ela merece destaque no texto;
- como o ambiente local tem incompatibilidade parcial com `shap/cv2/numpy`, este grafico deve ser citado com nota metodologica.

## Ordem Recomendada no Relatorio

Sugestao de narrativa:

1. comecar por PCoA e heatmap beta para mostrar separacao global;
2. entrar em Shannon e Chao1 para discutir diversidade local;
3. usar barplot e heatmap taxonomico para interpretar biologicamente os grupos;
4. fechar com ROC, matriz de confusao, importancia de features e SHAP.

## Frases Prontas

Voce pode reutilizar trechos como:

- "A ordenacao por Bray-Curtis revelou estruturacao parcial das amostras segundo a categoria ambiental `empo_3`."
- "Os boxplots de diversidade alfa indicaram heterogeneidade entre os grupos, com diferencas tanto em riqueza estimada quanto em uniformidade."
- "Os graficos taxonomicos sugerem que a separacao observada no espaco de coordenadas principais e sustentada por mudancas consistentes na composicao microbiana."
- "Os resultados do classificador demonstram viabilidade preditiva, mas o desbalanceamento entre classes recomenda interpretacao cuidadosa do F1-macro."
