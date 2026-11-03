# 4 · Modelagem

Treina **Random Forest** ou **XGBoost** para prever uma coluna dos metadados (ex.: `biome`).

## Divisão treino/teste

Você informa dois filtros SQL, por exemplo `site != 'A'` e `site = 'A'`. Cada filtro deve ser **um único predicado** (sem `;` nem comentários). Isso permite validar em um sítio não visto.

## Resultados

Acurácia, F1 macro, ROC AUC, validação cruzada, matriz de confusão e curvas ROC. Cada experimento é **gravado no projeto** com seed e versões, e a mesma seed reproduz o resultado.

## Ressalvas

- Com conjunto de teste pequeno, a acurácia é **instável**.
- A importância vem da **impureza do modelo**, não de SHAP: descreve o modelo, não um efeito biológico.
