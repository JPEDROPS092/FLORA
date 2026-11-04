"""Frontend shell for the FLORA web interface."""

from __future__ import annotations


def _styles() -> str:
    return """
<style>
  *, *::before, *::after { box-sizing: border-box; }
  :root {
    --bg: #f4efe5;
    --panel: rgba(255, 253, 248, 0.94);
    --text: #1f2937;
    --muted: #5b6472;
    --border: rgba(31, 41, 55, 0.12);
    --teal: #0f766e;
    --forest: #285943;
    --rust: #dc6b2f;
    --gold: #c7932d;
    --radius: 20px;
    --shadow: 0 20px 60px rgba(31, 41, 55, 0.10);
  }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
    color: var(--text);
    background:
      radial-gradient(circle at top left, rgba(199,147,45,0.22), transparent 26%),
      radial-gradient(circle at right 20%, rgba(15,118,110,0.18), transparent 24%),
      linear-gradient(160deg, #f6f0e6 0%, #efe5d4 40%, #f9f5ee 100%);
  }
  .shell { display: grid; grid-template-columns: 280px minmax(0, 1fr); min-height: 100vh; }
  .sidebar {
    position: sticky;
    top: 0;
    height: 100vh;
    padding: 28px 22px;
    background: rgba(23, 33, 31, 0.90);
    color: #f8f4ec;
    border-right: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(18px);
  }
  .brand {
    padding: 18px 18px 22px;
    border-radius: 22px;
    background: linear-gradient(145deg, rgba(15,118,110,0.36), rgba(40,89,67,0.20));
    border: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 22px;
  }
  .brand h1 {
    margin: 0;
    font-family: "Space Grotesk", "IBM Plex Sans", sans-serif;
    letter-spacing: -0.04em;
    font-size: 2rem;
  }
  .brand p {
    margin: 8px 0 0;
    color: rgba(248,244,236,0.76);
    line-height: 1.45;
    font-size: 0.92rem;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 999px;
    margin-top: 16px;
    background: rgba(255,255,255,0.08);
    font-size: 0.9rem;
  }
  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #9ca3af;
    box-shadow: 0 0 0 5px rgba(156,163,175,0.12);
  }
  .status-dot.live { background: #4ade80; box-shadow: 0 0 0 5px rgba(74,222,128,0.16); }
  .status-dot.off { background: #fb7185; box-shadow: 0 0 0 5px rgba(251,113,133,0.16); }
  .nav { display: grid; gap: 8px; margin-top: 18px; }
  .nav a {
    color: rgba(248,244,236,0.82);
    text-decoration: none;
    padding: 12px 14px;
    border-radius: 14px;
    transition: 160ms ease;
    border: 1px solid transparent;
  }
  .nav a:hover, .nav a.active {
    color: #fff;
    background: rgba(255,255,255,0.08);
    border-color: rgba(255,255,255,0.08);
    transform: translateX(2px);
  }
  .sidebar-footer {
    position: absolute;
    left: 22px;
    right: 22px;
    bottom: 24px;
    padding: 14px 16px;
    border-radius: 18px;
    background: rgba(255,255,255,0.06);
    font-size: 0.88rem;
    color: rgba(248,244,236,0.72);
    line-height: 1.5;
  }
  .content { padding: 28px; }
  .section { margin-bottom: 22px; }
  .hero { display: grid; grid-template-columns: 1.35fr 0.95fr; gap: 18px; margin-bottom: 18px; }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    backdrop-filter: blur(14px);
  }
  .hero-main {
    padding: 30px;
    position: relative;
    overflow: hidden;
  }
  .hero-main::after {
    content: "";
    position: absolute;
    width: 280px;
    height: 280px;
    right: -60px;
    top: -90px;
    background: radial-gradient(circle, rgba(15,118,110,0.16), transparent 70%);
    pointer-events: none;
  }
  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.18em;
    color: var(--rust);
    font-size: 0.75rem;
    font-weight: 700;
  }
  .hero h2 {
    margin: 10px 0 12px;
    font-family: "Space Grotesk", "IBM Plex Sans", sans-serif;
    font-size: clamp(2rem, 3vw, 3.35rem);
    line-height: 0.96;
    letter-spacing: -0.05em;
  }
  .hero p { color: var(--muted); line-height: 1.65; max-width: 62ch; }
  .tag-row, .quick-actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-radius: 999px;
    background: rgba(15,118,110,0.09);
    color: var(--forest);
    font-weight: 600;
    font-size: 0.92rem;
  }
  .hero-side { padding: 24px; display: grid; gap: 14px; }
  .checklist { display: grid; gap: 10px; }
  .check-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 16px;
    background: rgba(31,41,55,0.04);
  }
  .check-mark {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    background: rgba(156,163,175,0.16);
    color: var(--muted);
    flex: none;
  }
  .check-item.done .check-mark { background: rgba(15,118,110,0.12); color: var(--teal); }
  .metrics-grid, .feature-grid, .plot-grid, .control-grid { display: grid; gap: 16px; }
  .metrics-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); margin-bottom: 18px; }
  .metric {
    padding: 18px;
    border-radius: 18px;
    background: var(--panel);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
  }
  .metric .label {
    color: var(--muted);
    font-size: 0.84rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .metric .value {
    font-size: 1.7rem;
    font-weight: 700;
    margin-top: 8px;
    letter-spacing: -0.04em;
  }
  .section-title {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 14px;
    margin-bottom: 14px;
  }
  .section-title h3 {
    margin: 0;
    font-size: 1.35rem;
    font-family: "Space Grotesk", "IBM Plex Sans", sans-serif;
    letter-spacing: -0.04em;
  }
  .section-title p { margin: 4px 0 0; color: var(--muted); }
  .feature-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 18px; }
  .feature-card, .control-card, .plot-card { padding: 22px; }
  .feature-card strong { display: block; font-size: 1.06rem; margin-bottom: 10px; }
  .feature-card p { margin: 0; color: var(--muted); line-height: 1.65; }
  .control-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-bottom: 18px; }
  .tab-shell {
    padding: 10px;
    border-radius: var(--radius);
    background: rgba(255,255,255,0.34);
    border: 1px solid rgba(31,41,55,0.08);
  }
  .tab-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
  .tab-btn {
    border: 0;
    cursor: pointer;
    border-radius: 999px;
    padding: 12px 18px;
    font: inherit;
    font-weight: 700;
    transition: 160ms ease;
    background: rgba(31,41,55,0.06);
    color: var(--muted);
  }
  .tab-btn.active {
    background: linear-gradient(135deg, var(--forest), var(--teal));
    color: #fff;
  }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .control-card h4 { margin: 0 0 14px; font-size: 1.06rem; }
  .form-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
  .form-row.one { grid-template-columns: 1fr; }
  label {
    display: block;
    margin-bottom: 6px;
    font-size: 0.86rem;
    color: var(--muted);
    font-weight: 600;
  }
  input, select, textarea {
    width: 100%;
    border-radius: 14px;
    border: 1px solid rgba(31,41,55,0.14);
    background: rgba(255,255,255,0.88);
    padding: 12px 14px;
    font: inherit;
    color: var(--text);
    transition: 160ms ease;
  }
  input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: rgba(15,118,110,0.45);
    box-shadow: 0 0 0 4px rgba(15,118,110,0.10);
  }
  textarea { min-height: 110px; resize: vertical; }
  button {
    border: 0;
    cursor: pointer;
    border-radius: 999px;
    padding: 12px 18px;
    font: inherit;
    font-weight: 700;
    transition: 160ms ease;
  }
  .btn-primary { background: linear-gradient(135deg, var(--teal), #169487); color: #fff; }
  .btn-secondary { background: rgba(31,41,55,0.08); color: var(--text); }
  .btn-accent { background: linear-gradient(135deg, #d97706, var(--rust)); color: #fff; }
  button:hover { transform: translateY(-1px); filter: saturate(1.06); }
  button:disabled { opacity: 0.6; cursor: wait; transform: none; }
  .plot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .plot-head { display: flex; justify-content: space-between; align-items: start; gap: 14px; margin-bottom: 14px; }
  .plot-head h4 { margin: 0; font-size: 1.05rem; }
  .plot-head p { margin: 6px 0 0; color: var(--muted); font-size: 0.92rem; line-height: 1.55; }
  .plot-area {
    min-height: 440px;
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(31,41,55,0.08);
    background: rgba(255,255,255,0.64);
  }
  .panel-output { margin-top: 12px; }
  .notice { border-radius: 16px; padding: 14px 16px; line-height: 1.55; border: 1px solid transparent; }
  .notice.ok { background: rgba(15,118,110,0.10); border-color: rgba(15,118,110,0.16); color: #115e59; }
  .notice.err { background: rgba(180,35,24,0.08); border-color: rgba(180,35,24,0.12); color: #8c2d1f; }
  .notice.info { background: rgba(199,147,45,0.14); border-color: rgba(199,147,45,0.18); color: #7c5b12; }
  .mono-box {
    padding: 16px;
    border-radius: 16px;
    border: 1px solid var(--border);
    background: #1e293b;
    color: #e2e8f0;
    font-family: "IBM Plex Mono", monospace;
    white-space: pre-wrap;
    overflow: auto;
  }
  .log-box { max-height: 220px; }
  .spinner {
    width: 16px;
    height: 16px;
    display: inline-block;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.45);
    border-top-color: #fff;
    animation: spin .8s linear infinite;
    vertical-align: -3px;
    margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 1180px) {
    .hero, .control-grid, .plot-grid, .feature-grid, .metrics-grid { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 980px) {
    .shell { grid-template-columns: 1fr; }
    .sidebar { position: relative; height: auto; }
    .sidebar-footer { position: static; margin-top: 20px; }
    .hero, .control-grid, .plot-grid, .feature-grid, .metrics-grid, .form-row { grid-template-columns: 1fr; }
    .content { padding: 18px; }
  }
</style>
"""


