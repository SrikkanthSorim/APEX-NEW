import type { MigrationResult } from "../services/resultService";

/**
 * Elapsed migration time in whole seconds, from `started_at` to `completed_at`
 * (or `migrationTimerNow` while still running). Returns 0 when timestamps are
 * missing or unparseable.
 */
export function getMigrationElapsedSeconds(
  migrationJob: MigrationResult | null,
  migrationTimerNow: number,
): number {
  if (!migrationJob?.started_at) return 0;

  const startedAtMs = Date.parse(migrationJob.started_at);
  if (Number.isNaN(startedAtMs)) return 0;

  const completedAtMs = migrationJob.completed_at ? Date.parse(migrationJob.completed_at) : NaN;
  const endTimeMs = !Number.isNaN(completedAtMs) ? completedAtMs : migrationTimerNow;

  return Math.max(0, Math.floor((endTimeMs - startedAtMs) / 1000));
}
