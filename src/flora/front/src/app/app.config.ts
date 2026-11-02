import { ApplicationConfig } from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router';
import { providePrimeNG } from 'primeng/config';
import { definePreset } from '@primeuix/themes';
import Aura from '@primeng/themes/aura';

import { routes } from './app.routes';

/** FLORA design tokens applied over the PrimeNG Aura preset (ADR 0001). */
export const FloraPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '{blue.50}',
      100: '{blue.100}',
      200: '{blue.200}',
      300: '{blue.300}',
      400: '{blue.400}',
      500: '#4f92ff',
      600: '#3b7ae8',
      700: '#2f63c4',
      800: '#274f9e',
      900: '#22407c',
      950: '#16294f',
    },
    colorScheme: {
      light: {
        surface: {
          0: '#ffffff',
          50: '{slate.50}',
          100: '{slate.100}',
          200: '{slate.200}',
          300: '{slate.300}',
          400: '{slate.400}',
          500: '{slate.500}',
          600: '{slate.600}',
          700: '{slate.700}',
          800: '{slate.800}',
          900: '{slate.900}',
          950: '#0b1526',
        },
      },
      dark: {
        surface: {
          0: '#e8eefb',
          50: '#d5e0f2',
          100: '#aebfdc',
          200: '#7d92b6',
          300: '#4a648f',
          400: '#2c4a73',
          500: '#1d3860',
          600: '#12294d',
          700: '#0f2140',
          800: '#0c1a33',
          900: '#081221',
          950: '#050b18',
        },
      },
    },
  },
});

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes, withComponentInputBinding(), withInMemoryScrolling({ scrollPositionRestoration: 'top' })),
    provideHttpClient(withFetch()),
    provideAnimationsAsync(),
    providePrimeNG({
      ripple: true,
      theme: {
        preset: FloraPreset,
        options: {
          darkModeSelector: '.app-dark',
          cssLayer: false,
        },
      },
    }),
  ],
};