def _hero() -> str:
    return """
<section class="hero">
  <div class="hero-main card" id="overview">
    <div class="eyebrow">Sequenciamento • Microbioma • Publicação</div>
    <h2>FLORA Data Viz Studio</h2>
    <p>
      Interface moderna para análise de dados de sequenciamento cobrindo os três pilares exigidos
      em microbioma: <strong>diversidade</strong>, <strong>composição</strong> e <strong>estrutura</strong>.
      O foco aqui é transformar a pipeline em uma ferramenta visual completa, navegável e pronta para exploração.
    </p>
    <div class="tag-row">
      <span class="tag">Shannon / Chao1</span>
      <span class="tag">Bray-Curtis / PCoA</span>
      <span class="tag">Barplot / Heatmap</span>
      <span class="tag">Krona / Tree / Network</span>
    </div>
    <div class="quick-actions">
      <button class="btn-primary" onclick="runPublicationSuite(this)">Executar suíte recomendada</button>
      <button class="btn-secondary" onclick="refreshStatus()">Atualizar status</button>
      <button class="btn-accent" onclick="refreshLogs()">Ver logs</button>
    </div>
  </div>
  <aside class="hero-side card">
    <div class="section-title">
      <div>
        <h3>Checklist para publicação</h3>
        <p>O frontend acompanha os gráficos essenciais do fluxo padrão de microbioma.</p>
      </div>
    </div>
    <div class="checklist" id="publication-checklist"></div>
  </aside>
</section>
"""


