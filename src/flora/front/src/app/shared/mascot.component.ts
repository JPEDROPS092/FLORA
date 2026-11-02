import { Component, input } from '@angular/core';

export type MascotName = 'wave' | 'laptop' | 'binoculars' | 'celebrate' | 'fishing';

/** FLORA mascot sticker. Decorative by default (alt=""). */
@Component({
  selector: 'flora-mascot',
  standalone: true,
  template: `<img [src]="'branding/mascot/' + name() + '.webp'" [alt]="alt()" [style.width.px]="size()" [style.height]="'auto'" loading="lazy" decoding="async" />`,
  styles: [`:host { display: inline-block; line-height: 0; } img { filter: drop-shadow(0 6px 10px rgb(0 0 0 / .18)); max-width: 100%; }`]
})
export class MascotComponent {
  readonly name = input<MascotName>('wave');
  readonly size = input(120);
  readonly alt = input('');
}
