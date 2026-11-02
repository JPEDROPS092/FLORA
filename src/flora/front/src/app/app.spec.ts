import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { App } from './app';
import { FloraApiService, FloraStatus } from './core/api/flora-api.service';

describe('App (AppShell smoke)', () => {
  const status: FloraStatus = {
    success: true,
    status: 'connected',
    workdir: 'results',
    tables: { samples: 0 },
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideNoopAnimations(),
        { provide: FloraApiService, useValue: { getStatus: () => of(status) } },
      ],
    });
  });

  it('creates the root component with the shell rendered', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('flora-shell')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('nav')).toBeTruthy();
  });
});
