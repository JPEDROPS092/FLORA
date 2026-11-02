import { DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MessageService, PrimeTemplate } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { DrawerModule } from 'primeng/drawer';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';

import { FloraRepository } from '../../core/data/flora.repository';
import { ResearchProject } from '../../core/models/domain';
import { TPipe } from '../../core/i18n/t.pipe';

@Component({
  selector: 'flora-projects',
  standalone: true,
  imports: [TPipe, 
    DecimalPipe,
    ReactiveFormsModule,
    PrimeTemplate,
    ButtonModule,
    DialogModule,
    DrawerModule,
    InputTextModule,
    TableModule,
    TagModule,
    TextareaModule
  ],
  template: `
    <section class="page">
      <header class="page-heading">
        <div>
          <p class="kicker">{{ 'Projetos' | t }}</p>
          <h1>{{ 'Perguntas, datasets e resultados' | t }}</h1>
          <p class="lede">{{ 'Cada projeto guarda o dataset, as análises e o que já foi concluído.' | t }}</p>
        </div>
        <div class="actions">
          @if (repository.source.mocked) { <p-tag [value]="'Dados mockados' | t" severity="secondary" /> }
          <p-button [label]="'Novo projeto' | t" icon="pi pi-plus" (onClick)="creating.set(true)" />
        </div>
      </header>

      <article class="surface">
        <p-table [value]="projects()" [paginator]="true" [rows]="8" dataKey="id">
          <ng-template pTemplate="header">
            <tr><th>{{ 'Projeto' | t }}</th><th>{{ 'Estado' | t }}</th><th>{{ 'Amostras' | t }}</th><th>{{ 'ASVs' | t }}</th><th>{{ 'Grupos' | t }}</th><th>{{ 'Atualizado' | t }}</th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-project>
            <tr (click)="selected.set(project)" style="cursor:pointer">
              <td>{{ project.name }}<div class="note">{{ project.question }}</div></td>
              <td>{{ project.status }}</td>
              <td>{{ project.samples | number }}</td>
              <td>{{ project.asvs | number }}</td>
              <td>{{ project.groups.join(', ') || '—' }}</td>
              <td>{{ project.updatedAt }}</td>
            </tr>
          </ng-template>
        </p-table>
      </article>
    </section>

    <p-drawer [visible]="!!selected()" (visibleChange)="ifBlank($event)" [header]="'Projeto' | t" position="right" [style]="{ width: '440px' }">
      @if (selected(); as project) {
        <p>{{ project.question }}</p>
        <p class="note">{{ project.datasetName }} · {{ project.marker }}</p>
        <h3>{{ 'Análises' | t }}</h3>
        <ul class="limitations">
          @for (item of project.analyses; track item.id) { <li>{{ item.name }} · {{ item.status }}</li> }
          @if (!project.analyses.length) { <li>{{ 'Nenhuma análise ligada.' | t }}</li> }
        </ul>
        <h3>{{ 'Resultados' | t }}</h3>
        <ul class="limitations">
          @for (item of project.results; track item.id) { <li><strong>{{ item.title }}.</strong> {{ item.summary }}</li> }
          @if (!project.results.length) { <li>{{ 'Nenhum resultado registrado.' | t }}</li> }
        </ul>
      }
    </p-drawer>

    <p-dialog [visible]="creating()" (visibleChange)="creating.set($event)" [header]="'Novo projeto' | t" [modal]="true" [style]="{ width: '460px' }">
      <form class="filters" [formGroup]="form" (ngSubmit)="save()">
        <div class="field">
          <label for="name">{{ 'Nome' | t }}</label>
          <input id="name" pInputText formControlName="name" />
          @if (form.controls.name.invalid && form.controls.name.touched) {
            <small class="field-error">{{ 'Dê um nome ao projeto.' | t }}</small>
          }
        </div>
        <div class="field">
          <label for="question">{{ 'Pergunta' | t }}</label>
          <textarea id="question" pTextarea rows="4" formControlName="question"></textarea>
          @if (form.controls.question.invalid && form.controls.question.touched) {
            <small class="field-error">{{ 'Escreva a pergunta científica.' | t }}</small>
          }
        </div>
        <p-button type="submit" [label]="'Criar' | t" />
      </form>
    </p-dialog>
  `
})
export class ProjectsPageComponent {
  readonly repository = inject(FloraRepository);
  private readonly messages = inject(MessageService);
  private readonly fb = inject(FormBuilder);

  readonly projects = signal<ResearchProject[]>([]);
  readonly selected = signal<ResearchProject | null>(null);
  readonly creating = signal(false);
  readonly form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    question: ['', Validators.required]
  });

  constructor() {
    void this.reload();
  }

  ifBlank(visible: boolean): void {
    if (!visible) {
      this.selected.set(null);
    }
  }

  async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const project = await this.repository.saveProject(this.form.getRawValue());
    this.messages.add({ severity: 'success', summary: 'Projeto', detail: project.name });
    this.creating.set(false);
    this.form.reset();
    await this.reload();
  }

  private async reload(): Promise<void> {
    this.projects.set(await this.repository.projects());
  }
}
