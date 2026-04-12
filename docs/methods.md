# Methods

Scientific background and references for every algorithm used in FLORA.

---

## 1. 16S rRNA Amplicon Sequencing

16S rRNA gene sequencing is the standard method for culture-independent microbial community profiling. The 16S gene contains nine hypervariable regions (V1-V9). FLORA targets V3-V4 and V4 regions, which provide adequate taxonomic resolution for most environmental studies.

**Primer pairs commonly used:**
- V4: 515F/806R (Earth Microbiome Project standard)
- V3-V4: 341F/806R

Reference: Clarridge (2004). Impact of 16S rRNA gene sequence analysis for identification of bacteria on clinical microbiology and infectious diseases. *Clinical Microbiology Reviews*, 17(4), 840-862. https://doi.org/10.1128/CMR.17.4.840-862.2004

---

## 2. DADA2 Denoising

DADA2 (Divisive Amplicon Denoising Algorithm 2) models the amplicon sequencing errors and infers exact Amplicon Sequence Variants (ASVs) rather than OTUs. ASVs represent single-nucleotide resolution without the clustering artifacts introduced by 97% OTU thresholds.

**Steps performed:**
1. Quality filtering and trimming (cutoffs based on quality score distributions)
2. Error model learning from the data
3. Sample inference (dereplication + denoising)
4. Paired-end merging
5. Chimera removal

FLORA calls DADA2 through the QIIME 2 SDK (`qiime dada2 denoise-paired`).

Reference: Callahan et al. (2016). DADA2: High-resolution sample inference from Illumina amplicon data. *Nature Methods*, 13, 581-583. https://doi.org/10.1038/nmeth.3869

---

## 3. Taxonomic Classification

### Naive Bayes Classifier (QIIME 2 + SILVA)

FLORA uses a pre-trained Naive Bayes classifier against the SILVA 138 reference database. The classifier is trained on exact k-mer frequencies from the amplicon region.

Reference: Bokulich et al. (2018). Optimizing taxonomic classification of marker-gene amplicon sequences with QIIME 2's q2-feature-classifier. *Microbiome*, 6, 90. https://doi.org/10.1186/s40168-018-0470-z

### SILVA 138 Reference Database

SILVA provides curated, quality-controlled ribosomal RNA gene sequences and taxonomies.

Reference: Quast et al. (2013). The SILVA ribosomal RNA gene database project: improved data processing and web-based tools. *Nucleic Acids Research*, 41(D1), D590-D596. https://doi.org/10.1093/nar/gks1219

---

## 4. Phylogenetic Inference

### MAFFT Multiple Sequence Alignment

FLORA aligns representative ASV sequences using MAFFT (Multiple Alignment using Fast Fourier Transform), an iterative refinement method.

Reference: Katoh & Standley (2013). MAFFT multiple sequence alignment software version 7: improvements in performance and usability. *Molecular Biology and Evolution*, 30(4), 772-780. https://doi.org/10.1093/molbev/mst010

### FastTree

Phylogenetic tree inference uses FastTree, a maximum-likelihood method optimized for large datasets.

Reference: Price et al. (2010). FastTree 2 — Approximately Maximum-Likelihood Trees for Large Alignments. *PLOS ONE*, 5(3), e9490. https://doi.org/10.1371/journal.pone.0009490

---

## 5. Alpha Diversity Metrics

Alpha diversity measures the richness and evenness of species within a single sample.

### Shannon Index (H')

Accounts for both richness and evenness.

H' = -sum(p_i * log(p_i))

where p_i is the relative abundance of species i.

Reference: Shannon (1948). A mathematical theory of communication. *Bell System Technical Journal*, 27(3), 379-423.

### Chao1 Richness Estimator

Non-parametric estimator of species richness, useful for samples with rare species.

Chao1 = S_obs + (n1^2) / (2 * n2)

where n1 is the number of singletons and n2 is the number of doubletons.

Reference: Chao (1984). Nonparametric estimation of the number of classes in a population. *Scandinavian Journal of Statistics*, 11(4), 265-270.

### Observed Features (Species Richness)

Simple count of the number of non-zero ASVs per sample.

