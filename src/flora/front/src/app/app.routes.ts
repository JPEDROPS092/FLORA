import { Routes } from '@angular/router';

import { t } from './core/i18n/i18n';

import { WelcomePageComponent } from './features/welcome/welcome-page.component';
import { AgentsPageComponent } from './features/agents/agents-page.component';
import { DashboardPageComponent } from './features/dashboard/dashboard-page.component';
import { DownloadsPageComponent } from './features/downloads/downloads-page.component';
import { ExplorerPageComponent } from './features/explorer/explorer-page.component';
import { MlLabPageComponent } from './features/ml-lab/ml-lab-page.component';
import { PipelinePageComponent } from './features/pipeline/pipeline-page.component';
import { ProjectsPageComponent } from './features/projects/projects-page.component';
import { ReportBuilderPageComponent } from './features/reports/report-builder-page.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'welcome' },
  { path: 'welcome', component: WelcomePageComponent, title: t('FLORA · Apresentação') },
  { path: 'dashboard', component: DashboardPageComponent, title: t('Research Dashboard') },
  { path: 'explorer', component: ExplorerPageComponent, title: t('Scientific Explorer') },
  { path: 'pipeline', component: PipelinePageComponent, title: t('Data Pipeline Studio') },
  { path: 'ml', component: MlLabPageComponent, title: t('AI & ML Lab'), data: { tone: 'lab' } },
  { path: 'reports', component: ReportBuilderPageComponent, title: t('Scientific Report Builder') },
  { path: 'agents', component: AgentsPageComponent, title: t('Agentes de IA') },
  { path: 'projects', component: ProjectsPageComponent, title: t('Projetos') },
  { path: 'downloads', component: DownloadsPageComponent, title: t('Downloads') },
  { path: 'overview', redirectTo: 'dashboard' },
  { path: 'workspace', redirectTo: 'pipeline' },
  { path: 'data', redirectTo: 'pipeline' },
  { path: 'visuals', redirectTo: 'explorer' },
  { path: 'analysis', redirectTo: 'explorer' },
  { path: 'analysis/ml', redirectTo: 'ml' },
  { path: 'results', redirectTo: 'reports' },
  { path: 'reporting', redirectTo: 'reports' },
  { path: '**', redirectTo: 'welcome' }
];
