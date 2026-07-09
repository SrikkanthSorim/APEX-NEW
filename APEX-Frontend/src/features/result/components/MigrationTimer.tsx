import { FaStopwatch } from "react-icons/fa";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import type { MigrationResult } from "../services/resultService";

export function getMigrationElapsedSeconds(migrationJob: MigrationResult | null, migrationTimerNow: number): number {
  if (!migrationJob?.started_at) return 0;

  const startedAtMs = Date.parse(migrationJob.started_at);
  if (Number.isNaN(startedAtMs)) return 0;

  const completedAtMs = migrationJob.completed_at ? Date.parse(migrationJob.completed_at) : NaN;
  const endTimeMs = !Number.isNaN(completedAtMs) ? completedAtMs : migrationTimerNow;

  return Math.max(0, Math.floor((endTimeMs - startedAtMs) / 1000));
}

interface MigrationTimerProps {
  migrationJob: MigrationResult | null;
  migrationTimerNow: number;
}

export function MigrationTimer({ migrationJob, migrationTimerNow }: MigrationTimerProps) {
  if (!migrationJob?.started_at) return null;

  const migrationElapsedSeconds = getMigrationElapsedSeconds(migrationJob, migrationTimerNow);
  const normalizedTimerState = `${migrationJob?.status || ""} ${migrationJob?.current_step || ""}`.toLowerCase();
  const elapsedHours = Math.floor(migrationElapsedSeconds / 3600);
  const elapsedMinutes = Math.floor((migrationElapsedSeconds % 3600) / 60);
  const elapsedSeconds = migrationElapsedSeconds % 60;
  const elapsedSegments =
    elapsedHours > 0
      ? [
          { value: elapsedHours.toString().padStart(2, "0"), unit: "h" },
          { value: elapsedMinutes.toString().padStart(2, "0"), unit: "m" },
          { value: elapsedSeconds.toString().padStart(2, "0"), unit: "s" },
        ]
      : [
          { value: elapsedMinutes.toString().padStart(2, "0"), unit: "m" },
          { value: elapsedSeconds.toString().padStart(2, "0"), unit: "s" },
        ];
  const timerTheme = (() => {
    if (migrationJob?.status === "completed") {
      return {
        accent: "#059669",
        accentSoft: "rgba(16, 185, 129, 0.14)",
        border: "rgba(16, 185, 129, 0.24)",
        surface: "linear-gradient(135deg, #f3fff9 0%, #ecfdf5 48%, #ffffff 100%)",
        glow: "0 24px 54px rgba(16, 185, 129, 0.15)",
      };
    }

    if (migrationJob?.status === "failed") {
      return {
        accent: "#dc2626",
        accentSoft: "rgba(239, 68, 68, 0.14)",
        border: "rgba(239, 68, 68, 0.24)",
        surface: "linear-gradient(135deg, #fff7f7 0%, #fef2f2 45%, #ffffff 100%)",
        glow: "0 24px 54px rgba(239, 68, 68, 0.12)",
      };
    }

    if (normalizedTimerState.includes("analy")) {
      return {
        accent: "#0284c7",
        accentSoft: "rgba(14, 165, 233, 0.16)",
        border: "rgba(56, 189, 248, 0.26)",
        surface: "linear-gradient(135deg, #f2fbff 0%, #eef8ff 42%, #ffffff 100%)",
        glow: "0 24px 54px rgba(14, 165, 233, 0.12)",
      };
    }

    if (normalizedTimerState.includes("test") || normalizedTimerState.includes("sonar") || normalizedTimerState.includes("fossa")) {
      return {
        accent: "#d97706",
        accentSoft: "rgba(245, 158, 11, 0.16)",
        border: "rgba(251, 191, 36, 0.28)",
        surface: "linear-gradient(135deg, #fffaf0 0%, #fff7ed 45%, #ffffff 100%)",
        glow: "0 24px 54px rgba(245, 158, 11, 0.13)",
      };
    }

    return {
      accent: "#7c3aed",
      accentSoft: "rgba(124, 58, 237, 0.14)",
      border: "rgba(167, 139, 250, 0.3)",
      surface: "linear-gradient(135deg, #f8f5ff 0%, #f5f3ff 44%, #ffffff 100%)",
      glow: "0 24px 54px rgba(124, 58, 237, 0.14)",
    };
  })();

  return (
    <div style={styles.migrationTimerSection}>
      <div style={styles.migrationTimerCard}>
        <div style={styles.migrationTimerHero}>
          <div
            style={{
              ...styles.migrationTimerOrb,
              background: `radial-gradient(circle at 30% 30%, #ffffff 0%, ${timerTheme.accentSoft} 58%, rgba(255,255,255,0.92) 100%)`,
              border: `1px solid ${timerTheme.border}`,
              boxShadow: `inset 0 1px 0 rgba(255,255,255,0.72), 0 10px 22px ${timerTheme.accentSoft}`,
            }}
          >
            <div
              style={{
                ...styles.migrationTimerOrbInner,
                color: timerTheme.accent,
                background: "#ffffff",
                boxShadow: `0 0 0 8px ${timerTheme.accentSoft}`,
              }}
            >
              <FaStopwatch />
            </div>
          </div>

          <div style={styles.migrationTimerCopy}>
            <div style={{ ...styles.migrationTimerLabel, color: timerTheme.accent }}>Elapsed Time</div>
            <div style={styles.migrationTimerValue}>
              {elapsedSegments.map((segment) => (
                <span key={`${segment.value}${segment.unit}`} style={styles.migrationTimerSegment}>
                  <span style={styles.migrationTimerDigits}>{segment.value}</span>
                  <span style={styles.migrationTimerUnit}>{segment.unit}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
