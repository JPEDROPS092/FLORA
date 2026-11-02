import { Routes } from '@angular/router';

import { DashboardPageComponent } from './features/dashboard/dashboard-page.component';
import { DownloadsPageComponent } from './features/downloads/downloads-page.component';
import { ExplorerPageComponent } from './features/explorer/explorer-page.component';
import { MlLabPageComponent } from './features/ml-lab/ml-lab-page.component';
import { PipelinePageComponent } from './features/pipeline/pipeline-page.component';
import { ProjectsPageComponent } from './features/projects/projects-page.component';
import { ReportBuilderPageComponent } from './features/reports/report-builder-page.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: 'dashboard', component: DashboardPageComponent, title: 'Research Dashboard' },
  { path: 'explorer', component: ExplorerPageComponent, title: 'Scientific Explorer' },
  { path: 'pipeline', component: PipelinePageComponent, title: 'Data Pipeline Studio' },
  { path: 'ml', component: MlLabPageComponent, title: 'AI & ML Lab', data: { tone: 'lab' } },
  { path: 'reports', component: ReportBuilderPageComponent, title: 'Scientific Report Builder' },
  { path: 'projects', component: ProjectsPageComponent, title: 'Projetos' },
  { path: 'downloads', component: DownloadsPageComponent, title: 'Downloads' },
  { path: 'overview', redirectTo: 'dashboard' },
  { path: 'workspace', redirectTo: 'pipeline' },
  { path: 'data', redirectTo: 'pipeline' },
  { path: 'visuals', redirectTo: 'explorer' },
  { path: 'analysis', redirectTo: 'explorer' },
  { path: 'analysis/ml', redirectTo: 'ml' },
  { path: 'results', redirectTo: 'reports' },
  { path: 'reporting', redirectTo: 'reports' },
  { path: '**', redirectTo: 'dashboard' }
];
