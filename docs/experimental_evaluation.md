# Experimental Evaluation

## Objetivo Cientifico

Esta secao organiza a avaliacao experimental do FLORA como trabalho cientifico, e nao apenas como demonstracao de engenharia. O foco e responder se a biblioteca produz ganho metodologico real ao combinar:

- ingestao microbiologica estruturada;
- normalizacao composicional;
- machine learning supervisionado;
- interpretacao biologica dos atributos discriminantes.

## Hipotese Explicita

> A normalizacao composicional CLR melhora a separacao entre classes ambientais e o desempenho preditivo em relacao a abundancias brutas, mantendo interpretabilidade biologica plausivel dos atributos mais importantes.

Hipoteses auxiliares:

- modelos supervisionados treinados sobre dados CLR apresentam maior estabilidade que modelos treinados sobre contagens brutas;
- a combinacao entre filtro por prevalencia e CLR reduz ruído e melhora o equilibrio entre desempenho e interpretabilidade;
- os atributos mais discriminantes podem ser reconectados a grupos taxonomicos biologicamente plausiveis.

## Pipeline Biologico e Computacional

### 1. Ingestao biologica

Antes do dado entrar no DuckDB, o fluxo biologico ideal considerado pelo FLORA e:

1. controle de qualidade dos reads;
2. remocao de primers/adaptadores e trimming;
3. denoising por DADA2;
4. geracao de ASVs;
5. remocao de quimeras;
6. classificacao taxonomica por base de referencia;
7. exportacao de `metadata`, `asv_table` e `taxonomy`.

Mesmo quando o FLORA recebe tabelas ja prontas, a interpretacao cientifica do pipeline depende dessa cadeia biologica anterior. Isso precisa estar explicito em qualquer relatorio ou defesa.

### 2. Ingestao analitica

Depois da etapa biologica, o FLORA executa:

1. carga de `metadata.tsv`, `asv_table.tsv` ou BIOM e `taxonomy.tsv`;
2. persistencia em DuckDB;
3. geracao de matriz larga por amostra;
4. transformacao `raw`, `TSS` ou `CLR`;
5. filtro por prevalencia;
6. diversidade alfa e beta;
7. treino, validacao e relatorio.

### 3. Ligacao entre ML e biologia

O ponto central do FLORA nao e apenas classificar amostras. O valor cientifico surge quando a predicao pode ser reconectada a estrutura biologica:

- PCoA e heatmaps mostram separacao de comunidades;
- Shannon e Chao1 mostram diferencas de diversidade local;
- composicao taxonomica explica parte da separacao entre grupos;
- importancia de features e SHAP indicam quais ASVs dirigem a classificacao;
- o mapeamento dessas ASVs para filos e generos fecha a ponte entre padrao estatistico e interpretacao ecologica.

Em outras palavras, o ML no FLORA deve funcionar como instrumento de inferencia auxiliar, e nao como caixa-preta isolada.

## Comparacao Metodologica Atual

O benchmark ja implementado no projeto compara:

- baseline majoritario;
- Random Forest;
- XGBoost;
- SVM;
- normalizacoes `raw`, `TSS` e `CLR`;
- validacao cruzada repetida;
- sensibilidade a profundidade de rarefacao;
- sensibilidade ao filtro de prevalencia.

### Comparacao principal no EMP

Em vez de apresentar apenas uma lista longa de configuracoes, a comparacao abaixo foi organizada para responder tres perguntas:

1. o problema e trivial ou realmente exige modelagem?
2. a normalizacao influencia o resultado?
3. qual configuracao entrega o melhor equilibrio entre desempenho e interpretabilidade?

