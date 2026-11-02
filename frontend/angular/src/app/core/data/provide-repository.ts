import { HttpClient } from '@angular/common/http';
import { EnvironmentProviders, makeEnvironmentProviders } from '@angular/core';

import { environment } from '../../../environments/environment';
import { FloraRepository } from './flora.repository';
import { HttpFloraRepository } from './http/http-flora.repository';
import { MockFloraRepository } from './mock/mock-flora.repository';

export function provideFloraRepository(): EnvironmentProviders {
  return makeEnvironmentProviders([
    {
      provide: FloraRepository,
      useFactory: (http: HttpClient) =>
        environment.useMocks ? new MockFloraRepository() : new HttpFloraRepository(http),
      deps: [HttpClient]
    }
  ]);
}
