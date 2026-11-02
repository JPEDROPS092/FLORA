# ADR 0001 — Design system do FLORA Studio: Angular 21 + PrimeNG 21

- **Status:** Aceito
- **Data:** 2026-11-02
- **Issue:** #3
- **Contexto:** auditoria da issue #2 (`docs/audit.md`)

---

## Contexto

O roadmap do FLORA Studio define uma plataforma científica web exclusivamente
Angular 21, com biblioteca de componentes produtiva e o mínimo de dependências
de estilização. A auditoria (#2) confirmou que o scaffolding existente em
`src/flora/front/` não contém código da aplicação (zero arquivos `.ts`) e foi
gerado por exportação do Google AI Studio, carregando decisões incompatíveis
com o projeto:

- `@angular/material` + Tailwind CSS 4 como stack de UI;
- `@google/genai` e artefatos de runtime do AI Studio (`metadata.json`,
  `.env.example` com `GEMINI_API_KEY`);
- `package.json` sem lockfile e scripts com sintasse shell não portátil.

A documentação (`docs/ui.md`, `src/flora/front/README.md`) descrevia uma SPA
completa que não existia — qualquer decisão de design system precisava, antes,
de uma decisão formal e de um scaffolding alinhado.

## Decisão

1. **Biblioteca de componentes: PrimeNG 21** (`primeng@^21`, compatível com
   Angular 21 e CDK 21), com PrimeIcons para ícones. Componentes principais
   esperados: Table (virtualização) para exploração tabular, Dialog/Drawer,
   Toast, Menu/Sidebar, Chart (com Plotly.js para as figuras científicas),
   FileUpload, Steps/Timeline para o pipeline.
2. **Estilização: CSS Variables + CSS utilitários próprios** — sem Tailwind e
   sem Material. O tema do FLORA (design tokens em `styles/tokens.css`,
   `styles/themes.css`, `styles/scientific.css`) é aplicado sobre as
   variáveis de design do PrimeNG (preset Aura, customizado).
3. **Sem SDK de IA no cliente** — `@google/genai` removido. Qualquer recurso
   de IA futuro passa por decisão e ADR próprios, e nunca com segredos no
   frontend.
4. **Estado, rotas e dados:** Angular Signals para estado local, HttpClient +
   RxJS para o remoto, componentes standalone, lazy loading, TypeScript
   estrito. Visualizações científicas com Plotly.js (paridade com as figuras
   Python do backend).
5. **Código-fonte do frontend passa a ser rastreado** no repositório
   (removida a regra do `.gitignore` que ignorava `src/flora/front/src/`).

## Alternativas consideradas

| Alternativa | Motivo da rejeição |
|-------------|--------------------|
| Manter Angular Material + Tailwind (scaffolding atual) | Diverge do roadmap (PrimeNG 21); herda artefatos do AI Studio; dois sistemas de estilo para manter sem ganho mensurável |
| PrimeVue / outro framework | Violaria a regra "nenhum frontend concorrente" e descartaria a stack Angular já fixada |
| Biblioteca de componentes própria | Custo de acessibilidade, manutenção e testes cross-browser incompatível com o cronograma de 12 sprints |
| Tailwind como camada de estilo | Roadmap fixa "CSS Variables + CSS Modules — menos dependências de estilização"; PrimeNG cobre o necessário |

## Consequências

- `package.json` realinhado: removidos `@angular/material`, `@google/genai`,
  `motion`, `tailwindcss`, `@tailwindcss/postcss`, `postcss`, `cross-env`;
  adicionados `primeng@^21` e `primeicons`.
- Removidos `metadata.json`, `.env.example` (artefatos do AI Studio) e
  `.postcssrc.json` (Tailwind).
- O build do frontend continua falhando **porque ainda não há código-fonte** —
  isso é esperado e será resolvido na issue #4 (AppShell), que criará
  `src/flora/front/src/` com o tema e o layout base.
- A documentação passa a descrever o estado real (scaffolding + decisão),
  eliminando as rotas/componentes "implementados" inexistentes.
- Licenças: PrimeNG e PrimeIcons são MIT, compatíveis com o projeto.

## Referências

- Auditoria: `docs/audit.md` (seções 5.3 e 7)
- Roadmap: decisões técnicas da Fase 1 (frontend Angular 21, PrimeNG 21)
- PrimeNG 21: peer dependencies `@angular/* ^21` verificadas no npm
