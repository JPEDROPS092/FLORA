# 4 · Modelling

Trains **Random Forest** or **XGBoost** to predict a metadata column (e.g. `biome`).

## Train/test split

You provide two SQL filters, for example `site != 'A'` and `site = 'A'`. Each filter must be **a single predicate** (no `;` or comments). This lets you validate on an unseen site.

## Results

Accuracy, macro F1, ROC AUC, cross-validation, confusion matrix and ROC curves. Every experiment is **saved in the project** with its seed and versions, and the same seed reproduces the result.

## Caveats

- With a small test set, accuracy is **unstable**.
- Importance comes from **model impurity**, not SHAP: it describes the model, not a biological effect.