| Grupo | Normalizacao | Modelo | Accuracy | Balanced Acc. | F1-macro | ROC-AUC | N features | Leitura cientifica |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline | Raw | Majority | 0.7529 | 0.3333 | 0.2864 | 0.5000 | 1177 | mostra que a classe majoritaria sozinha nao resolve o problema |
| Comparacao inicial | Raw | XGBoost | 0.9294 | 0.8252 | 0.8204 | 0.9946 | 1177 | sinal biologico forte ja aparece mesmo sem transformacao composicional |
| Comparacao inicial | TSS | Random Forest | 0.9471 | 0.8838 | 0.8801 | 0.9941 | 1177 | abundancia relativa melhora estabilidade frente ao dado bruto |
| Comparacao inicial | TSS | XGBoost | 0.9471 | 0.8782 | 0.8757 | 0.9952 | 1177 | desempenho alto, com ganho consistente em relacao ao dado cru |
| Comparacao central | CLR | Random Forest | 0.9471 | 0.8615 | 0.8721 | 0.9924 | 1177 | camada composicional preserva desempenho com boa robustez |
| Melhor resultado | CLR | XGBoost | 0.9529 | 0.8919 | 0.8903 | 0.9936 | 1177 | melhor equilibrio geral entre separacao, sensibilidade entre classes e plausibilidade metodologica |
| Referencia adicional | CLR | SVM | 0.9294 | 0.8085 | 0.8072 | 0.9874 | 1177 | competitivo, mas inferior a XGBoost e Random Forest |

### Efeito da normalizacao sobre o melhor modelo

Como a hipotese central do trabalho e metodologica, faz sentido destacar a comparacao mantendo o modelo constante.

| Modelo fixo | Normalizacao | Accuracy | Balanced Acc. | F1-macro | ROC-AUC | Delta F1 vs Raw | Interpretacao |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| XGBoost | Raw | 0.9294 | 0.8252 | 0.8204 | 0.9946 | 0.0000 | referencia sem tratamento composicional |
| XGBoost | TSS | 0.9471 | 0.8782 | 0.8757 | 0.9952 | +0.0553 | ganho claro com abundancia relativa |
| XGBoost | CLR | 0.9529 | 0.8919 | 0.8903 | 0.9936 | +0.0699 | melhor resultado global e melhor suporte para a hipotese do trabalho |

### Leitura da comparacao

- o baseline majoritario mostra que `accuracy` isolada seria enganosa, porque o problema e desbalanceado;
- `raw + XGBoost` ja produz resultado alto, indicando que existe estrutura biologica discriminante real no EMP;
- `TSS` melhora bastante o comportamento do modelo, sugerindo que tratar a matriz como abundancia relativa ja reduz parte do ruido;
- `CLR + XGBoost` entrega o melhor `F1-macro` e a melhor `balanced_accuracy`, o que sustenta a hipotese de que a normalizacao composicional agrega valor cientifico ao pipeline;
- o ganho de CLR sobre raw e mais convincente em metricas sensiveis ao desbalanceamento do que em `accuracy` simples.

## Robustez

### Sensibilidade a profundidade de rarefacao

| Sampling depth | Accuracy | Balanced Acc. | F1-macro | ROC-AUC | N features | Interpretacao |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 3000 | 0.9375 | 0.7057 | 0.6931 | 0.9912 | 995 | profundidade baixa retém mais amostras, mas piora equilibrio entre classes |
| 5000 | 0.9803 | 0.9883 | 0.9693 | 0.9948 | 1193 | melhor equilibrio observado |
| 8000 | 0.9857 | 0.9648 | 0.9544 | 1.0000 | 1048 | desempenho muito alto, com menos amostras |
| 10000 | 0.9609 | 0.8667 | 0.8228 | 1.0000 | 1005 | profundidade alta remove mais amostras e reduz robustez |

Leitura:

- a rarefacao nao e neutra;
- `5000` apareceu como melhor compromisso entre retencao de amostras e qualidade preditiva;
- `10000` mostrou que aumentar profundidade pode custar mais do que entregar ganho real.

### Sensibilidade ao filtro de prevalencia

| Prevalencia minima | Accuracy | Balanced Acc. | F1-macro | ROC-AUC | N features | Interpretacao |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 0.01 | 0.9359 | 0.8307 | 0.8410 | 0.9645 | 9748 | muitas features, maior risco de ruido |
| 0.03 | 0.9416 | 0.8446 | 0.8475 | 0.9670 | 2616 | bom equilibrio inicial |
| 0.05 | 0.9356 | 0.8236 | 0.8236 | 0.9943 | 1177 | mais compacto, com ROC muito alto |
| 0.10 | 0.9356 | 0.8420 | 0.8441 | 0.9759 | 532 | forte compactacao sem colapso de desempenho |
| 0.15 | 0.9123 | 0.7908 | 0.7860 | 0.9637 | 347 | filtro agressivo demais |

Leitura:

- o filtro por prevalencia muda fortemente a dimensionalidade;
- valores entre `0.03` e `0.10` parecem mais defensaveis;
- `0.15` ja remove sinal demais.

