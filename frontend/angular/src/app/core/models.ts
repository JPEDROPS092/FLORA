export interface FrontendStatus {
  mode: string;
}

export interface ApiStatus {
  success: boolean;
  status: string;
  workdir: string;
  db_path?: string;
  frontend?: FrontendStatus;
  tables: Record<string, number>;
  error?: string;
}

export interface ApiResponse {
  success: boolean;
  error?: string;
  [key: string]: unknown;
}

export interface PlotResponse extends ApiResponse {
  plot?: {
    data: unknown[];
    layout: Record<string, unknown>;
  };
}
