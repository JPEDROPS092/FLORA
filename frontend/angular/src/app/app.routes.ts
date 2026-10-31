import { Routes } from '@angular/router';

import { DownloadsPageComponent } from './features/downloads/downloads-page.component';
import { OverviewPageComponent } from './features/overview/overview-page.component';
import { ReportingPageComponent } from './features/reporting/reporting-page.component';
import { VisualsPageComponent } from './features/visuals/visuals-page.component';
import { WorkspacePageComponent } from './features/workspace/workspace-page.component';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'overview' },
  { path: 'overview', component: OverviewPageComponent },
  { path: 'workspace', component: WorkspacePageComponent },
  { path: 'downloads', component: DownloadsPageComponent },
  { path: 'visuals', component: VisualsPageComponent },
  { path: 'reporting', component: ReportingPageComponent },
  { path: '**', redirectTo: 'overview' }
];
