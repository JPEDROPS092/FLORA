import { registerLocaleData } from '@angular/common';
import { provideHttpClient } from '@angular/common/http';
import localePt from '@angular/common/locales/pt';
import { LANG, LOCALE, t } from './core/i18n/i18n';
import { ApplicationConfig, LOCALE_ID, provideZoneChangeDetection } from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withInMemoryScrolling } from '@angular/router';
import { MessageService } from 'primeng/api';
import { providePrimeNG } from 'primeng/config';

import { routes } from './app.routes';
import { provideFloraRepository } from './core/data/provide-repository';
import FloraPreset from './core/theme/flora.preset';

registerLocaleData(localePt);
document.documentElement.lang = LANG === 'pt' ? 'pt-BR' : 'en';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideAnimationsAsync(),
    provideHttpClient(),
    provideRouter(
      routes,
      withInMemoryScrolling({
        scrollPositionRestoration: 'enabled',
        anchorScrolling: 'enabled'
      })
    ),
    providePrimeNG({
      translation: {
        emptyMessage: t('Sem resultados'),
        emptyFilterMessage: t('Sem resultados'),
        apply: t('Aplicar'),
        clear: t('Limpar'),
        accept: t('Sim'),
        reject: t('Não')
      },
      theme: {
        preset: FloraPreset,
        options: {
          darkModeSelector: '.flora-dark'
        }
      }
    }),
    { provide: LOCALE_ID, useValue: LOCALE },
    MessageService,
    provideFloraRepository()
  ]
};
