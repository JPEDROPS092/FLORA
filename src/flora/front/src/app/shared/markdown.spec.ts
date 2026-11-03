
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
  it('escapes raw HTML', () => {
    expect(renderMarkdown('<script>alert(1)</script>')).not.toContain('<script>');
  });

  it('renders headings, emphasis and code', () => {
    const html = renderMarkdown('# T\n\nA **b** *c* `d`');
    expect(html).toContain('<h1>T</h1>');
    expect(html).toContain('<strong>b</strong>');
    expect(html).toContain('<em>c</em>');
    expect(html).toContain('<code>d</code>');
  });

  it('renders lists and tables', () => {
    expect(renderMarkdown('1. a\n2. b')).toContain('<ol><li>a</li><li>b</li></ol>');
    const table = renderMarkdown('| x | y |\n|---|---|\n| 1 | 2 |');
    expect(table).toContain('<th>x</th>');
    expect(table).toContain('<td>2</td>');
  });

  it('only links http(s) URLs', () => {
    expect(renderMarkdown('[a](javascript:alert(1))')).not.toContain('<a ');
    expect(renderMarkdown('[a](https://x.org)')).toContain('rel="noopener noreferrer"');
  });
});
