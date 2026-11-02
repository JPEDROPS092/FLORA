import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { CardModule } from 'primeng/card';
import { catchError, map, Observable, of } from 'rxjs';

import { FloraApiService, FloraStatus } from '../core/api/flora-api.service';

type HomeState =
  | { kind: 'checking' }
  | { kind: 'connected'; status: FloraStatus }
  | { kind: 'error' };

/**
 * Dashboard placeholder shipped with the AppShell (#4).
 * Replaced by the real Dashboard feature in issue #7.
 */
@Component({
  selector: 'flora-home-page',
  imports: [CardModule],
  template: `
    <div class="page-head">
      <h1>Dashboard</h1>
      <p class="flora-muted">Platform status and pipeline overview — full dashboard lands in issue #7.</p>
    </div>

    <p-card header="Backend">
      <dl class="kv">
        <dt>Connection</dt>
        <dd>{{ state().kind }}</dd>
        @if (detail(); as d) {
          <dt>Working directory</dt>
          <dd class="flora-mono">{{ d.workdir }}</dd>
          <dt>Database</dt>
          <dd class="flora-mono">{{ d.db_path ?? '—' }}</dd>
          <dt>Tables</dt>
          <dd>{{ tableCount() }}</dd>
        }
        @if (isError()) {
          <dt>Detail</dt>
          <dd>Backend unreachable — start it with <code>flora ui</code>.</dd>
        }
      </dl>
    </p-card>

    <p-card header="Next steps">
      <ol class="next-steps">
        <li>Ingest sample metadata, an ASV table, and taxonomy (#8).</li>
        <li>Explore the DuckDB warehouse (#9).</li>
        <li>Run diversity, feature engineering, and ML analyses (#10–#12).</li>
        <li>Generate a reproducible HTML report (#14).</li>
      </ol>
    </p-card>
  `,
  styles: `
    .page-head { margin-bottom: 1.25rem; }
    h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
    p-card { display: block; margin-bottom: 1rem; }
    .kv { display: grid; grid-template-columns: max-content 1fr; gap: 0.35rem 1.25rem; margin: 0; }
    dt { font-weight: 600; }
    dd { margin: 0; }
    .next-steps { margin: 0; padding-left: 1.25rem; display: grid; gap: 0.35rem; }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomePage {
  private readonly api = inject(FloraApiService);

  protected readonly state = toSignal(
    this.api.getStatus().pipe(
      map((status): HomeState => ({ kind: 'connected', status })),
      catchError((): Observable<HomeState> => of({ kind: 'error' })),
    ),
    { initialValue: { kind: 'checking' } as HomeState },
  );

  protected readonly detail = computed<FloraStatus | null>(() => {
    const s = this.state();
    return s.kind === 'connected' ? s.status : null;
  });

  protected readonly isError = computed(() => this.state().kind === 'error');

  protected tableCount(): number {
    const d = this.detail();
    return d ? Object.keys(d.tables).length : 0;
  }
}
