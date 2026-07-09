import { FaCheckCircle } from "react-icons/fa";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import { renderWizardIconBadge, renderForwardButtonLabel, renderForwardLinkLabel } from "@/shared/components/wizard";
import type { MigrationResult } from "../services/resultService";
import { getRepositoryLink } from "../utils/reportFormatting";
import { MigrationTimer } from "./MigrationTimer";

interface MigrationProgressViewProps {
  migrationJob: MigrationResult | null;
  migrationTimerNow: number;
  onCancel: () => void;
  onViewReport: () => void;
}

export function MigrationProgressView({ migrationJob, migrationTimerNow, onCancel, onViewReport }: MigrationProgressViewProps) {
  if (!migrationJob) return null;
  return (
    <div style={styles.card}>
      <div style={styles.stepHeader}>
        {renderWizardIconBadge(<FaCheckCircle />, "#22c55e", "xl")}
        <div>
          <h2 style={styles.title}>Migration Completed!</h2>
          <p style={styles.subtitle}>{migrationJob?.current_step || "Processing..."}</p>
        </div>
      </div>
      <MigrationTimer migrationJob={migrationJob} migrationTimerNow={migrationTimerNow} />
      <div style={styles.progressSection}>
        <div style={styles.progressHeader}><span>Overall Progress</span><span>{migrationJob?.progress_percent ?? 0}%</span></div>
        <div style={styles.progressBar}><div style={{ ...styles.progressFill, width: `${migrationJob?.progress_percent ?? 0}%` }} /></div>
      </div>
      <div style={styles.statsGrid}>
        <div style={styles.statBox}><div style={styles.statValue}>{migrationJob.files_modified}</div><div style={styles.statLabel}>Files Modified</div></div>
        <div style={styles.statBox}><div style={styles.statValue}>{migrationJob.issues_fixed}</div><div style={styles.statLabel}>Issues Fixed</div></div>
        <div style={styles.statBox}><div style={{ ...styles.statValue, color: "#22c55e" }}>{migrationJob.total_errors}</div><div style={styles.statLabel}>Errors</div></div>
        <div style={styles.statBox}><div style={{ ...styles.statValue, color: "#22c55e" }}>{migrationJob.total_warnings}</div><div style={styles.statLabel}>Warnings</div></div>
      </div>
      {migrationJob.status === "completed" && migrationJob.target_repo && (
        <div style={styles.successBox}>
          <div style={styles.successTitle}>Migration Successful!</div>
          <a href={getRepositoryLink(migrationJob.target_repo) || "#"} target="_blank" rel="noreferrer" style={styles.repoLink}>
            {renderForwardLinkLabel("View Migrated Repository")}
          </a>
        </div>
      )}
      <div style={styles.btnRow}>
        {(migrationJob.status === "cloning" || migrationJob.status === "analyzing" || migrationJob.status === "migrating") && (
          <button
            style={{ ...styles.secondaryBtn, marginRight: 10, backgroundColor: '#ef4444', color: 'white' }}
            onClick={onCancel}
          >
            Cancel Migration
          </button>
        )}
        {migrationJob.status !== "cloning" && migrationJob.status !== "analyzing" && migrationJob.status !== "migrating" && migrationJob.status !== "pending" && (
          <button style={styles.primaryBtn} onClick={onViewReport}>{renderForwardButtonLabel("View Migration Report")}</button>
        )}
      </div>
    </div>
  );
}
