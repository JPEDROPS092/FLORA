import { IngestOutcome, IngestStepResult } from '../models/domain';

/**
 * An ingest batch succeeds only when every step succeeds.
 * A single `success: true` envelope used to hide a failed taxonomy or ASV load.
 */
export function aggregateIngest(steps: IngestStepResult[]): IngestOutcome {
  const failed = steps.filter((step) => !step.success);
  const success = steps.length > 0 && failed.length === 0;
  return {
    success,
    steps,
    error: failed.length
      ? failed.map((step) => `${step.step}: ${step.error ?? 'falhou'}`).join('; ')
      : undefined
  };
}