## Interpretacao Biologica

### Top features e taxonomia

As top ASVs mapeadas sugerem que a classificacao nao esta apoiada em ruido arbitrario. Entre os grupos mais frequentes entre os atributos discriminantes aparecem:

- Proteobacteria;
- Planctomycetes;
- Firmicutes;
- Bacteroidetes;
- Chloroflexi;
- Acidobacteria.

### Sinal taxonomico agregado

| Phylum | N features | Score total |
| --- | ---: | ---: |
| Proteobacteria | 11 | 0.0571 |
| Planctomycetes | 2 | 0.0110 |
| Firmicutes | 1 | 0.0088 |
| Bacteroidetes | 1 | 0.0058 |
| Chloroflexi | 1 | 0.0047 |
| Acidobacteria | 1 | 0.0043 |

### Ligacao ML ↔ biologia

Essa distribuicao e importante por tres motivos:

1. mostra que o modelo nao depende de um unico atributo isolado;
2. sugere coerencia com ecossistemas microbianos diversos e nao com artefato puramente numerico;
3. permite discutir o resultado em linguagem biologica, e nao apenas computacional.

No texto do relatorio, isso deve aparecer como:

- separacao estatistica observada no espaco de coordenadas principais;
- reforco por mudancas em diversidade alfa;
- sustentacao biologica por grupos taxonomicos plausiveis entre as features mais relevantes.

## Limitacoes

Esta secao precisa estar explicita para a banca.

### Limitacoes biologicas

- o FLORA aceita tabelas ja processadas, mas a qualidade final depende do pipeline biologico anterior;
- o relatorio atual ainda nao detalha completamente primers, regiao 16S, parametros de denoising e base taxonomica em cada dataset;
- parte da interpretacao biologica ainda esta em nivel de filo/genero e pode ser aprofundada.

### Limitacoes estatisticas

- o benchmark principal ainda esta concentrado no EMP;
- parte dos experimentos reais ampliados foi preparada no codigo, mas requer reexecucao completa para atualizar todos os artefatos;
- o desbalanceamento entre classes impacta `F1-macro` e `balanced_accuracy`, exigindo cautela na leitura de `accuracy`.

### Limitacoes computacionais

- tuning e benchmark completos ainda sao custosos em tempo;
- a etapa de SHAP depende de ambiente mais estavel por causa da compatibilidade entre `numpy`, `cv2` e binarios externos;
- ainda faltam checkpoints incrementais no benchmark longo.

## Discussao Cientifica

O projeto ja demonstra claramente tres pontos:

- existe sinal biologico suficiente nos dados para classificacao ambiental;
- a camada composicional nao e apenas uma escolha estetica, mas uma estrategia metodologica defensavel;
- o FLORA ja permite sair de uma tabela microbiologica e chegar a uma interpretacao quantitativa estruturada.

O que ainda precisa ser fortalecido para fechar o argumento cientifico:

- repetir o benchmark ampliado com mais datasets reais;
- consolidar comparacoes entre `raw`, `TSS` e `CLR` em mais de uma base;
- formalizar melhor a secao de ingestao biologica;
- discutir explicitamente porque certos hiperparametros e filtros foram escolhidos.

## Plano de Acao

### Semana 1

- definir hipotese central do trabalho;
- rodar comparacao com e sem CLR;
- registrar criterios biologicos da ingestao.

### Semana 2

- adicionar baseline de ML;
- rodar validacao cruzada repetida;
- consolidar tabela comparativa principal.

### Semana 3

- escrever secao de comparacao metodologica;
- melhorar a discussao da ligacao entre ML e biologia;
- fechar a secao de limitacoes e ameacas a validade.

## Mensagem central do projeto

O FLORA ja e:

- forte tecnicamente;
- inovador para o nivel PIBIC;
- acima do padrao de prototipo simples.

O que falta agora nao e infraestrutura. O que falta e demonstrar, de forma comparativa e cientificamente argumentada, o valor do que foi construido.

## Arquivos Relacionados

- `results/benchmark/benchmark_summary.csv`
- `results/benchmark/rarefaction_sensitivity.csv`
- `results/benchmark/prevalence_sensitivity.csv`
- `results/benchmark/top_features_taxonomy.csv`
- `results/benchmark/taxonomic_signal.csv`
- `docs/graph_guide.md`
- `docs/technical_execution_report.md`
