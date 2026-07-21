import { FaCheckCircle, FaCode, FaCogs, FaFileAlt, FaRocket, FaSearch, FaVial } from "react-icons/fa";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import { renderWizardIconBadge } from "@/shared/components/wizard";
import type { MigrationResult } from "../services/resultService";
import { MigrationTimer } from "./MigrationTimer";

interface MigrationAnimationViewProps {
  loading: boolean;
  migrationJob: MigrationResult | null;
  migrationTimerNow: number;
  animationProgress: number;
  runFossa: boolean;
  runSonar: boolean;
  runTests: boolean;
  selectedRepoName: string | undefined;
  repoUrl: string;
  selectedSourceVersion: string;
  effectiveTargetVersion: string;
}

export function MigrationAnimationView({
  loading,
  migrationJob,
  migrationTimerNow,
  animationProgress,
  runFossa,
  runSonar,
  runTests,
  selectedRepoName,
  repoUrl,
  selectedSourceVersion,
  effectiveTargetVersion,
}: MigrationAnimationViewProps) {
  const isInitializingMigration = loading && !migrationJob?.job_id;
  const normalizedMigrationStatus = (() => {
    if (isInitializingMigration) return "starting";
    const currentStepText = (migrationJob?.current_step || "").toLowerCase();
    if (currentStepText.includes("fossa")) return "fossa_analysis";
    if (currentStepText.includes("sonar")) return "sonar_analysis";
    if (currentStepText.includes("test")) return "testing";
    return (migrationJob?.status || "pending").toLowerCase();
  })();

  const phaseRank: Record<string, number> = {
    pending: 0,
    cloning: 1,
    analyzing: 2,
    migrating: 3,
    testing: 4,
    sonar_analysis: 5,
    fossa_analysis: 6,
    pushing: 7,
    completed: 8,
    failed: 8,
  };

  const currentPhaseRank = phaseRank[normalizedMigrationStatus] ?? 0;
  const visibleProgress = isInitializingMigration
    ? 5
    : migrationJob?.status === "completed"
      ? 100
      : Math.min(Math.max(animationProgress, 5), 99);
  const qualityPhase = runFossa
    ? "fossa_analysis"
    : runSonar
      ? "sonar_analysis"
      : runTests
        ? "testing"
        : "migrating";

  const analysisComplete = currentPhaseRank > phaseRank.analyzing || migrationJob?.status === "completed";
  const dependencyComplete =
    currentPhaseRank > phaseRank.migrating ||
    migrationJob?.status === "completed" ||
    animationProgress >= 40;
  const transformationsComplete =
    currentPhaseRank > phaseRank.migrating ||
    migrationJob?.status === "completed" ||
    animationProgress >= 55;
  const qualityComplete =
    currentPhaseRank > phaseRank[qualityPhase] ||
    migrationJob?.status === "completed";
  const reportComplete = migrationJob?.status === "completed";
  const analysisVisible = currentPhaseRank >= phaseRank.analyzing || visibleProgress >= 10;
  const dependencyVisible = currentPhaseRank >= phaseRank.migrating || visibleProgress >= 30;
  const transformationsVisible = currentPhaseRank >= phaseRank.migrating || visibleProgress >= 50;
  const qualityVisible = currentPhaseRank >= phaseRank.testing || visibleProgress >= 60;
  const reportVisible = currentPhaseRank >= phaseRank.pushing || visibleProgress >= 90;
  const currentStepLabel = isInitializingMigration
    ? "Creating migration job and preparing the workspace..."
    : migrationJob?.current_step || "Initializing migration...";

  return (
    <div style={styles.card}>
      <div style={styles.stepHeader}>
        {renderWizardIconBadge(<FaRocket />, "#f59e0b", "xl")}
        <div>
          <h2 style={styles.title}>Migration in Progress</h2>
          <p style={styles.subtitle}>Your project is being migrated... Please wait.</p>
        </div>
      </div>

      <div style={styles.animationContainer}>
        <div style={styles.migrationAnimation}>
          <div style={styles.animationHeader}>
            <div style={styles.migratingText}>
            <span style={{ color: "#7c3aed" }}>Modernizing</span>{" "} {selectedRepoName || repoUrl.split("/").pop()?.replace(".git", "") || "Java Project"}
            </div>
            <div style={styles.versionTransition}>
              Java {selectedSourceVersion} {"->"} Java {effectiveTargetVersion || "Select Java Version"}
            </div>
          </div>

          <div style={styles.animationSteps}>
            <div style={{ ...styles.animationStep, opacity: analysisVisible ? 1 : 0.3, transition: "opacity 0.3s ease" }}>
              <div style={styles.stepIconAnimated}>{renderWizardIconBadge(<FaSearch />, "#0ea5e9", "md")}</div>
              <div style={styles.stepText}>Analyzing Source Code</div>
              {analysisComplete && <div style={styles.checkMarkAnimated}><FaCheckCircle /></div>}
            </div>

            <div style={{ ...styles.animationStep, opacity: dependencyVisible ? 1 : 0.3, transition: "opacity 0.3s ease" }}>
              <div style={styles.stepIconAnimated}>{renderWizardIconBadge(<FaCogs />, "#7c3aed", "md")}</div>
              <div style={styles.stepText}>Updating Dependencies</div>
              {dependencyComplete && <div style={styles.checkMarkAnimated}><FaCheckCircle /></div>}
            </div>

            <div style={{ ...styles.animationStep, opacity: transformationsVisible ? 1 : 0.3, transition: "opacity 0.3s ease" }}>
              <div style={styles.stepIconAnimated}>{renderWizardIconBadge(<FaCode />, "#22c55e", "md")}</div>
              <div style={styles.stepText}>Applying Code Transformations</div>
              {transformationsComplete && <div style={styles.checkMarkAnimated}><FaCheckCircle /></div>}
            </div>

            <div style={{ ...styles.animationStep, opacity: qualityVisible ? 1 : 0.3, transition: "opacity 0.3s ease" }}>
              <div style={styles.stepIconAnimated}>{renderWizardIconBadge(<FaVial />, "#f59e0b", "md")}</div>
              <div style={styles.stepText}>Running Tests &amp; Quality Checks</div>
              {qualityComplete && <div style={styles.checkMarkAnimated}><FaCheckCircle /></div>}
            </div>

            <div style={{ ...styles.animationStep, opacity: reportVisible ? 1 : 0.3, transition: "opacity 0.3s ease" }}>
              <div style={styles.stepIconAnimated}>{renderWizardIconBadge(<FaFileAlt />, "#22c55e", "md")}</div>
              <div style={styles.stepText}>Generating Migration Report</div>
              {reportComplete && <div style={styles.checkMarkAnimated}><FaCheckCircle /></div>}
            </div>
          </div>

          <div style={styles.progressExperienceSection}>
            <div style={styles.animatedProgressSection}>
              <div style={styles.animatedProgressHeader}>
                <span>Migration Progress</span>
                <span>{visibleProgress}%</span>
              </div>
              <div style={styles.animatedProgressBar}>
                <div style={{
                  ...styles.animatedProgressFill,
                  width: `${visibleProgress}%`,
                  background: `linear-gradient(90deg, #3b82f6 ${Math.max(visibleProgress - 10, 0)}%, #22c55e ${visibleProgress}%)`
                }} />
              </div>
            </div>

            <div style={styles.progressInsightRow}>
              <MigrationTimer migrationJob={migrationJob} migrationTimerNow={migrationTimerNow} />

              <div style={styles.statusHeroBlock}>
                <div style={styles.currentStatusHeadline}>{currentStepLabel}</div>
              </div>
            </div>
            {isInitializingMigration && (
              <div style={{ ...styles.recentLog, color: "#2563eb", fontSize: 12 }}>
                Info: loading the progress session. Large repositories can take a little longer to initialize.
              </div>
            )}
            {migrationJob?.status === "cloning" && (
              <div style={{ ...styles.recentLog, color: '#f59e0b', fontSize: 12 }}>
                Info: cloning repository... this may take a few minutes for large repositories. Please wait.
              </div>
            )}
          </div>
        </div>
      </div>

      {(qualityVisible || qualityComplete) && (() => {
        const functionalTesting = migrationJob?.test_pipeline?.functional_testing ?? migrationJob?.functional_pipeline ?? null;
        const runners = functionalTesting?.execution?.runners ?? [];
        const mockMvcRunners = runners.filter((r) =>
          r.tool === "MOCK_MVC" || r.tool?.toLowerCase().includes("mock") || r.tool?.toLowerCase().includes("springmvc")
        );
        const uiRunners = runners.filter((r) =>
          r.tool === "PLAYWRIGHT" || r.tool === "SELENIUM" || r.tool?.toLowerCase() === "playwright" || r.tool?.toLowerCase() === "selenium"
        );
        const springTestCases = functionalTesting?.test_cases ?? [];
        const filteredSpringTestCases = springTestCases.filter((tc) =>
          tc.tool === "MOCK_MVC" || tc.tool?.toLowerCase().includes("mock") || tc.tool?.toLowerCase().includes("spring")
        );
        if (runners.length === 0 && filteredSpringTestCases.length === 0) return null;
        const totalTests = runners.reduce((s: number, r) => s + (r.tests_run ?? 0), 0);
        const totalPassed = runners.reduce((s: number, r) => s + (r.tests_passed ?? 0), 0);
        const renderRunnerRow = (runner: (typeof runners)[number], idx: number) => (
          <div key={`runner-${idx}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "10px 14px", borderRadius: 10, border: "1px solid #bbf7d0", background: "#f0fdf4" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
              <span style={{ fontSize: 16 }}>{runner.status === "passed" ? "✅" : runner.status === "skipped" ? "⏭️" : "⚠️"}</span>
              <span style={{ fontWeight: 700, color: "#0f172a", fontSize: 13 }}>{runner.tool || "Tool"}</span>
              <span style={{ fontSize: 12, color: runner.status === "passed" ? "#166534" : runner.status === "skipped" ? "#6b7280" : "#dc2626", fontWeight: 600, textTransform: "uppercase" }}>{runner.status === "passed" ? "PASSED" : runner.status === "failed" ? "FAILED" : runner.status === "skipped" ? "SKIPPED" : runner.status || "EXECUTED"}</span>
              {runner.execution_mode && (
                <span style={{ fontSize: 11, color: "#64748b" }}>({runner.execution_mode === "internal_validation" ? "source validated" : "container validated"})</span>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              {runner.tests_run != null && runner.tests_run > 0 && (
                <>
                  <span style={{ fontSize: 12, color: "#64748b" }}>
                    <strong style={{ color: "#16a34a" }}>{runner.tests_passed ?? 0}</strong>/{runner.tests_run} passed
                  </span>
                  {(runner.tests_failed ?? 0) > 0 && (
                    <span style={{ fontSize: 12, color: "#dc2626", fontWeight: 600 }}>
                      {runner.tests_failed} failed
                    </span>
                  )}
                </>
              )}
              {runner.output_tail && (
                <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{runner.output_tail}</span>
              )}
            </div>
          </div>
        );
        return (
          <div style={{ marginTop: 20, border: "1px solid #bfdbfe", borderRadius: 12, background: "#f8fbff", overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 18px", background: "linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)", borderBottom: "1px solid #bfdbfe" }}>
              <FaVial style={{ fontSize: 16, color: "#2563eb" }} />
              <span style={{ fontWeight: 700, fontSize: 14, color: "#1e40af" }}>Functional Test Results</span>
              {runners.length > 0 && (
                <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 12, padding: "3px 10px", borderRadius: 999, background: runners.every(r => r.status === "passed") ? "#dcfce7" : "#fef3c7", color: runners.every(r => r.status === "passed") ? "#166534" : "#92400e", fontWeight: 700 }}>
                    {runners.every(r => r.status === "passed") ? "✅ All Passed" : "⚠️ Issues Found"}
                  </span>
                </span>
              )}
            </div>
            <div style={{ padding: "14px 18px" }}>
              {mockMvcRunners.length > 0 && (
                <div style={{ marginBottom: uiRunners.length > 0 ? 16 : 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>MockMvc &amp; Spring MVC</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {mockMvcRunners.map((runner, idx: number) => renderRunnerRow(runner, idx))}
                  </div>
                </div>
              )}
              {uiRunners.length > 0 && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>Playwright / Selenium</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {uiRunners.map((runner, idx: number) => renderRunnerRow(runner, idx))}
                  </div>
                </div>
              )}
              {totalTests > 0 && (
                <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap" }}>
                  <div style={{ padding: "10px 16px", borderRadius: 10, background: "#ffffff", border: "1px solid #e2e8f0", textAlign: "center", flex: 1, minWidth: 100 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#0f172a" }}>{totalTests}</div>
                    <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, textTransform: "uppercase" }}>Tests Run</div>
                  </div>
                  <div style={{ padding: "10px 16px", borderRadius: 10, background: "#f0fdf4", border: "1px solid #bbf7d0", textAlign: "center", flex: 1, minWidth: 100 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: "#16a34a" }}>{totalPassed}</div>
                    <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, textTransform: "uppercase" }}>Passed</div>
                  </div>
                  <div style={{ padding: "10px 16px", borderRadius: 10, background: totalTests - totalPassed > 0 ? "#fef2f2" : "#ffffff", border: `1px solid ${totalTests - totalPassed > 0 ? "#fecaca" : "#e2e8f0"}`, textAlign: "center", flex: 1, minWidth: 100 }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: totalTests - totalPassed > 0 ? "#dc2626" : "#64748b" }}>{totalTests - totalPassed}</div>
                    <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, textTransform: "uppercase" }}>Failed</div>
                  </div>
                  {totalTests > 0 && (
                    <div style={{ padding: "10px 16px", borderRadius: 10, background: "#ffffff", border: "1px solid #e2e8f0", textAlign: "center", flex: 1, minWidth: 100 }}>
                      <div style={{ fontSize: 22, fontWeight: 800, color: totalPassed === totalTests ? "#16a34a" : "#d97706" }}>{Math.round((totalPassed / totalTests) * 100)}%</div>
                      <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, textTransform: "uppercase" }}>Success Rate</div>
                    </div>
                  )}
                </div>
              )}
              {filteredSpringTestCases.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>Test Cases</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {filteredSpringTestCases.slice(0, 10).map((tc, idx: number) => (
                      <div key={`spring-tc-${idx}`} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff" }}>
                        <span style={{ fontSize: 14, color: tc.status === "passed" ? "#16a34a" : tc.status === "failed" ? "#dc2626" : "#64748b" }}>
                          {tc.status === "passed" ? "✅" : tc.status === "failed" ? "❌" : "⏳"}
                        </span>
                        <span style={{ fontWeight: 600, fontSize: 12, color: "#0f172a", flex: 1 }}>
                          {tc.name || `${tc.method || "GET"} ${tc.path || tc.route || tc.schema || "/"}`}
                        </span>
                        {tc.expectedStatus && (
                          <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: "#eff6ff", color: "#1d4ed8", fontWeight: 600 }}>{tc.expectedStatus}</span>
                        )}
                        <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: tc.status === "passed" ? "#dcfce7" : tc.status === "failed" ? "#fee2e2" : "#f1f5f9", color: tc.status === "passed" ? "#166534" : tc.status === "failed" ? "#991b1b" : "#475569", fontWeight: 600, textTransform: "uppercase" }}>
                          {tc.status || "GENERATED"}
                        </span>
                        {tc.validation_reason && (
                          <span style={{ fontSize: 11, color: "#64748b", fontStyle: "italic", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tc.validation_reason}</span>
                        )}
                      </div>
                    ))}
                    {filteredSpringTestCases.length > 10 && (
                      <div style={{ fontSize: 11, color: "#64748b", textAlign: "center", padding: 4 }}>
                        +{filteredSpringTestCases.length - 10} more test cases
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