### Faith's Phylogenetic Diversity (PD)

Measures the total branch length of a phylogenetic tree spanning all taxa in a sample. Accounts for evolutionary divergence rather than just counts.

Reference: Faith (1992). Conservation evaluation and phylogenetic diversity. *Biological Conservation*, 61(1), 1-10. https://doi.org/10.1016/0006-3207(92)91201-3

### Simpson Index (1 - D)

Probability that two randomly selected individuals belong to different species.

D = sum(n_i * (n_i - 1)) / (N * (N - 1))

Simpson diversity = 1 - D

Reference: Simpson (1949). Measurement of diversity. *Nature*, 163, 688. https://doi.org/10.1038/163688a0

---

## 6. Beta Diversity Metrics

Beta diversity measures dissimilarity between communities.

### Bray-Curtis Dissimilarity

Quantifies the compositional dissimilarity between samples based on abundance counts.

BC(i,j) = 1 - (2 * sum(min(x_ik, x_jk))) / (sum(x_ik) + sum(x_jk))

Ranges from 0 (identical communities) to 1 (no shared species).

Reference: Bray & Curtis (1957). An ordination of the upland forest communities of southern Wisconsin. *Ecological Monographs*, 27(4), 325-349. https://doi.org/10.2307/1942268

### UniFrac Distance

Phylogeny-aware beta diversity measure. Weighted UniFrac accounts for relative abundances; Unweighted UniFrac treats all taxa equally.

UniFrac = (sum of branch lengths unique to one sample) / (total branch length)

Reference: Lozupone & Knight (2005). UniFrac: a new phylogenetic method for comparing microbial communities. *Applied and Environmental Microbiology*, 71(12), 8228-8235. https://doi.org/10.1128/AEM.71.12.8228-8235.2005

---

## 7. Compositional Data Normalization

Microbiome count data are compositional: only relative abundances are observed, not absolute counts. Standard normalization methods that ignore this can introduce spurious correlations.

### Centered Log-Ratio (CLR) Transformation

The CLR transform maps compositions into unconstrained Euclidean space.

CLR(x_i) = log(x_i / g(x))

where g(x) is the geometric mean of all components.

A pseudo-count (typically 0.5 or 1) is added before log transformation to handle zeros.

CLR is the recommended normalization in FLORA for all ML tasks.

Reference: Aitchison (1982). The statistical analysis of compositional data. *Journal of the Royal Statistical Society: Series B*, 44(2), 139-160. https://doi.org/10.1111/j.2517-6161.1982.tb01195.x

Implementation guidance: Gloor et al. (2017). Microbiome Datasets Are Compositional: And This Is Not Optional. *Frontiers in Microbiology*, 8, 2224. https://doi.org/10.3389/fmicb.2017.02224

### Total Sum Scaling (TSS)

Divides each count by the sample total. Converts absolute counts to relative abundances. Simple but ignores compositionality constraints.

### Rarefaction

Randomly subsamples each sample to a fixed depth (minimum observed depth by default) to equalize sequencing effort. Discards samples below the threshold.

Reference: Weiss et al. (2017). Normalization and microbial differential abundance strategies depend upon data characteristics. *Microbiome*, 5, 27. https://doi.org/10.1186/s40168-017-0237-y

---

## 8. Dimensionality Reduction

### Principal Coordinates Analysis (PCoA)

PCoA (also called metric Multidimensional Scaling) projects samples from a distance matrix into a low-dimensional space where Euclidean distances approximate the original pairwise distances.

Applied on Bray-Curtis or UniFrac distance matrices for ordination of samples.

Reference: Gower (1966). Some distance properties of latent root and vector methods used in multivariate analysis. *Biometrika*, 53(3-4), 325-338. https://doi.org/10.1093/biomet/53.3-4.325

### UMAP

Uniform Manifold Approximation and Projection. Non-linear dimensionality reduction that preserves both local and global structure.

Reference: McInnes et al. (2018). UMAP: Uniform Manifold Approximation and Projection for Dimension Reduction. *arXiv*, 1802.03426. https://arxiv.org/abs/1802.03426

---

