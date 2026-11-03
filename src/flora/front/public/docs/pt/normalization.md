# 2 · Normalização

Contagens de 16S são **composicionais**: a soma por amostra depende do sequenciamento, não da biologia.

- **Rarefação** — descarta amostras abaixo da profundidade e iguala as demais.
- **TSS** — divide cada contagem pelo total da amostra (abundância relativa).
- **CLR** — log-razão centrada; usa pseudocontagem 0,5, o que comprime zeros.
- **Prevalência mínima** — remove ASVs presentes em poucas amostras.

## Cuidados

- CLR em dados muito esparsos pode **inflar correlações**.
- Trocar a rarefação ou a transformação muda a matriz: **não compare** resultados de configurações diferentes sem registrar.

Os parâmetros escolhidos entram na proveniência dos experimentos e do relatório.
