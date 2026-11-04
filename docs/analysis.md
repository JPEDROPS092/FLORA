# Análises e motores externos

## O que o FLORA calcula sozinho (numpy/scipy, sem dependências extras)

| Análise | Onde | Método |
|---|---|---|
| Controle de qualidade | Explorer → Qualidade | reads por amostra, corte de profundidade, % de cloroplasto/mitocôndria; remoção só com confirmação |
| Curvas de rarefação | Explorer → Rarefação | riqueza esperada exata (hipergeométrica), saturação por amostra |
| Diversidade alfa | Explorer → Estatística | Kruskal-Wallis por métrica, q = Benjamini-Hochberg, pares por Mann-Whitney |
| Diversidade beta | Explorer → Estatística | PERMANOVA + PERMDISP (Bray-Curtis, Jaccard, Aitchison, UniFrac), permutações com semente fixa; conferência opcional com o scikit-bio |
| Abundância diferencial | Explorer → Estatística | Mann-Whitney sobre CLR + volcano (aproximação composicional) |
| Metadados MIxS | `GET /api/analysis/mixs` | campos obrigatórios e MIMARKS, por nome e apelidos |
| Exportação | Explorer → Dados | TSV, BIOM, taxonomia; SVG em cada gráfico |

## UniFrac

Implementado no próprio FLORA (não ponderado e ponderado normalizado), conferido contra valores calculados à mão.
Precisa de uma árvore Newick cujas pontas tenham os IDs das features: envie-a em Explorer → Estatística, ou gere-a no
QIIME 2 com "Construir árvore" (ela é salva no projeto ao ingerir o resultado). O UniFrac não ponderado só olha
presença e ausência, então não separa grupos quando todas as features aparecem em todas as amostras.

## Conectar o QIIME 2 e o DADA2 (Motores de análise → Ambientes)

O QIIME 2 e o DADA2 quase sempre vivem num ambiente conda à parte. O FLORA não precisa rodar dentro dele:

- **Descoberta:** procura ambientes com QIIME 2 ou o pacote `dada2` do R em `~/miniconda3`, `~/anaconda3`, `~/mambaforge`,
  `~/miniforge3`, `~/micromamba`, `/opt/conda` e em `CONDA_PREFIX`/`MAMBA_ROOT_PREFIX`. Só olha o disco, não executa nada.
- **Configuração:** "Usar este ambiente" (ou caminhos manuais) guarda o `python`, o `qiime` e o `Rscript` em
  `<workdir>/engines.json`. Só caminhos absolutos de executáveis existentes são aceitos.
- **Duas formas de falar com o QIIME 2:**
  - *CLI* — o FLORA chama o `qiime` configurado;
  - *API Python* — o FLORA roda o `flora/engines/q2_bridge.py` com o Python do ambiente do QIIME 2, usando `qiime2.Artifact` e o
    plugin DADA2. Gera o mesmo `export/` da CLI, então a conversão é idêntica.
- O DADA2 também roda pelo `Rscript` configurado (fluxo `dada2-r`).

## Motores externos (Motores de análise)

O FLORA detecta o que está instalado e roda como jobs em segundo plano, com log, progresso e cancelamento.

| Fluxo | Ferramenta | O que faz |
|---|---|---|
| `qiime2-dada2` | QIIME 2 | manifest FASTQ → DADA2 → classificador → (árvore) → tabelas do FLORA, com ingestão opcional |
| `dada2-r` | DADA2 (R) | pasta de FASTQ + FASTA de referência → ASVs e taxonomia |
| `cutadapt-trim` | cutadapt | remove primers (pareado ou não) e gera um manifest para o QIIME 2 |
| `vsearch-otu` | VSEARCH | agrupa os ASVs do projeto em OTUs (identidade configurável) e soma as contagens |
| `aldex2`, `ancombc2` | R | abundância diferencial entre dois grupos; tabela e volcano na própria página |
| `vegan` | R | PERMANOVA (adonis2) + PERMDISP (betadisper) |
| scikit-bio | Python | conferência independente da PERMANOVA (opção na aba Estatística) |

`GET /api/engines` mostra versões e a dica de instalação de cada um.

## Limites conhecidos

- UniFrac sem árvore enviada responde com o que fazer, em vez de calcular algo errado.
- Os fluxos externos (QIIME 2, DADA2, ALDEx2, ANCOM-BC2, vegan, cutadapt, VSEARCH) foram testados com executáveis simulados: a montagem dos comandos e a leitura dos resultados são testadas, mas a execução com as ferramentas reais depende da sua instalação. Os scripts R do ANCOM-BC2 e do DADA2 ainda não rodaram em R de verdade.
- A conexão com o QIIME 2 foi testada com um pacote `qiime2` e executáveis simulados (a descoberta, a configuração, os comandos e a conversão do resultado são reais); nenhum QIIME 2 de verdade foi executado. O DADA2 não tem API Python própria: ele roda pelo plugin do QIIME 2 ou pelo R (`rpy2` não é usado).
- As tabelas do MGnify são **perfis taxonômicos** do pipeline deles, não ASVs (não têm sequências).
- Leituras brutas (SRA/ENA) não são analisadas diretamente: processe com QIIME 2 ou DADA2 e ingira o resultado.