## 9. Machine Learning Models

### Random Forest

Ensemble of decision trees trained on bootstrap samples with random feature selection at each split. Effective for high-dimensional, sparse microbiome data.

Reference: Breiman (2001). Random forests. *Machine Learning*, 45, 5-32. https://doi.org/10.1023/A:1010933404324

### Support Vector Machine (SVM)

Finds the maximum-margin hyperplane in a high-dimensional feature space. Effective in high-p, low-n settings typical of microbiome studies.

Reference: Cortes & Vapnik (1995). Support-vector networks. *Machine Learning*, 20, 273-297. https://doi.org/10.1007/BF00994018

### XGBoost

Gradient boosted trees with regularization. State-of-the-art performance on tabular data with built-in handling of feature importance.

Reference: Chen & Guestrin (2016). XGBoost: A Scalable Tree Boosting System. *Proceedings of KDD 2016*, 785-794. https://doi.org/10.1145/2939672.2939785

### HDBSCAN

Hierarchical Density-Based Spatial Clustering of Applications with Noise. Identifies clusters of arbitrary shape without requiring the number of clusters as input.

Reference: Campello et al. (2013). Density-Based Clustering Based on Hierarchical Density Estimates. *Proceedings of PAKDD 2013*, 160-172. https://doi.org/10.1007/978-3-642-37456-2_14

---

## 10. Model Interpretability

### SHAP (SHapley Additive exPlanations)

SHAP assigns each feature a contribution value for a specific prediction based on game-theoretic Shapley values. Provides both global feature importance and local per-sample explanations.

Reference: Lundberg & Lee (2017). A Unified Approach to Interpreting Model Predictions. *Advances in Neural Information Processing Systems*, 30. https://proceedings.neurips.cc/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html

---

## 11. Hyperparameter Optimization

### Optuna

Bayesian-like hyperparameter optimization framework using Tree-structured Parzen Estimators (TPE). More sample-efficient than grid or random search.

Reference: Akiba et al. (2019). Optuna: A Next-generation Hyperparameter Optimization Framework. *Proceedings of KDD 2019*, 2623-2631. https://doi.org/10.1145/3292500.3330701

---

## 12. Analytical Database

### DuckDB

In-process analytical SQL database with native Parquet support, columnar storage, and OLAP query optimization. Used as the central query engine to avoid loading large feature matrices into RAM.

Reference: Raasveldt & Muehleisen (2019). DuckDB: an embeddable analytical database. *Proceedings of SIGMOD 2019*, 1981-1984. https://doi.org/10.1145/3299869.3320212

---

## 13. QIIME 2 Framework

QIIME 2 (Quantitative Insights Into Microbial Ecology 2) is the primary framework wrapping bioinformatics tools for amplicon analysis. FLORA uses the QIIME 2 Python SDK to call DADA2, classifiers, and diversity metrics programmatically.

Reference: Bolyen et al. (2019). Reproducible, interactive, scalable and extensible microbiome data science using QIIME 2. *Nature Biotechnology*, 37, 852-857. https://doi.org/10.1038/s41587-019-0209-9

---

## 14. Evaluation Metrics

### Classification

- **Accuracy**: fraction of correctly classified samples.
- **F1-macro**: unweighted mean of per-class F1 scores. Use when class imbalance exists.
- **ROC-AUC**: area under the Receiver Operating Characteristic curve. Measures discriminative ability independently of threshold.

Reference: Powers (2011). Evaluation: From Precision, Recall and F-measure to ROC, Informedness, Markedness and Correlation. *Journal of Machine Learning Technologies*, 2(1), 37-63.

### Regression

- **R² (coefficient of determination)**: proportion of variance in the target explained by the model.
- **MAE (mean absolute error)**: average absolute deviation between predicted and true values.
- **RMSE (root mean squared error)**: square root of mean squared errors, penalizes large deviations.

### Clustering

- **Silhouette Score**: measures how similar a sample is to its own cluster versus other clusters. Ranges from -1 (wrong cluster) to 1 (well-separated).

Reference: Rousseeuw (1987). Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53-65. https://doi.org/10.1016/0377-0427(87)90125-7
