import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MessageService } from 'primeng/api';

import { AppComponent } from './app.component';
import { FloraRepository } from './core/data/flora.repository';

describe('AppComponent', () => {
  it('should create the research workspace shell', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [
        provideRouter([]),
        MessageService,
        {
          provide: FloraRepository,
          useValue: {
            source: {
              mode: 'mock',
              label: 'Estudo mockado',
              apiBaseUrl: '',
              mocked: true
            }
          }
        }
      ]
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.componentInstance).toBeTruthy();
    expect(fixture.nativeElement.textContent).toContain('Explorer');
    expect(fixture.nativeElement.textContent).toContain('ML Lab');
  });
});
