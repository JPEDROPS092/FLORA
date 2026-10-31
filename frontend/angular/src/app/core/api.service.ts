import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiResponse, ApiStatus, PlotResponse } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  status(): Promise<ApiStatus> {
    return firstValueFrom(this.http.get<ApiStatus>('/api/status'));
  }

  logs(lines = 120): Promise<ApiResponse> {
    return firstValueFrom(this.http.get<ApiResponse>(`/api/logs?n=${lines}`));
  }

  ingestMetadata(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/ingest/metadata', payload));
  }

  ingestAsv(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/ingest/asv', payload));
  }

  ingestTaxonomy(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/ingest/taxonomy', payload));
  }

  diversity(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/diversity', payload));
  }

  featureMatrix(normalize: string, minPrevalence: number): Promise<ApiResponse> {
    return firstValueFrom(
      this.http.get<ApiResponse>(
        `/api/feature_matrix?normalize=${encodeURIComponent(normalize)}&min_prevalence=${minPrevalence}`
      )
    );
  }

  classify(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/ml/classify', payload));
  }

  cluster(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/ml/cluster', payload));
  }

  generateReport(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/report', payload));
  }

  downloadSynthetic(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/download/synthetic', payload));
  }

  downloadEmp(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/download/emp', payload));
  }

  downloadMgnify(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/download/mgnify', payload));
  }

  downloadSra(payload: Record<string, unknown>): Promise<ApiResponse> {
    return firstValueFrom(this.http.post<ApiResponse>('/api/download/sra', payload));
  }

  plot(path: string, params: Record<string, string | number | null | undefined>): Promise<PlotResponse> {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        query.set(key, String(value));
      }
    });
    return firstValueFrom(this.http.get<PlotResponse>(`${path}?${query.toString()}`));
  }
}