def _metrics() -> str:
    return """
<section class="section">
  <div class="metrics-grid" id="metrics-grid"></div>
</section>
"""


def _guides() -> str:
    return """
<section class="section" id="analysis">
  <div class="section-title">
    <div>
      <h3>Núcleo analítico</h3>
      <p>Os painéis abaixo refletem a estrutura recomendada para estudos de microbioma e metagenômica.</p>
    </div>
  </div>
  <div class="feature-grid">
    <article class="feature-card card">
      <strong>Diversidade</strong>
      <p>Alpha diversity com Shannon e Chao1 resume riqueza e uniformidade local. Beta diversity com Bray-Curtis mostra separação global entre amostras e grupos ecológicos.</p>
    </article>
    <article class="feature-card card">
      <strong>Composição taxonômica</strong>
      <p>Barplots, heatmaps e Krona traduzem abundância relativa para interpretação biológica direta, destacando quais táxons sustentam diferenças entre ambientes ou condições.</p>
    </article>
    <article class="feature-card card">
      <strong>Estrutura e relação</strong>
      <p>PCoA expõe a geometria da comunidade, redes mostram co-abundância entre táxons e a árvore taxonômica ajuda a ler a hierarquia do perfil observado.</p>
    </article>
  </div>
</section>
"""


def _workspace() -> str:
    return """
<section class="section" id="workspace">
  <div class="section-title">
    <div>
      <h3>Workspace operacional</h3>
      <p>Abas separadas para ingestão, execução analítica e inspeção da matriz de features.</p>
    </div>
  </div>
  <div class="card tab-shell">
    <div class="tab-bar">
      <button class="tab-btn active" data-tab-group="workspace" data-tab-target="workspace-ingest">Ingestão</button>
      <button class="tab-btn" data-tab-group="workspace" data-tab-target="workspace-analysis">Execução</button>
      <button class="tab-btn" data-tab-group="workspace" data-tab-target="workspace-matrix">Matriz e filtros</button>
    </div>
    <div id="workspace-ingest" class="tab-panel active">
      <div class="control-grid">
        <div class="control-card card">
          <h4>Carregamento de tabelas</h4>
          <div class="form-row one">
            <div>
              <label>Metadata path</label>
              <input id="meta-path" type="text" placeholder="data/raw/metadata.tsv">
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>Sample ID column</label>
              <input id="meta-sample-col" type="text" value="sample_id">
            </div>
            <div>
              <label>ASV table path</label>
              <input id="asv-path" type="text" placeholder="data/raw/asv_table.tsv">
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>ASV format</label>
              <select id="asv-wide">
                <option value="true">Wide: samples x features</option>
                <option value="false">Long: sample_id / feature_id / abundance</option>
              </select>
            </div>
            <div>
              <label>Taxonomy path</label>
              <input id="tax-path" type="text" placeholder="data/raw/taxonomy.tsv">
            </div>
          </div>
          <div class="quick-actions">
            <button class="btn-primary" onclick="ingestAll(this)">Carregar dataset completo</button>
            <button class="btn-secondary" onclick="ingestMetadata(this)">Só metadata</button>
            <button class="btn-secondary" onclick="ingestASV(this)">Só ASV</button>
            <button class="btn-secondary" onclick="ingestTaxonomy(this)">Só taxonomy</button>
          </div>
          <div class="panel-output" id="ingest-output"></div>
        </div>
        <div class="control-card card">
          <h4>Parâmetros globais</h4>
          <div class="form-row">
            <div>
              <label>Group by</label>
              <input id="global-group" type="text" value="biome" placeholder="biome">
            </div>
            <div>
              <label>Normalization</label>
              <select id="global-normalize">
                <option value="tss">TSS</option>
                <option value="clr">CLR</option>
                <option value="none">Raw</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>Sampling depth</label>
              <input id="div-depth" type="number" value="1000" min="100">
            </div>
            <div>
              <label>Min prevalence</label>
              <input id="matrix-prev" type="number" value="0.05" min="0" max="1" step="0.01">
            </div>
          </div>
          <div class="quick-actions">
            <button class="btn-primary" onclick="refreshStatus()">Sincronizar status</button>
            <button class="btn-secondary" onclick="refreshLogs()">Atualizar logs</button>
          </div>
          <div class="panel-output" id="workspace-output"></div>
        </div>
      </div>
    </div>
    <div id="workspace-analysis" class="tab-panel">
      <div class="control-grid">
        <div class="control-card card">
          <h4>Execução rápida</h4>
          <div class="form-row">
            <div>
              <label>Synthetic output dir</label>
              <input id="syn-outdir" type="text" value="results/raw/synthetic">
            </div>
            <div>
              <label>Samples</label>
              <input id="syn-samples" type="number" value="80" min="12">
            </div>
          </div>
          <div class="form-row">
            <div>
              <label>Features</label>
              <input id="syn-features" type="number" value="200" min="20">
            </div>
            <div>
              <label>Seed</label>
              <input id="syn-seed" type="number" value="42" min="1">
            </div>
          </div>
          <div class="quick-actions">
            <button class="btn-accent" onclick="downloadSynthetic(this)">Gerar dataset sintético</button>
            <button class="btn-primary" onclick="computeDiversity(this)">Calcular diversidade</button>
            <button class="btn-secondary" onclick="runPublicationSuite(this)">Rodar suíte recomendada</button>
          </div>
          <div class="panel-output" id="analysis-output"></div>
        </div>
        <div class="control-card card">
          <h4>Fluxo recomendado</h4>
          <div class="feature-grid" style="grid-template-columns:1fr;">
            <article class="feature-card card">
              <strong>1. Ingestão</strong>
              <p>Carregue metadata, ASV e taxonomy ou use um dataset baixado na central logo abaixo.</p>
            </article>
            <article class="feature-card card">
              <strong>2. Diversidade e estrutura</strong>
              <p>Calcule diversidade alfa, carregue PCoA, beta heatmap e verifique separação ecológica.</p>
            </article>
            <article class="feature-card card">
              <strong>3. Composição e relação</strong>
              <p>Explore barplots, heatmaps, Krona, árvore e rede para fechar a interpretação biológica.</p>
            </article>
          </div>
        </div>
      </div>
    </div>
    <div id="workspace-matrix" class="tab-panel">
      <div class="control-grid">
        <div class="control-card card">
          <h4>Feature matrix</h4>
          <div class="form-row">
            <div>
              <label>Normalization</label>
              <select id="matrix-normalize">
                <option value="tss">TSS</option>
                <option value="clr">CLR</option>
                <option value="none">Raw</option>
              </select>
            </div>
            <div>
              <label>Min prevalence</label>
              <input id="matrix-prev-alt" type="number" value="0.05" min="0" max="1" step="0.01">
            </div>
          </div>
          <div class="quick-actions">
            <button class="btn-primary" onclick="previewMatrix(this)">Gerar preview da matriz</button>
          </div>
          <div class="panel-output" id="matrix-output"></div>
        </div>
        <div class="control-card card">
          <h4>Configuração para gráficos</h4>
          <div class="form-row">
            <div>
              <label>Color / group field</label>
              <input id="global-group-alt" type="text" value="biome" placeholder="biome">
            </div>
            <div>
              <label>PCoA normalization</label>
              <select id="global-normalize-alt">
                <option value="tss">TSS</option>
                <option value="clr">CLR</option>
                <option value="none">Raw</option>
              </select>
            </div>
          </div>
          <div class="quick-actions">
            <button class="btn-secondary" onclick="syncGlobalControls()">Aplicar aos gráficos</button>
          </div>
          <div class="panel-output" id="matrix-config-output"></div>
        </div>
      </div>
    </div>
  </div>
</section>
"""


