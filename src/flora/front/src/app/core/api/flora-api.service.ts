import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

/** Response of `GET /api/status` (flora.ui.server). */
export interface FloraStatus {
  success: boolean;
  status: string;
  workdir: string;
  db_path?: string;
  tables: Record<string, number>;
}

/**
 * Minimal client for the FLORA JSON API. Grows per endpoint contract in #5;
 * only `/api/status` is needed by the AppShell connection badge (#4).
 */
@Injectable({ providedIn: 'root' })
export class FloraApiService {
  private readonly http = inject(HttpClient);

  getStatus(): Observable<FloraStatus> {
    return this.http.get<FloraStatus>('/api/status');
  }
}
