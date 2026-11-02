import { Routes } from '@angular/router';

import { HomePage } from './pages/home.page';

/**
 * Feature routes land with their issues and use lazy loading, e.g.:
 *   { path: 'acquisition', loadComponent: () => import('./features/acquisition/acquisition.page').then(m => m.AcquisitionPage) } // #8
 */
export const routes: Routes = [
  { path: 'dashboard', component: HomePage, title: 'FLORA Studio — Dashboard' },
  { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
  { path: '**', redirectTo: 'dashboard' },
];