def _downloads() -> str:
    return """
<section class="section" id="downloads">
  <div class="section-title">
    <div>
      <h3>Dataset Center</h3>
      <p>Baixe datasets públicos e sintéticos sem sair da ferramenta.</p>
    </div>
  </div>
  <div class="card tab-shell">
    <div class="tab-bar">
      <button class="tab-btn active" data-tab-group="downloads" data-tab-target="download-synthetic">Synthetic</button>
      <button class="tab-btn" data-tab-group="downloads" data-tab-target="download-emp">EMP</button>
      <button class="tab-btn" data-tab-group="downloads" data-tab-target="download-mgnify">MGnify</button>
      <button class="tab-btn" data-tab-group="downloads" data-tab-target="download-sra">NCBI SRA</button>
    </div>
    <div id="download-synthetic" class="tab-panel active">
      <div class="control-card card">
        <h4>Dataset sintético local</h4>
        <p style="color:var(--muted); margin:0 0 14px;">Ideal para validar a interface e a pipeline inteira sem depender de rede.</p>
        <div class="quick-actions">
          <button class="btn-accent" onclick="downloadSynthetic(this)">Gerar e preencher paths</button>
        </div>
        <div class="panel-output" id="download-synthetic-output"></div>
      </div>
    </div>
    <div id="download-emp" class="tab-panel">
      <div class="control-card card">
        <h4>Earth Microbiome Project</h4>
        <div class="form-row">
          <div>
            <label>Output dir</label>
            <input id="emp-outdir" type="text" value="results/raw/emp">
          </div>
          <div>
            <label>Max samples</label>
            <input id="emp-maxsamples" type="number" value="200" min="10">
          </div>
        </div>
        <div class="form-row one">
          <div>
            <label>Biome filter</label>
            <input id="emp-biome" type="text" placeholder="forest, soil, marine">
          </div>
        </div>
        <div class="quick-actions">
          <button class="btn-primary" onclick="downloadEMP(this)">Baixar EMP</button>
        </div>
        <div class="panel-output" id="download-emp-output"></div>
      </div>
    </div>
    <div id="download-mgnify" class="tab-panel">
      <div class="control-card card">
        <h4>MGnify</h4>
        <div class="form-row">
          <div>
            <label>Study accession</label>
            <input id="mg-study" type="text" placeholder="MGYS00005779">
          </div>
          <div>
            <label>Max samples</label>
            <input id="mg-maxsamples" type="number" value="20" min="1">
          </div>
        </div>
        <div class="form-row">
          <div>
            <label>Biome filter</label>
            <input id="mg-biome" type="text" value="root:Environmental:Terrestrial:Forest">
          </div>
          <div>
            <label>Output dir</label>
            <input id="mg-outdir" type="text" value="results/raw/mgnify">
          </div>
        </div>
        <div class="quick-actions">
          <button class="btn-primary" onclick="downloadMGnify(this)">Baixar MGnify</button>
        </div>
        <div class="panel-output" id="download-mgnify-output"></div>
      </div>
    </div>
    <div id="download-sra" class="tab-panel">
      <div class="control-card card">
        <h4>NCBI SRA</h4>
        <div class="form-row">
          <div>
            <label>Output dir</label>
            <input id="sra-outdir" type="text" value="results/raw/sra">
          </div>
          <div>
            <label>Jobs</label>
            <input id="sra-jobs" type="number" value="4" min="1">
          </div>
        </div>
        <div class="form-row one">
          <div>
            <label>Accessions</label>
            <textarea id="sra-accessions" placeholder="SRR12345678&#10;SRR12345679"></textarea>
          </div>
        </div>
        <div class="quick-actions">
          <button class="btn-primary" onclick="downloadSRA(this)">Baixar SRA</button>
        </div>
        <div class="panel-output" id="download-sra-output"></div>
      </div>
    </div>
  </div>
</section>
"""


