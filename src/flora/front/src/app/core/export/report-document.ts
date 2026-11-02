import { PlotFigure, ReportSection } from '../models/domain';

export interface ReportFileInput {
  title: string;
  sections: ReportSection[];
  parameters: { label: string; value: string }[];
  figures: Partial<Record<string, PlotFigure | undefined>>;
  mocked: boolean;
}

export function buildReportFiles(input: ReportFileInput): { html: string; pdfBase64: string } {
  const html = buildHtml(input);
  const lines = buildPlainLines(input);
  return { html, pdfBase64: bytesToBase64(buildPdf(input.title, lines)) };
}

function buildHtml(input: ReportFileInput): string {
  const included = input.sections.filter((section) => section.included);
  const figures = included
    .map((section) => {
      const figure = section.figure ? input.figures[section.figure] : undefined;
      return figure ? { id: section.id, figure } : null;
    })
    .filter((item): item is { id: string; figure: PlotFigure } => item !== null);

  const sections = included
    .map((section) => {
      const table = section.table
        ? `<table><thead><tr>${section.table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join('')}</tr></thead><tbody>${section.table.rows
            .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`)
            .join('')}</tbody></table>`
        : '';
      const plot = section.figure && input.figures[section.figure] ? `<div id="plot-${section.id}" class="plot"></div>` : '';
      return `<section><h2>${escapeHtml(section.title)}</h2><p>${escapeHtml(section.narrative)}</p>${plot}${table}</section>`;
    })
    .join('');

  const script = figures.length
    ? `<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script><script>
      const figures = ${JSON.stringify(Object.fromEntries(figures.map((item) => [item.id, item.figure])))};
      for (const [id, figure] of Object.entries(figures)) {
        const target = document.getElementById('plot-' + id);
        if (target && window.Plotly) {
          Plotly.newPlot(target, figure.data, Object.assign({ paper_bgcolor: '#fff', plot_bgcolor: '#fff', font: { family: 'Segoe UI, sans-serif', color: '#22332F' } }, figure.layout), { displaylogo: false, responsive: true });
        }
      }
    </script>`
    : '';

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(input.title)}</title>
  <style>
    body { margin: 0; background: #F8FAF9; color: #22332F; font: 15px/1.5 "Segoe UI", sans-serif; }
    main { max-width: 880px; margin: 0 auto; padding: 32px 20px 64px; }
    h1 { font-size: 1.6rem; font-weight: 650; letter-spacing: -0.02em; margin: 0 0 8px; }
    h2 { font-size: 1.05rem; margin: 0 0 8px; }
    .banner { color: #64736E; font-size: 0.82rem; letter-spacing: 0.04em; text-transform: uppercase; }
    section { background: #fff; border: 1px solid #DCE5E1; border-radius: 8px; padding: 16px 18px; margin-top: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #DCE5E1; }
    th { color: #64736E; font-weight: 600; }
    .plot { min-height: 360px; }
  </style>
</head>
<body>
  <main>
    <p class="banner">${input.mocked ? 'Dados mockados · ' : ''}FLORA Scientific Report</p>
    <h1>${escapeHtml(input.title)}</h1>
    ${sections}
  </main>
  ${script}
</body>
</html>`;
}

function buildPlainLines(input: ReportFileInput): string[] {
  const lines = [input.title, input.mocked ? 'Dados mockados' : 'Exportação da API', ''];
  for (const section of input.sections.filter((item) => item.included)) {
    lines.push(section.title, section.narrative, '');
    if (section.table) {
      lines.push(section.table.columns.join(' | '));
      for (const row of section.table.rows) {
        lines.push(row.join(' | '));
      }
      lines.push('');
    }
    if (section.figure) {
      lines.push(`Figura: ${section.figure} (ver HTML)`, '');
    }
  }
  if (input.parameters.length) {
    lines.push('Parâmetros');
    for (const parameter of input.parameters) {
      lines.push(`${parameter.label}: ${parameter.value}`);
    }
  }
  return lines;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const WIN: Record<string, string> = {
  á: '\\341',
  à: '\\340',
  â: '\\342',
  ã: '\\343',
  é: '\\351',
  ê: '\\352',
  í: '\\355',
  ó: '\\363',
  ô: '\\364',
  õ: '\\365',
  ú: '\\372',
  ç: '\\347',
  Á: '\\301',
  Â: '\\302',
  Ã: '\\303',
  É: '\\311',
  Í: '\\315',
  Ó: '\\323',
  Õ: '\\325',
  Ú: '\\332',
  Ç: '\\307',
  '–': '-',
  '—': '-',
  '’': "'"
};

function pdfText(value: string): string {
  let out = '';
  for (const char of value) {
    if (char === '\\' || char === '(' || char === ')') {
      out += `\\${char}`;
    } else if (WIN[char]) {
      out += WIN[char];
    } else if (char.charCodeAt(0) < 128) {
      out += char;
    } else {
      out += '?';
    }
  }
  return out;
}

function wrap(value: string, width = 92): string[] {
  const words = value.split(/\s+/);
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > width) {
      if (current) {
        lines.push(current);
      }
      current = word;
    } else {
      current = next;
    }
  }
  if (current) {
    lines.push(current);
  }
  return lines.length ? lines : [''];
}

function buildPdf(title: string, lines: string[]): Uint8Array {
  const wrapped = [title, ...lines.flatMap((line) => wrap(line))];
  const pages: string[][] = [];
  for (let index = 0; index < wrapped.length; index += 46) {
    pages.push(wrapped.slice(index, index + 46));
  }
  if (pages.length === 0) {
    pages.push(['FLORA']);
  }

  const objects: string[] = [];
  const pageIds: number[] = [];
  let nextId = 3;
  const fontId = 3 + pages.length * 2;
  for (const page of pages) {
    const contentId = nextId;
    const pageId = nextId + 1;
    nextId += 2;
    pageIds.push(pageId);
    const commands = ['BT', '/F1 11 Tf', '14 TL', '48 760 Td'];
    page.forEach((line, index) => {
      if (index === 0) {
        commands.push(`(${pdfText(line)}) Tj`);
      } else {
        commands.push('T*');
        commands.push(`(${pdfText(line)}) Tj`);
      }
    });
    commands.push('ET');
    const stream = commands.join('\n');
    objects[contentId] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
    objects[pageId] =
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${contentId} 0 R /Resources << /Font << /F1 ${fontId} 0 R >> >> >>`;
  }
  objects[1] = `<< /Type /Catalog /Pages 2 0 R >>`;
  objects[2] = `<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`;
  objects[fontId] = `<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>`;

  let body = '%PDF-1.4\n';
  const offsets = [0];
  const maxId = fontId;
  for (let id = 1; id <= maxId; id += 1) {
    offsets[id] = body.length;
    body += `${id} 0 obj\n${objects[id] ?? '<< >>'}\nendobj\n`;
  }
  const xref = body.length;
  body += `xref\n0 ${maxId + 1}\n`;
  body += '0000000000 65535 f \n';
  for (let id = 1; id <= maxId; id += 1) {
    body += `${String(offsets[id]).padStart(10, '0')} 00000 n \n`;
  }
  body += `trailer << /Size ${maxId + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return new TextEncoder().encode(body);
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}
