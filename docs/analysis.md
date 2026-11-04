# Análises e motores externos

## O que o FLORA calcula sozinho (numpy/scipy, sem dependências extras)

| Análise | Onde | Método |
|---|---|---|
| Controle de qualidade | Explorer → Qualidade | reads por amostra, corte de profundidade, % de cloroplasto/mitocôndria; remoção só com confirmação |
| Curvas de rarefação | Explorer → Rarefação | riqueza esperada exata (hipergeométrica), saturação por amostra |
| Diversidade alfa | Explorer → Estatística | Kruskal-Wallis por métrica, q = Benjamini-Hochberg, pares por Mann-Whitney |
| Diversidade beta | Explorer → Estatística | PERMANOVA + PERMDISP (Bray-Curtis, Jaccard, Aitchison), permutações com semente fixa |
| Abundância diferencial | Explorer → Estatística | Mann-Whitney sobre CLR + volcano (aproximação composicional) |
| Metadados MIxS | `GET /api/analysis/mixs` | campos obrigatórios e MIMARKS, por nome e apelidos |
| Exportação | Explorer → Dados | TSV, BIOM, taxonomia; SVG em cada gráfico |

## Motores externos (Configurações → Motores de análise)

O FLORA detecta o que está instalado e roda como jobs em segundo plano, com log, progresso e cancelamento.

| Motor | Uso |
|---|---|
| QIIME 2 | `qiime2-dada2`: manifest FASTQ → DADA2 → classificador → (árvore) → tabelas do FLORA |
| DADA2 (R) | `dada2-r`: pasta de FASTQ + FASTA de referência → ASVs e taxonomia |
| ALDEx2 (R) | `aldex2`: abundância diferencial sobre o projeto ativo |
| ANCOM-BC2, vegan, VSEARCH, cutadapt, scikit-bio | apenas detectados; ainda sem fluxo próprio |

`GET /api/engines` mostra versões e a dica de instalação de cada um.

## Limites conhecidos

- UniFrac exige árvore filogenética: gere-a pelo QIIME 2 (`build_tree`). O endpoint explica isso em vez de calcular algo errado.
- Os fluxos de QIIME 2 e DADA2 foram testados com executáveis simulados; a execução com as ferramentas reais depende da sua instalação.
- As tabelas do MGnify são **perfis taxonômicos** do pipeline deles, não ASVs (não têm sequências).
- Leituras brutas (SRA/ENA) não são analisadas diretamente: processe com QIIME 2 ou DADA2 e ingira o resultado.