def _visuals() -> str:
    return """
<section class="section" id="visuals">
  <div class="section-title">
    <div>
      <h3>Visualization Studio</h3>
      <p>Gráficos centrais para sequenciamento, microbioma e exploração taxonômica avançada.</p>
    </div>
    <div class="quick-actions">
      <button class="btn-primary" onclick="loadCoreVisuals(this)">Carregar gráficos principais</button>
      <button class="btn-secondary" onclick="loadAdvancedVisuals(this)">Carregar gráficos avançados</button>
    </div>
  </div>
  <div class="plot-grid">
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>PCoA / estrutura</h4>
          <p>Ordenação global das amostras com Bray-Curtis para enxergar separação composicional.</p>
        </div>
        <button class="btn-secondary" onclick="loadPCoA(this)">Atualizar</button>
      </div>
      <div id="plot-pcoa" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Alpha diversity</h4>
          <p>Distribuição de Shannon ou Chao1 por grupo experimental ou ecológico.</p>
        </div>
        <button class="btn-secondary" onclick="loadAlpha(this)">Atualizar</button>
      </div>
      <div id="plot-alpha" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Taxonomy barplot</h4>
          <p>Abundância relativa agregada por rank taxonômico com comparação entre grupos.</p>
        </div>
        <button class="btn-secondary" onclick="loadTaxonomyBar(this)">Atualizar</button>
      </div>
      <div id="plot-taxonomy-bar" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Taxonomy heatmap</h4>
          <p>Mapa interativo para detectar táxons dominantes e padrões locais de abundância.</p>
        </div>
        <button class="btn-secondary" onclick="loadTaxonomyHeatmap(this)">Atualizar</button>
      </div>
      <div id="plot-taxonomy-heatmap" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Beta heatmap</h4>
          <p>Distâncias Bray-Curtis entre amostras para ver coesão e blocos estruturais.</p>
        </div>
        <button class="btn-secondary" onclick="loadBetaHeatmap(this)">Atualizar</button>
      </div>
      <div id="plot-beta-heatmap" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Krona circular taxonomy</h4>
          <p>Visão radial da composição taxonômica para exploração hierárquica da abundância.</p>
        </div>
        <button class="btn-secondary" onclick="loadKrona(this)">Atualizar</button>
      </div>
      <div id="plot-krona" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Taxonomic tree</h4>
          <p>Árvore hierárquica da linhagem disponível no dataset. Útil para leitura estrutural rápida.</p>
        </div>
        <button class="btn-secondary" onclick="loadTree(this)">Atualizar</button>
      </div>
      <div id="plot-tree" class="plot-area"></div>
    </article>
    <article class="plot-card card">
      <div class="plot-head">
        <div>
          <h4>Co-abundance network</h4>
          <p>Rede de correlação entre táxons mais abundantes para evidenciar módulos e associações.</p>
        </div>
        <button class="btn-secondary" onclick="loadNetwork(this)">Atualizar</button>
      </div>
      <div id="plot-network" class="plot-area"></div>
    </article>
  </div>
</section>
"""


def _reporting() -> str:
    return """
<section class="section" id="reporting">
  <div class="control-grid">
    <div class="control-card card">
      <h4>Machine learning</h4>
      <div class="form-row">
        <div>
          <label>Target column</label>
          <input id="clf-target" type="text" value="biome">
        </div>
        <div>
          <label>Model</label>
          <select id="clf-model">
            <option value="random_forest">Random Forest</option>
            <option value="xgboost">XGBoost</option>
            <option value="svm">SVM</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div>
          <label>Train filter</label>
          <input id="clf-train" type="text" placeholder="biome IN ('Amazon','Cerrado')">
        </div>
        <div>
          <label>Test filter</label>
          <input id="clf-test" type="text" placeholder="biome = 'Pantanal'">
        </div>
      </div>
      <div class="quick-actions">
        <button class="btn-primary" onclick="runClassification(this)">Executar classificação</button>
      </div>
      <div class="panel-output" id="ml-output"></div>
    </div>
    <div class="control-card card">
      <h4>Relatório e logs</h4>
      <div class="form-row">
        <div>
          <label>Report title</label>
          <input id="report-title" type="text" value="FLORA Sequencing Analysis Report">
        </div>
        <div>
          <label>Report path</label>
          <input id="report-path" type="text" value="results/report.html">
        </div>
      </div>
      <div class="quick-actions">
        <button class="btn-accent" onclick="generateReport(this)">Gerar relatório HTML</button>
        <button class="btn-secondary" onclick="refreshLogs()">Atualizar logs</button>
      </div>
      <div class="panel-output" id="report-output"></div>
      <div class="mono-box log-box" id="log-box">Aguardando logs...</div>
    </div>
  </div>
</section>
"""


