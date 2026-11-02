import { Pipe, PipeTransform } from '@angular/core';

import { t } from './i18n';

/** `{{ 'Texto em português' | t }}` or `{{ 'Olá, {name}' | t: { name } }}` */
@Pipe({ name: 't', standalone: true })
export class TPipe implements PipeTransform {
  transform(source: string, params?: Record<string, string | number>): string {
    return t(source, params);
  }
}