def _scripts() -> str:
    return """
<script>
const API = '';
const initialPlotText = '<div class="notice info">Carregue um dataset e dispare os gráficos para iniciar a exploração.</div>';

function qs(id) { return document.getElementById(id); }
function getValue(...ids) {
  for (const id of ids) {
    const el = qs(id);
    if (el && String(el.value || '').trim()) return String(el.value).trim();
  }
  return '';
}
function getNumber(ids, fallback) {
  const value = parseFloat(getValue(...ids));
  return Number.isFinite(value) ? value : fallback;
}
function groupValue() { return getValue('global-group-alt', 'global-group'); }
function normalizeValue() {
  const value = getValue('global-normalize-alt', 'matrix-normalize', 'global-normalize') || 'tss';
  return value === 'none' ? 'none' : value;
}
function prevalenceValue() {
  return getNumber(['matrix-prev-alt', 'matrix-prev'], 0.05);
}

function setLoading(btn, loading, label='Processando') {
  if (!btn) return;
  if (loading) {
    btn.dataset.original = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span>${label}`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.original || 'Executar';
    btn.disabled = false;
  }
}

async function apiFetch(path, method='GET', body=null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(API + path, opts);
    return await res.json();
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

function notice(type, message) {
  return `<div class="notice ${type}">${message}</div>`;
}

function setPanel(id, html) {
  const el = qs(id);
  if (el) el.innerHTML = html;
}

function renderResponse(id, data, formatter=null) {
  if (!data.success) {
    setPanel(id, notice('err', data.error || 'Falha na operação.'));
    return;
  }
  setPanel(id, formatter ? formatter(data) : notice('ok', 'Operação concluída.'));
}

function renderPlot(targetId, payload) {
  const container = qs(targetId);
  if (!container) return;
  if (!payload.success || !payload.plot) {
    container.innerHTML = notice('err', payload.error || 'Falha ao gerar gráfico.');
    return;
  }
  Plotly.newPlot(targetId, payload.plot.data, payload.plot.layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d', 'select2d']
  });
}

function updateMetrics(data) {
  const tables = data.tables || {};
  const metrics = [
    ['Samples', tables.samples || 0],
    ['ASV rows', tables.asv || 0],
    ['Taxonomy rows', tables.taxonomy || 0],
    ['Alpha metrics', tables.diversity_alpha || 0],
    ['Beta pairs', tables.diversity_beta || 0],
    ['Workdir', data.workdir || '—'],
  ];
  qs('metrics-grid').innerHTML = metrics.map(([label, value]) => `
    <div class="metric">
      <div class="label">${label}</div>
      <div class="value">${typeof value === 'number' ? value.toLocaleString() : value}</div>
    </div>
  `).join('');

  const checklist = [
    ['Alpha diversity: Shannon / Chao1', (tables.diversity_alpha || 0) > 0],
    ['Beta diversity: Bray-Curtis', (tables.diversity_beta || 0) > 0],
    ['Structure: PCoA / PCA / NMDS-ready', (tables.asv || 0) > 0 && (tables.samples || 0) > 0],
    ['Taxonomy: barplot + heatmap', (tables.taxonomy || 0) > 0],
    ['Statistics / ML overlays', (tables.samples || 0) > 0 && (tables.asv || 0) > 0],
  ];
  qs('publication-checklist').innerHTML = checklist.map(([label, done]) => `
    <div class="check-item ${done ? 'done' : ''}">
      <span class="check-mark">${done ? '✓' : '•'}</span>
      <span>${label}</span>
    </div>
  `).join('');
}

async function refreshStatus() {
  const data = await apiFetch('/api/status');
  const dot = qs('status-dot');
  const text = qs('status-text');
  if (data.success) {
    dot.className = 'status-dot live';
    text.textContent = 'DuckDB e pipeline acessíveis';
    updateMetrics(data);
  } else {
    dot.className = 'status-dot off';
    text.textContent = 'Conexão indisponível';
  }
}

function adoptDatasetPaths(data) {
  if (data.metadata && qs('meta-path')) qs('meta-path').value = data.metadata;
  if (data.asv_table && qs('asv-path')) qs('asv-path').value = data.asv_table;
  if (data.taxonomy && qs('tax-path')) qs('tax-path').value = data.taxonomy;
}

function syncGlobalControls() {
  const group = getValue('global-group-alt');
  const norm = getValue('global-normalize-alt');
  if (group && qs('global-group')) qs('global-group').value = group;
  if (norm && qs('global-normalize')) qs('global-normalize').value = norm;
  setPanel('matrix-config-output', notice('ok', 'Configurações globais sincronizadas com os gráficos.'));
}

async function ingestMetadata(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/metadata', 'POST', {
    path: qs('meta-path').value,
    sample_col: qs('meta-sample-col').value,
  });
  renderResponse('ingest-output', data, d => notice('ok', `Metadata carregada: <strong>${d.samples_ingested}</strong> amostras.`));
  setLoading(btn, false);
  refreshStatus();
}

async function ingestASV(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/asv', 'POST', {
    path: qs('asv-path').value,
    wide_format: qs('asv-wide').value === 'true',
  });
  renderResponse('ingest-output', data, d => notice('ok', `ASV carregada: <strong>${d.observations_ingested}</strong> observações.`));
  setLoading(btn, false);
  refreshStatus();
}

async function ingestTaxonomy(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/ingest/taxonomy', 'POST', { path: qs('tax-path').value });
  renderResponse('ingest-output', data, d => notice('ok', `Taxonomia carregada: <strong>${d.taxonomy_rows}</strong> linhas.`));
  setLoading(btn, false);
  refreshStatus();
}

async function ingestAll(btn) {
  setLoading(btn, true, 'Carregando');
  const meta = await apiFetch('/api/ingest/metadata', 'POST', {
    path: qs('meta-path').value,
    sample_col: qs('meta-sample-col').value,
  });
  if (!meta.success) {
    renderResponse('ingest-output', meta);
    setLoading(btn, false);
    return;
  }
  const asv = await apiFetch('/api/ingest/asv', 'POST', {
    path: qs('asv-path').value,
    wide_format: qs('asv-wide').value === 'true',
  });
  if (!asv.success) {
    renderResponse('ingest-output', asv);
    setLoading(btn, false);
    return;
  }
  const tax = await apiFetch('/api/ingest/taxonomy', 'POST', { path: qs('tax-path').value });
  renderResponse('ingest-output', tax, d => notice('ok', `Dataset carregado. Metadata=${meta.samples_ingested}, ASV=${asv.observations_ingested}, Taxonomy=${d.taxonomy_rows}.`));
  setLoading(btn, false);
  refreshStatus();
}

async function downloadSynthetic(btn) {
  setLoading(btn, true, 'Gerando');
  const data = await apiFetch('/api/download/synthetic', 'POST', {
    output_dir: qs('syn-outdir').value,
    samples: parseInt(qs('syn-samples').value, 10),
    features: parseInt(qs('syn-features').value, 10),
    seed: parseInt(qs('syn-seed').value, 10),
  });
  if (data.success) adoptDatasetPaths(data);
  const message = d => notice('ok', `Dataset sintético pronto em <strong>${d.metadata.replace('/metadata.tsv', '')}</strong>. Paths preenchidos automaticamente.`);
  renderResponse('analysis-output', data, message);
  renderResponse('download-synthetic-output', data, message);
  setLoading(btn, false);
}

async function downloadEMP(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/download/emp', 'POST', {
    output_dir: qs('emp-outdir').value,
    biome_filter: qs('emp-biome').value,
    max_samples: parseInt(qs('emp-maxsamples').value, 10),
  });
  if (data.success) adoptDatasetPaths(data);
  renderResponse('download-emp-output', data, d => notice('ok', `EMP baixado e preparado. Metadata, ASV e taxonomy já podem ser ingeridos.`));
  setLoading(btn, false);
}

async function downloadMGnify(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/download/mgnify', 'POST', {
    study_accession: qs('mg-study').value,
    biome: qs('mg-biome').value,
    output_dir: qs('mg-outdir').value,
    max_samples: parseInt(qs('mg-maxsamples').value, 10),
  });
  renderResponse('download-mgnify-output', data, d => notice('ok', `Download MGnify iniciado/concluído. Manifest: <strong>${d.manifest}</strong>.`));
  setLoading(btn, false);
}

async function downloadSRA(btn) {
  setLoading(btn, true);
  const accessions = qs('sra-accessions').value.split('\\n').map(v => v.trim()).filter(Boolean);
  const data = await apiFetch('/api/download/sra', 'POST', {
    accessions,
    output_dir: qs('sra-outdir').value,
    n_jobs: parseInt(qs('sra-jobs').value, 10),
  });
  renderResponse('download-sra-output', data, d => notice('ok', `Download SRA iniciado/concluído. Manifest: <strong>${d.manifest}</strong>.`));
  setLoading(btn, false);
}

async function computeDiversity(btn) {
  setLoading(btn, true);
  const depth = qs('div-depth').value;
  const data = await apiFetch('/api/diversity', 'POST', {
    metrics: ['shannon', 'observed_features', 'chao1'],
    sampling_depth: depth ? parseInt(depth, 10) : null,
  });
  renderResponse('analysis-output', data, d => notice('ok', `Diversidade calculada para <strong>${d.samples}</strong> amostras.`));
  setLoading(btn, false);
  refreshStatus();
}

async function previewMatrix(btn) {
  setLoading(btn, true);
  const norm = normalizeValue();
  const prev = prevalenceValue();
  const data = await apiFetch(`/api/feature_matrix?normalize=${norm}&min_prevalence=${prev}`);
  const formatter = d => notice('info', `Matriz: <strong>${d.n_samples}</strong> amostras x <strong>${d.n_features}</strong> features (${d.normalize}).`);
  renderResponse('matrix-output', data, formatter);
  renderResponse('workspace-output', data, formatter);
  setLoading(btn, false);
}

async function runClassification(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/ml/classify', 'POST', {
    model: qs('clf-model').value,
    target_column: qs('clf-target').value,
    cv_folds: 5,
    train_filter: qs('clf-train').value,
    test_filter: qs('clf-test').value,
    normalize: normalizeValue() === 'none' ? 'asv' : normalizeValue(),
  });
  renderResponse('ml-output', data, d => `
    <div class="metrics-grid">
      <div class="metric"><div class="label">Accuracy</div><div class="value">${(d.accuracy * 100).toFixed(1)}%</div></div>
      <div class="metric"><div class="label">F1 macro</div><div class="value">${(d.f1_macro * 100).toFixed(1)}%</div></div>
      <div class="metric"><div class="label">ROC-AUC</div><div class="value">${d.roc_auc ? (d.roc_auc * 100).toFixed(1) + '%' : '—'}</div></div>
      <div class="metric"><div class="label">CV accuracy</div><div class="value">${(d.cv_accuracy_mean * 100).toFixed(1)}%</div></div>
    </div>
    <div class="mono-box">${d.classification_report || ''}</div>
  `);
  setLoading(btn, false);
}

async function generateReport(btn) {
  setLoading(btn, true);
  const data = await apiFetch('/api/report', 'POST', {
    title: qs('report-title').value,
    output_path: qs('report-path').value,
  });
  renderResponse('report-output', data, d => notice('ok', `Relatório salvo em <strong>${d.report_path}</strong>.`));
  setLoading(btn, false);
}

async function refreshLogs() {
  const data = await apiFetch('/api/logs?n=120');
  if (!data.success) {
    qs('log-box').textContent = data.error || 'Falha ao carregar logs.';
    return;
  }
  qs('log-box').textContent = (data.lines || []).join('\\n') || 'Sem logs recentes.';
}

function plotQuery(base, params={}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  });
  return `${base}?${query.toString()}`;
}

async function loadPCoA(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/pcoa', { normalize: normalizeValue(), color_by: groupValue() }));
  renderPlot('plot-pcoa', data);
  setLoading(btn, false);
}

async function loadAlpha(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/alpha', { metric: 'shannon', group_by: groupValue() }));
  renderPlot('plot-alpha', data);
  setLoading(btn, false);
}

async function loadTaxonomyBar(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/taxonomy', { level: 'phylum', group_by: groupValue() }));
  renderPlot('plot-taxonomy-bar', data);
  setLoading(btn, false);
}

async function loadTaxonomyHeatmap(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/taxonomy_heatmap', { level: 'genus', top_n: 25 }));
  renderPlot('plot-taxonomy-heatmap', data);
  setLoading(btn, false);
}

async function loadBetaHeatmap(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/beta_heatmap', { normalize: normalizeValue(), metric: 'bray_curtis', max_samples: 60 }));
  renderPlot('plot-beta-heatmap', data);
  setLoading(btn, false);
  refreshStatus();
}

async function loadKrona(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/krona', { group_by: groupValue(), top_n: 120 }));
  renderPlot('plot-krona', data);
  setLoading(btn, false);
}

async function loadTree(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/tree', { group_by: groupValue(), top_n: 120 }));
  renderPlot('plot-tree', data);
  setLoading(btn, false);
}

async function loadNetwork(btn=null) {
  setLoading(btn, true);
  const data = await apiFetch(plotQuery('/api/viz/network', { level: 'genus', top_n: 18, threshold: 0.35 }));
  renderPlot('plot-network', data);
  setLoading(btn, false);
}

async function loadCoreVisuals(btn=null) {
  setLoading(btn, true, 'Carregando');
  await Promise.all([loadPCoA(), loadAlpha(), loadTaxonomyBar(), loadTaxonomyHeatmap()]);
  setLoading(btn, false);
}

async function loadAdvancedVisuals(btn=null) {
  setLoading(btn, true, 'Carregando');
  await Promise.all([loadBetaHeatmap(), loadKrona(), loadTree(), loadNetwork()]);
  setLoading(btn, false);
}

async function runPublicationSuite(btn) {
  setLoading(btn, true, 'Executando');
  await computeDiversity();
  await loadCoreVisuals();
  await loadAdvancedVisuals();
  setLoading(btn, false);
}

function primePlotAreas() {
  ['plot-pcoa','plot-alpha','plot-taxonomy-bar','plot-taxonomy-heatmap','plot-beta-heatmap','plot-krona','plot-tree','plot-network']
    .forEach(id => setPanel(id, initialPlotText));
}

document.querySelectorAll('.nav a').forEach(link => {
  link.addEventListener('click', event => {
    event.preventDefault();
    document.querySelectorAll('.nav a').forEach(item => item.classList.remove('active'));
    link.classList.add('active');
    const el = document.querySelector(link.getAttribute('href'));
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const group = btn.dataset.tabGroup;
    const target = btn.dataset.tabTarget;
    const prefix = group === 'downloads' ? 'download-' : 'workspace-';
    document.querySelectorAll(`.tab-btn[data-tab-group="${group}"]`).forEach(item => item.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll(`.tab-panel[id^="${prefix}"]`).forEach(panel => panel.classList.remove('active'));
    const panel = qs(target);
    if (panel) panel.classList.add('active');
  });
});

primePlotAreas();
refreshStatus();
refreshLogs();
setInterval(refreshStatus, 15000);
</script>
"""


def build_index_html() -> str:
    """Return the standalone web application HTML."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLORA Data Viz Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  {_styles()}
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <h1>FLORA</h1>
        <p>Feature Learning &amp; Omics Research Analytics<br>Sequencing visualization cockpit</p>
        <div class="status-pill">
          <span id="status-dot" class="status-dot"></span>
          <span id="status-text">Verificando pipeline...</span>
        </div>
      </div>
      <nav class="nav">
        <a href="#overview" class="active">Overview</a>
        <a href="#analysis">Análise microbioma</a>
        <a href="#workspace">Workspace</a>
        <a href="#downloads">Downloads</a>
        <a href="#visuals">Visualization Studio</a>
        <a href="#reporting">Relatório e ML</a>
      </nav>
      <div class="sidebar-footer">
        A análise padrão precisa cobrir diversidade, composição e estrutura.
        Esta UI foi organizada exatamente nessa lógica.
      </div>
    </aside>
    <main class="content">
      {_hero()}
      {_metrics()}
      {_guides()}
      {_workspace()}
      {_downloads()}
      {_visuals()}
      {_reporting()}
    </main>
  </div>
  {_scripts()}
</body>
</html>"""
