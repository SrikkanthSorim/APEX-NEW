import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import {
  FaCheckCircle,
  FaFolderOpen,
  FaLink,
  FaProjectDiagram,
  FaRocket,
  FaSearch,
} from "react-icons/fa";
import { useLocation, useNavigate } from "react-router-dom";
import {
  buildHtmlFilename,
  downloadHtmlDocument,
} from "@/features/result/utils/migrationWizardPdf";
import {
  analyzeRepoUrl,
  analyzeLocalProject,
  getRepoVisibility,
  listLocalProjectFiles,
  getLocalProjectFileContent,
} from "@/features/connect/services/connectService";
import {
  listRepoFiles,
  getFileContent,
  getMicroserviceEligibility,
  getLocalProjectMicroserviceEligibility,
  generateGithubDocument,
  generateLocalProjectDocument,
  type GithubDocumentResponse,
} from "@/features/discovery/services/discoveryService";
import {
  getJavaVersions,
  getJavaVersionRecommendation,
  type JavaVersionRecommendationResponse,
  type StrategyPageContext,
} from "@/features/strategy/services/strategyService";
import { ApiError } from "@/services/http/client";
import {
    getMigrationDetail,
    getMigrationStatusSummary,
    getMigrationLogs,
    startMigration,
  getMigrationFossa,
  type MigrationJobSummary,
  type MigrationResult,
} from "@/features/result/services/resultService";
import type {
  RepoAnalysis,
  DependencyInfo,
  MicroserviceEligibilityResult,
  MicroserviceServiceCandidate,
} from "@/shared/types/domain";
import {
  previewMigration,
  type PreviewFileDiff,
} from "@/features/modernization/services/modernizationService";
import {
  clearWizardStorage,
  readSessionJson,
  type PersistedWizardFormState,
  WIZARD_FORM_STATE_KEY,
} from "@/shared/utils/migrationWizardStorage";
import { getStepFromPath, STEP_ROUTES } from "@/config/stepRoutes";
import { useMigrationWizardPersistence } from "@/shared/hooks/useMigrationWizardPersistence";
import { isPrivateRepoAccessError } from "@/shared/utils/repoAccessError";
import { buildWizardAccentVars } from "@/shared/components/wizard";
import { useRepositoryConnect } from "@/features/connect/hooks/useRepositoryConnect";
import { useDiscoveryState } from "@/features/discovery/hooks/useDiscoveryState";
import { useStrategyState, type MigrationApproachValue } from "@/features/strategy/hooks/useStrategyState";
import { useModernizationState } from "@/features/modernization/hooks/useModernizationState";
import { useMigrationExecution } from "@/features/result/hooks/useMigrationExecution";
interface DiffLineEntry {
  type: "add" | "remove" | "context" | "hunk";
  oldLineNumber: number | null;
  newLineNumber: number | null;
  content: string;
}

interface CodeChangeEntry {
  fileName: string;
  filePath: string;
  changeType: "modified" | "added" | "deleted";
  additions: number;
  deletions: number;
  oldContent: string;
  newContent: string;
  diffLines: DiffLineEntry[];
}

interface PrefetchedBrdDocument {
  filename: string;
  html: string;
}

const mergeMigrationSummaryIntoJob = (
  previous: MigrationResult | null,
  summary: MigrationJobSummary
): MigrationResult => ({
  ...(previous ?? {
    dependencies: [],
    migration_log: [],
    issues: [],
    file_diffs: [],
    test_insights: [],
    target_repo: null,
    test_summary: null,
    test_llm_model: null,
    sonar_quality_gate: null,
    sonar_error_message: null,
    fossa_policy_status: null,
    fossa_total_dependencies: 0,
    fossa_license_issues: 0,
    fossa_vulnerabilities: 0,
    fossa_outdated_dependencies: 0,
    fossa_scan_mode: null,
    fossa_real_scan: false,
    fossa_analysis_url: null,
    fossa_error_message: null,
    error_message: null,
    started_at: summary.started_at,
    worker_started_at: summary.worker_started_at ?? null,
    completed_at: summary.completed_at,
    conversion_types: summary.conversion_types,
    source_repo: summary.source_repo,
    source_java_version: summary.source_java_version,
    target_java_version: summary.target_java_version,
    status: summary.status,
    progress_percent: summary.progress_percent,
    current_step: summary.current_step,
    files_modified: summary.files_modified,
    issues_fixed: summary.issues_fixed,
    api_endpoints_validated: summary.api_endpoints_validated,
    api_endpoints_working: summary.api_endpoints_working,
    sonar_bugs: summary.sonar_bugs,
    sonar_vulnerabilities: summary.sonar_vulnerabilities,
    sonar_code_smells: summary.sonar_code_smells,
    sonar_coverage: summary.sonar_coverage,
    tests_run: summary.tests_run,
    tests_passed: summary.tests_passed,
    tests_failed: summary.tests_failed,
    total_errors: summary.total_errors,
    total_warnings: summary.total_warnings,
    errors_fixed: summary.errors_fixed,
    warnings_fixed: summary.warnings_fixed,
    dependency_count: summary.dependency_count,
    job_id: summary.job_id,
  }),
  job_id: summary.job_id,
  status: summary.status,
  source_repo: summary.source_repo,
  target_repo: summary.target_repo,
  source_java_version: summary.source_java_version,
  target_java_version: summary.target_java_version,
  conversion_types: summary.conversion_types,
  started_at: summary.started_at,
  worker_started_at: summary.worker_started_at ?? previous?.worker_started_at ?? null,
  completed_at: summary.completed_at,
  progress_percent: summary.progress_percent,
  current_step: summary.current_step,
  files_modified: summary.files_modified,
  issues_fixed: summary.issues_fixed,
  api_endpoints_validated: summary.api_endpoints_validated,
  api_endpoints_working: summary.api_endpoints_working,
  tests_run: summary.tests_run,
  tests_passed: summary.tests_passed,
  tests_failed: summary.tests_failed,
  sonar_quality_gate: summary.sonar_quality_gate ?? null,
  sonar_bugs: summary.sonar_bugs,
  sonar_vulnerabilities: summary.sonar_vulnerabilities,
  sonar_code_smells: summary.sonar_code_smells,
  sonar_coverage: summary.sonar_coverage,
  sonar_duplications: summary.sonar_duplications,
  sonar_security_hotspots: summary.sonar_security_hotspots,
  sonar_scan_mode: summary.sonar_scan_mode ?? null,
  sonar_real_scan: summary.sonar_real_scan,
  sonar_analysis_url: summary.sonar_analysis_url ?? null,
  sonar_error_message: summary.sonar_error_message ?? null,
  fossa_policy_status: summary.fossa_policy_status ?? null,
  fossa_total_dependencies: summary.fossa_total_dependencies,
  fossa_license_issues: summary.fossa_license_issues,
  fossa_vulnerabilities: summary.fossa_vulnerabilities,
  fossa_outdated_dependencies: summary.fossa_outdated_dependencies,
  fossa_scan_mode: summary.fossa_scan_mode ?? null,
  fossa_real_scan: summary.fossa_real_scan,
  fossa_analysis_url: summary.fossa_analysis_url ?? null,
  fossa_error_message: summary.fossa_error_message ?? null,
  error_message: summary.error_message ?? null,
  total_errors: summary.total_errors,
  total_warnings: summary.total_warnings,
  errors_fixed: summary.errors_fixed,
  warnings_fixed: summary.warnings_fixed,
  dependency_count: summary.dependency_count,
});

const TERMINAL_MIGRATION_STATUSES = new Set(["completed", "failed", "cancelled"]);

const isTerminalMigrationStatus = (status: string | null | undefined): boolean =>
  Boolean(status && TERMINAL_MIGRATION_STATUSES.has(status.toLowerCase()));

const getMigrationPollingDelayMs = (status: string | null | undefined, startedAt?: string | null): number => {
  const normalizedStatus = (status || "").toLowerCase();
  
  const startedAtMs = startedAt ? Date.parse(startedAt) : Number.NaN;
  const elapsedMs = Number.isNaN(startedAtMs) ? 0 : Math.max(0, Date.now() - startedAtMs);
  
  // Progressive backoff based on elapsed time and status
  let baseDelayMs: number;
  
  if (normalizedStatus === "queued" || normalizedStatus === "pending") {
    // Queue: start at 8s, increase to 15s after 60s
    baseDelayMs = elapsedMs >= 60_000 ? 15000 : 8000;
  } else if (normalizedStatus === "stale") {
    baseDelayMs = 5000;
  } else if (normalizedStatus === "cancel_requested") {
    baseDelayMs = 3000;
  } else {
    // In-progress or other states: progressive backoff
    // 0-2 min: 5s, 2-5 min: 8s, 5-10 min: 12s, 10+ min: 18s
    if (elapsedMs < 120_000) {
      baseDelayMs = 5000;
    } else if (elapsedMs < 300_000) {
      baseDelayMs = 8000;
    } else if (elapsedMs < 600_000) {
      baseDelayMs = 12000;
    } else {
      baseDelayMs = 18000;
    }
  }

  // If browser tab is hidden, use 25+ seconds to reduce background load
  if (typeof document !== "undefined" && document.visibilityState === "hidden") {
    return Math.max(baseDelayMs, 25000);
  }

  return baseDelayMs;
};

type DependencyCategory =
  | "Framework"
  | "Testing"
  | "Logging"
  | "Persistence"
  | "Security"
  | "Build"
  | "Jakarta / Java EE"
  | "Data / JSON"
  | "Utilities"
  | "Other";

type DependencyRiskLevel = "critical" | "high" | "medium" | "low";
type DependencyRiskFilter = DependencyRiskLevel | "all";

interface CategorizedDependency extends DependencyInfo {
  displayName: string;
  category: DependencyCategory;
  risk: DependencyRiskLevel;
  reason: string;
}

type MicroserviceAccordionKey =
  | "signals"
  | "scores"
  | "services"
  | "concerns"
  | "strategy"
  | "observations";

const REPORT_DIFFS_PAGE_SIZE = 25;
const createDefaultMicroserviceAccordionState = (): Record<MicroserviceAccordionKey, boolean> => ({
  signals: true,
  scores: false,
  services: false,
  concerns: false,
  strategy: false,
  observations: false,
});

const normalizeAssessmentScore = (value: number) => {
  const normalizedScore = value <= 1 ? value * 100 : value;
  return Math.max(5, Math.min(95, Math.round(normalizedScore)));
};

const _getMicroserviceFitScore = (result?: MicroserviceEligibilityResult | null) => {
  if (!result) return 50;
  return normalizeAssessmentScore(typeof result.score === "number" ? result.score : 50);
};

const _getMicroserviceAssessmentLabel = (result?: MicroserviceEligibilityResult | null) => {
  return result?.eligibility || "NOT ELIGIBLE";
};

const _getAssessmentBarColor = (score: number) => {
  if (score >= 75) return "#22c55e";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
};

const _getMicroserviceScoreTooltip = (metricName: string) => {
  const explanations: Record<string, { title: string; description: string; interpretation: string }> = {
    "Domain separation": {
      title: "How clearly the application is split into business areas",
      description: "This checks whether the code already looks organized into meaningful functional areas such as users, payments, or reporting.",
      interpretation: "Higher is better. A higher score means the system may be easier to split with clear ownership.",
    },
    Coupling: {
      title: "How tightly different parts of the application depend on each other",
      description: "This measures whether modules are tangled together through shared logic, direct calls, or circular dependencies.",
      interpretation: "Higher is better. A higher score means the modules are more independent and easier to separate.",
    },
    "DB independence": {
      title: "How independently each area can manage its own data",
      description: "This checks whether modules can work with their own data boundaries instead of relying heavily on the same shared tables or queries.",
      interpretation: "Higher is better. A higher score means the system is less tied to one shared data model.",
    },
    Scalability: {
      title: "How easily parts of the system could scale on their own",
      description: "This looks for signs that certain workloads could grow independently, such as heavy processing, scheduled jobs, or traffic spikes.",
      interpretation: "Higher is better. A higher score means there are stronger signs that some areas could scale separately.",
    },
    "Deployment independence": {
      title: "How easily parts of the system could be released separately",
      description: "This checks whether modules appear self-contained enough that they could eventually be deployed without moving the whole application together.",
      interpretation: "Higher is better. A higher score means teams may be able to release parts of the system more independently.",
    },
    "Failure isolation": {
      title: "How well problems in one area stay contained",
      description: "This measures whether an issue in one module is likely to remain local instead of spreading across many parts of the application.",
      interpretation: "Higher is better. A higher score means failures may be easier to isolate and control.",
    },
    "Async/event readiness": {
      title: "How prepared the system is for event-driven communication",
      description: "This looks for messaging, background jobs, scheduling, or asynchronous processing patterns that support decoupled communication.",
      interpretation: "Higher is better. A higher score means the application shows more readiness for async or event-based architecture.",
    },
  };

  return (
    explanations[metricName] || {
      title: "How supportive this area is for microservice adoption",
      description: "This score reflects whether this part of the codebase helps or hinders splitting the application into clearer, more independent services.",
      interpretation: "Higher is better. A higher score means this area creates fewer obstacles for service separation.",
    }
  );
};

const _getMicroserviceServiceTagTooltip = (
  tag: string,
  candidate: MicroserviceServiceCandidate
) => {
  const normalizedTag = tag.trim().toLowerCase();
  const integrationPreview = (candidate.external_integrations || []).slice(0, 2).join(", ");

  if (normalizedTag.includes("cpu-intensive")) {
    return {
      title: "CPU-intensive work",
      description:
        "This candidate appears to spend more effort on computation, business rules, transformations, or in-memory processing than on waiting for outside systems.",
      interpretation:
        "Why it is shown: the analyzer found scaling signals suggesting this area may need extra compute capacity when load grows.",
    };
  }

  if (normalizedTag.includes("io-intensive")) {
    return {
      title: "I/O-intensive work",
      description:
        "This candidate appears to spend more time waiting on databases, APIs, files, or network calls than on raw computation.",
      interpretation: integrationPreview
        ? `Why it is shown: the analyzer found access or integration patterns such as ${integrationPreview}, which often benefit from targeted scaling and isolation.`
        : "Why it is shown: the analyzer found access or communication patterns that often benefit from independent scaling and failure isolation.",
    };
  }

  if (
    normalizedTag.includes("rest") ||
    normalizedTag.includes("client") ||
    normalizedTag.includes("api") ||
    normalizedTag.includes("queue") ||
    normalizedTag.includes("event") ||
    normalizedTag.includes("messag")
  ) {
    return {
      title: `External integration: ${tag}`,
      description:
        "This tag indicates the candidate talks to another system or communication layer, such as an API, client, queue, or messaging channel.",
      interpretation:
        "Why it is shown: external integrations are useful service-boundary signals because they affect latency, retries, and failure isolation.",
    };
  }

  return {
    title: tag,
    description:
      "This tag is a workload or integration hint the analyzer found while reviewing the candidate's code structure and dependencies.",
    interpretation:
      "Why it is shown: the analyzer believes this characteristic matters when deciding whether the candidate could become its own service.",
  };
};

const MIGRATION_STEPS = [
  {
    id: 1,
    name: "Connect",
    icon: <FaLink />,
    accent: "#2563eb",
    description: "Connect to GitHub Repository",
    summary: "Enter your GitHub repository URL to start the migration process"
  },
  {
    id: 2,
    name: "Discovery",
    icon: <FaSearch />,
    accent: "#0ea5e9",
    description: "Repository Discovery & Dependencies",
    summary: "Explore repository structure and analyze project dependencies"
  },
  {
    id: 3,
    name: "Strategy",
    icon: <FaProjectDiagram />,
    accent: "#f97316",
    description: "Assessment & Migration Strategy",
    summary: "Review assessment results and define the migration roadmap"
  },
  {
    id: 4,
    name: "Migration",
    icon: <FaRocket />,
    accent: "#f59e0b",
    description: "Build Modernization & Migration",
    summary: "Execute the upgrade using automation tools and refactor legacy components"
  },
  {
    id: 5,
    name: "Result",
    icon: <FaCheckCircle />,
    accent: "#22c55e",
    description: "Migration Results",
    summary: "View migration report and download migrated project"
  },
];

const DEFAULT_TARGET_GITHUB_OWNER = "Javaapex";
const DEFAULT_TARGET_GITHUB_HOST = "github.com";

const getIndicatorStep = (step: number) => Math.min(step, MIGRATION_STEPS.length);

let jsPdfModulePromise: Promise<typeof import("jspdf")["jsPDF"]> | null = null;
let zipSyncModulePromise: Promise<typeof import("fflate")["zipSync"]> | null = null;

const loadJsPdf = async () => {
  if (!jsPdfModulePromise) {
    jsPdfModulePromise = import("jspdf").then((module) => module.jsPDF);
  }

  return jsPdfModulePromise;
};

const loadZipSync = async () => {
  if (!zipSyncModulePromise) {
    zipSyncModulePromise = import("fflate").then((module) => module.zipSync);
  }

  return zipSyncModulePromise;
};

export function useWizardController() {
  const navigate = useNavigate();
  const location = useLocation();
  const persistedFormState =
    readSessionJson<PersistedWizardFormState>(WIZARD_FORM_STATE_KEY);
  const initialStep =
    typeof window !== "undefined" ? getStepFromPath(window.location.pathname) : 1;
  const generateRepoTimestamp = () => {
    const now = new Date();
    const pad = (value: number) => value.toString().padStart(2, "0");

    return [
      now.getFullYear(),
      pad(now.getMonth() + 1),
      pad(now.getDate()),
      pad(now.getHours()),
      pad(now.getMinutes()),
      pad(now.getSeconds()),
    ].join("");
  };

  const buildTargetRepoUrl = (
    repoName: string,
    timestamp: string,
    owner: string = "owner",
    host: string = "github.com"
  ) => `https://${host}/${owner}/${repoName || "repo"}-Migrated${timestamp}`;

  const buildTargetBranchName = (repoName: string, timestamp: string) =>
    `migration/${repoName || "repo"}-Migrated${timestamp}`;

  const buildLocalTargetFolderName = (repoName: string) =>
    `${repoName || "repo"}-Migrated`;

  const isLocalRepoRef = (value: string | null | undefined) => Boolean(value && value.startsWith("local://"));
  const buildLocalRepoRef = (value: string) => `local://${value.trim()}`;
  const extractLocalRepoPath = (value: string) => value.replace(/^local:\/\//, "");
  const getPathBasename = (value: string) => {
    const normalized = value.replace(/[\\/]+$/, "");
    const parts = normalized.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] || "local-project";
  };

  const parseRepositoryContext = (value: string | null | undefined) => {
    if (!value || value.startsWith("local://")) return null;

    const normalized = value.trim().replace(/\.git$/, "").replace(/\/+$/, "");
    if (/^[^/\s]+\/[^/\s]+$/.test(normalized)) {
      const [owner, repo] = normalized.split("/");
      return { platform: "github", host: "github.com", owner, repo };
    }

    try {
      const parsed = new URL(normalized);
      const pathParts = parsed.pathname.split("/").filter(Boolean);
      if (pathParts.length < 2) return null;

      const platform = parsed.hostname.includes("gitlab") ? "gitlab" : "github";
      return {
        platform,
        host: parsed.host,
        owner: pathParts[0],
        repo: pathParts[1],
      };
    } catch {
      return null;
    }
  };

  const [step, setStep] = useState(() => initialStep);
  const [maxVisitedIndicatorStep, setMaxVisitedIndicatorStep] = useState(
    Math.max(persistedFormState?.maxVisitedIndicatorStep ?? 1, getIndicatorStep(initialStep))
  );
  const [error, setError] = useState<string>("");
  const discoveryState = useDiscoveryState(persistedFormState, createDefaultMicroserviceAccordionState);
  const {
    repoAnalysis,
    setRepoAnalysis,
    setRepoFiles,
    currentPath,
    setCurrentPath,
    analysisLoading,
    setAnalysisLoading,
    analysisElapsedSeconds,
    setAnalysisElapsedSeconds,
    microserviceResult,
    setMicroserviceResult,
    microserviceLoading,
    setMicroserviceLoading,
    microserviceAccordionState,
    setMicroserviceAccordionState,
    setIsMicroserviceEligibilityCollapsed,
    setShowAllMicroserviceServices,
    setActiveScoreTooltip,
    microserviceExpandedSections,
    setMicroserviceExpandedSections,
    analysisStartedAtMs,
    setAnalysisStartedAtMs,
    analysisCompletedSeconds,
    setAnalysisCompletedSeconds,
    riskLevel,
    setRiskLevel,
    selectedFrameworks,
    setSelectedFrameworks,
    isJavaProject,
    setIsJavaProject,
    setSelectedFile,
    setFileContent,
    setEditedContent,
    setIsEditing,
    pathHistory,
    setPathHistory,
    setShowFileExplorer,
    isHighRiskProject,
    setIsHighRiskProject,
    highRiskConfirmed,
    setHighRiskConfirmed,
    suggestedJavaVersion,
    setSuggestedJavaVersion,
    detectedFrameworks,
    setDetectedFrameworks,
    setViewingFrameworkFile,
    setFrameworkFileLoading,
    repoPreviewInitialized,
    setRepoPreviewInitialized,
    microserviceAssessmentResolved,
    setMicroserviceAssessmentResolved,
    resetDiscoverySelectionState,
  } = discoveryState;
  const [conversionDecision, setConversionDecision] = useState<"yes" | "no" | null>(null);
  const [showFolderStructure, setShowFolderStructure] = useState(false);
  const strategyState = useStrategyState(persistedFormState, generateRepoTimestamp);
  const {
    targetRepoNamesByApproach,
    setTargetRepoNamesByApproach,
    targetRepoNameEditedByApproach,
    setTargetRepoNameEditedByApproach,
    targetRepoTimestamp,
    setTargetRepoTimestamp,
    targetVersions,
    setTargetVersions,
    selectedSourceVersion,
    setSelectedSourceVersion,
    selectedTargetVersion,
    setSelectedTargetVersion,
    selectedConversions,
    setSelectedConversions,
    targetVersionRequiredError,
    setTargetVersionRequiredError,
    setTargetRepoNameError,
    migrationApproach,
    setMigrationApproach,
    userSelectedVersion,
    setUserSelectedVersion,
    sourceVersionStatus,
    setSourceVersionStatus,
    updateSourceVersion,
    resetTargetRepoNaming,
    applyDetectedSourceVersion,
  } = strategyState;
  const modernizationState = useModernizationState(persistedFormState);
  const {
    runTests,
    setRunTests,
    useLLMTests,
    selectedLLMProvider,
    runSonar,
    setRunSonar,
    runFossa,
    setRunFossa,
    fixBusinessLogic,
  } = modernizationState;

  const resultExecState = useMigrationExecution();
  const {
    loading,
    setLoading,
    migrationTimerNow,
    setMigrationTimerNow,
    migrationJob,
    setMigrationJob,
    setMigrationDetailLoadedJobId,
    setMigrationLogs,
    fossaResult,
    setFossaResult,
    setFossaLoading,
    migrationPreview,
    setMigrationPreview,
    codeChanges,
    setCodeChanges,
    selectedDiffFile,
    setSelectedDiffFile,
    setShowCodeChanges,
    visibleReportDiffCount,
    setVisibleReportDiffCount,
    setReportDependencyPage,
    reportAccordionState,
    documentGenerationLoading,
    setDocumentGenerationLoading,
    documentPrefetchStatus,
    setDocumentPrefetchStatus,
    prefetchedBrdDocument,
    setPrefetchedBrdDocument,
    animationProgress,
    setAnimationProgress,
  } = resultExecState;
  const connectState = useRepositoryConnect({
    persistedIsPrivateRepo: persistedFormState?.isPrivateRepo,
    persistedPatToken: persistedFormState?.patToken,
    setRepoAnalysis,
    setRepoFiles,
    setStep,
    setError,
    resetRepositorySelectionState,
    buildLocalRepoRef,
    getPathBasename,
    isLocalRepoRef,
    loadZipSync,
  });
  const {
    repoUrl,
    setRepoUrl,
    selectedRepo,
    setSelectedRepo,
    githubUserLogin,
    isPrivateRepo,
    setIsPrivateRepo,
    patToken,
    setRepoAccessCheckLoading,
    setAccessTokenValidationState,
    setAccessTokenValidationMessage,
    urlValidation,
    showEnterpriseToken,
    currentToken,
    resetAccessTokenValidationState,
  } = connectState;
  const currentMigrationApproach =
    migrationApproach === "branch"
      ? "branch"
      : migrationApproach === "local"
        ? "local"
        : "fork";
  const targetRepoName = targetRepoNamesByApproach[currentMigrationApproach] ?? "";
  const sourceRepositoryContext = parseRepositoryContext(selectedRepo?.url || repoUrl);
  const targetRepositoryHost =
    currentMigrationApproach === "fork"
      ? DEFAULT_TARGET_GITHUB_HOST
      : sourceRepositoryContext?.host || DEFAULT_TARGET_GITHUB_HOST;
  const targetRepositoryOwner =
    currentMigrationApproach === "fork"
      ? DEFAULT_TARGET_GITHUB_OWNER
      : sourceRepositoryContext?.platform === "github" && githubUserLogin
        ? githubUserLogin
        : sourceRepositoryContext?.owner || githubUserLogin || "owner";
  const sourceRepositoryName =
    selectedRepo?.name || sourceRepositoryContext?.repo || repoUrl.split("/").pop()?.replace(".git", "") || "repo";

  const getAutoGeneratedTargetName = useCallback(
    (approach: MigrationApproachValue, repoName: string = sourceRepositoryName) =>
      approach === "branch"
        ? buildTargetBranchName(repoName, targetRepoTimestamp)
        : approach === "local"
          ? buildLocalTargetFolderName(repoName)
          : buildTargetRepoUrl(repoName, targetRepoTimestamp, targetRepositoryOwner, targetRepositoryHost),
    [sourceRepositoryName, targetRepoTimestamp, targetRepositoryOwner, targetRepositoryHost]
  );

  const setTargetRepoNameForApproach = (
    approach: MigrationApproachValue,
    value: string,
    edited: boolean
  ) => {
    setTargetRepoNamesByApproach((prev) => ({ ...prev, [approach]: value }));
    setTargetRepoNameEditedByApproach((prev) => ({ ...prev, [approach]: edited }));
  };

  const handleTargetRepoNameChange = (value: string) => {
    setTargetRepoNameError("");
    setTargetRepoNameForApproach(currentMigrationApproach, value, true);
  };
  const [versionRecommendation, setVersionRecommendation] = useState<JavaVersionRecommendationResponse | null>(null);
  const [versionRecommendationLoading, setVersionRecommendationLoading] = useState(false);
  const [versionRecommendationError, setVersionRecommendationError] = useState("");
  const [dependencyRiskFilter, setDependencyRiskFilter] = useState<DependencyRiskFilter>("all");

  // Functional test tool selection for Strategy page (multi-select)
  const [functionalTestToolMethod, setFunctionalTestToolMethod] = useState<string[]>(
    persistedFormState?.functionalTestToolMethod ?? []
  );

  const functionalTestingTools = useMemo(() => {
    const endpointCount = repoAnalysis?.api_endpoints?.length ?? 0;
    const hasRest = endpointCount > 0;
    const javaFileCount = repoAnalysis?.java_files?.length ?? 0;
    const depCount = repoAnalysis?.dependencies?.length ?? 0;
    const _hasTests = repoAnalysis?.has_tests ?? false;
    const hasSrcMain = repoAnalysis?.structure?.has_src_main ?? false;
    const hasSrcTest = repoAnalysis?.structure?.has_src_test ?? false;
    const hasBuildTool = Boolean(repoAnalysis?.build_tool) || repoAnalysis?.structure?.has_pom_xml || repoAnalysis?.structure?.has_build_gradle;

    const deps = repoAnalysis?.dependencies ?? [];
    const depArtifacts = deps.map(d => (d.artifact_id || "").toLowerCase());

    const hasSpringBoot = depArtifacts.some(a =>
      a.includes("spring-boot-starter-web") || a.includes("spring-webmvc") || a.includes("spring-boot-starter")
    );
    const hasSpringMvc = depArtifacts.some(a =>
      a.includes("spring-webmvc") || a.includes("spring-boot-starter-web") || a.includes("spring-mvc")
    );
    const hasSpringTest = depArtifacts.some(a =>
      a.includes("spring-boot-starter-test") || a.includes("spring-test")
    );
    const hasThymeleaf = depArtifacts.some(a => a.includes("thymeleaf"));
    const hasJsp = depArtifacts.some(a => a.includes("jsp") || a.includes("jstl") || a.includes("servlet"));

    const allFiles: string[] = ((repoAnalysis as any)?.all_files ?? []).map((f: any) =>
      (typeof f === "string" ? f : (f?.path || "")).toLowerCase()
    );

    const hasStaticAssets = allFiles.some(p =>
      p.includes("/static/") || p.includes("/public/") || p.includes("/resources/templates/") || p.includes("/webapp/")
    );
    const hasWebXml = allFiles.some(p => p.endsWith("web.xml"));
    const hasJspFiles = allFiles.some(p => p.endsWith(".jsp") || p.endsWith(".jspx"));
    const hasHtmlTemplates = allFiles.some(p => p.endsWith(".html") && (p.includes("/templates/") || p.includes("/webapp/")));
    const hasAngular = allFiles.some(p => p.endsWith("angular.json") || p.endsWith("angular-cli.json") || p.endsWith(".component.ts"));
    const hasReact = allFiles.some(p => p.endsWith("package.json")) && (allFiles.some(p => p.endsWith(".tsx")) || allFiles.some(p => p.endsWith(".jsx")));
    const hasVue = allFiles.some(p => p.endsWith(".vue")) || allFiles.some(p => p.endsWith("vue.config.js"));
    const hasModernJsFramework = hasAngular || hasReact || hasVue;
    const hasUI = hasStaticAssets || hasThymeleaf || hasJspFiles || hasHtmlTemplates || hasWebXml || hasModernJsFramework;

    const hasOpenApiFile = allFiles.some(p =>
      p.includes("openapi") || p.includes("swagger") || p.endsWith("api-docs.json") || p.endsWith("api-docs.yaml")
    );
    const hasSpringDoc = depArtifacts.some(a => a.includes("springdoc") || a.includes("springfox") || a.includes("swagger"));
    const _hasOpenApi = hasOpenApiFile || hasSpringDoc;

    // ── Playwright confidence ──
    let playwrightConf = 5;
    if (hasUI) {
      playwrightConf = 72;
      if (hasThymeleaf || hasHtmlTemplates) playwrightConf += 10;
      if (hasStaticAssets) playwrightConf += 6;
      if (hasJspFiles) playwrightConf += 4;
      if (hasAngular) playwrightConf += 12;
      if (hasReact) playwrightConf += 10;
      if (hasVue) playwrightConf += 10;
    } else if (hasSrcMain && hasJsp) {
      playwrightConf = 38;
    } else if (hasSrcMain) {
      playwrightConf = 12;
    }
    playwrightConf = Math.min(playwrightConf, 97);

    const uiFrameworks = [
      hasThymeleaf && "Thymeleaf templates",
      hasJspFiles && "JSP pages",
      hasHtmlTemplates && "HTML templates",
      hasStaticAssets && "static assets",
      hasAngular && "Angular",
      hasReact && "React",
      hasVue && "Vue",
    ].filter(Boolean).join(", ");
    const playwrightTag = playwrightConf >= 70 ? "Highly Recommended"
      : playwrightConf >= 35 ? "Potential Fit"
      : "Not Detected";
    const playwrightReason = playwrightConf >= 70
      ? `Highly Recommended: Detected ${uiFrameworks || "UI assets"} in project.`
      : playwrightConf >= 35
        ? "Potential Fit: Some web resources found but no strong UI framework detected."
        : "Not Detected: No web UI assets or templating engine found in this project.";

    // ── Rest Assured confidence ──
    let restAssuredConf = 5;
    if (hasRest) {
      restAssuredConf = 78;
      if (endpointCount >= 5) restAssuredConf += 8;
      if (endpointCount >= 10) restAssuredConf += 6;
      if (hasSpringBoot) restAssuredConf += 3;
    } else if (hasSpringBoot) {
      restAssuredConf = 52;
      if (hasSrcMain && javaFileCount > 10) restAssuredConf += 8;
    } else if (hasBuildTool && javaFileCount > 5) {
      restAssuredConf = 28;
    }
    restAssuredConf = Math.min(restAssuredConf, 97);

    const restAssuredTag = restAssuredConf >= 70 ? "Highly Recommended"
      : restAssuredConf >= 40 ? "Potential Fit"
      : "Low Match";
    const restAssuredReason = restAssuredConf >= 70
      ? `Highly Recommended: Found ${endpointCount} REST endpoint${endpointCount !== 1 ? "s" : ""} across project controllers.`
      : restAssuredConf >= 40
        ? "Potential Fit: Spring web dependencies detected but explicit endpoints not fully mapped."
        : "Low Match: No REST controllers or Spring web dependencies detected.";

    // ── Selenium confidence ──
    let seleniumConf = 3;
    if (hasUI) {
      seleniumConf = 32;
      if (hasJspFiles || hasWebXml) seleniumConf += 12;
      if (!hasThymeleaf && !hasHtmlTemplates) seleniumConf += 6;
    } else if (hasJsp) {
      seleniumConf = 22;
    }
    seleniumConf = Math.min(seleniumConf, 55);

    const seleniumReason = seleniumConf >= 30
      ? "Legacy UI detected — Selenium can test it, but Playwright is preferred for modern stacks."
      : "Not Recommended: No significant UI layer detected for browser-based testing.";

    // ── MockMvc confidence ──
    let mockMvcConf = 3;
    if (hasSpringMvc && hasSpringTest) {
      mockMvcConf = 82;
      if (hasRest) mockMvcConf += 6;
      if (hasSrcTest) mockMvcConf += 5;
    } else if (hasSpringMvc || hasSpringBoot) {
      mockMvcConf = 58;
      if (hasRest) mockMvcConf += 8;
      if (hasSrcTest) mockMvcConf += 5;
    } else if (hasBuildTool && depCount > 3) {
      mockMvcConf = 14;
    }
    mockMvcConf = Math.min(mockMvcConf, 97);

    const mockMvcTag = mockMvcConf >= 70 ? "Highly Recommended"
      : mockMvcConf >= 40 ? "Integration Ready"
      : "Low Match";
    const mockMvcReason = mockMvcConf >= 70
      ? "Highly Recommended: Spring MVC and spring-test detected — MockMvc is ideal for controller-level testing."
      : mockMvcConf >= 40
        ? "Integration Ready: Spring Boot detected — MockMvc can test web layer in isolation."
        : "Low Match: Project does not appear to use Spring MVC.";

    // ── Schemathesis confidence ──
    let schemathesisConf = 3;
    if (hasOpenApiFile) {
      schemathesisConf = 88;
      if (hasRest) schemathesisConf += 6;
    } else if (hasSpringDoc) {
      schemathesisConf = 68;
      if (hasRest) schemathesisConf += 8;
    } else if (hasRest) {
      schemathesisConf = 28;
    }
    schemathesisConf = Math.min(schemathesisConf, 97);

    const schemathesisTag = schemathesisConf >= 70 ? "Highly Recommended"
      : schemathesisConf >= 40 ? "Spec Available"
      : hasRest ? "Spec Not Found" : "Not Applicable";
    const schemathesisReason = schemathesisConf >= 70
      ? "Highly Recommended: OpenAPI/Swagger specification found in the repository."
      : schemathesisConf >= 40
        ? "Spec Available: Springdoc/Springfox dependency detected — API spec likely auto-generated at runtime."
        : hasRest
          ? "Spec Not Found: REST endpoints exist but no OpenAPI specification file detected."
          : "Not Applicable: No REST API layer or OpenAPI specification detected.";

    const isSpring = hasSpringMvc || hasSpringBoot;

    const tools = [];

    // UI tools: only when UI assets detected
    if (hasUI) {
      tools.push({
        id: "PLAYWRIGHT",
        name: "Playwright (UI)",
        description: "Modern web testing for fast, reliable end-to-end tests across browsers.",
        confidence: playwrightConf,
        reason: playwrightReason,
        color: "#22c55e",
        tag: playwrightTag,
      });
      tools.push({
        id: "SELENIUM",
        name: "Selenium (Legacy UI)",
        description: "Widely used but may require significant configuration for your specific stack.",
        confidence: seleniumConf,
        reason: seleniumReason,
        color: "#ef4444",
        tag: "Legacy Support",
      });
    }

    // Spring framework projects get MockMvc
    if (isSpring) {
      tools.push({
        id: "MOCK_MVC",
        name: "MockMvc (Spring MVC)",
        description: "Ideal for testing Spring MVC applications in isolation.",
        confidence: mockMvcConf,
        reason: mockMvcReason,
        color: "#3b82f6",
        tag: mockMvcTag,
      });
    }

    // Non-Spring REST endpoints get Rest Assured
    if (hasRest && !isSpring) {
      tools.push({
        id: "REST_ASSURED",
        name: "Rest Assured (API)",
        description: "Strong for API testing, but doesn't cover UI interactions.",
        confidence: restAssuredConf,
        reason: restAssuredReason,
        color: "#f59e0b",
        tag: restAssuredTag,
      });
    }

    // If nothing matched, show Rest Assured as a fallback
    if (tools.length === 0) {
      tools.push({
        id: "REST_ASSURED",
        name: "Rest Assured (API)",
        description: "Strong for API testing, but doesn't cover UI interactions.",
        confidence: restAssuredConf,
        reason: restAssuredReason,
        color: "#f59e0b",
        tag: restAssuredTag,
      });
    }

    return tools;
  }, [repoAnalysis]);


  const hasUI = useMemo(() => {
    const allFiles: string[] = ((repoAnalysis as any)?.all_files ?? []).map((f: any) =>
      (typeof f === "string" ? f : (f?.path || "")).toLowerCase()
    );
    const deps = repoAnalysis?.dependencies ?? [];
    const depArtifacts = deps.map(d => (d.artifact_id || "").toLowerCase());
    const hasStaticAssets = allFiles.some(p =>
      p.includes("/static/") || p.includes("/public/") || p.includes("/resources/templates/") || p.includes("/webapp/")
    );
    const hasWebXml = allFiles.some(p => p.endsWith("web.xml"));
    const hasJspFiles = allFiles.some(p => p.endsWith(".jsp") || p.endsWith(".jspx"));
    const hasHtmlTemplates = allFiles.some(p => p.endsWith(".html") && (p.includes("/templates/") || p.includes("/webapp/")));
    const hasThymeleaf = depArtifacts.some(a => a.includes("thymeleaf"));
    const hasAngular = allFiles.some(p => p.endsWith("angular.json") || p.endsWith("angular-cli.json") || p.endsWith(".component.ts"));
    const hasReact = allFiles.some(p => p.endsWith("package.json")) && (allFiles.some(p => p.endsWith(".tsx")) || allFiles.some(p => p.endsWith(".jsx")));
    const hasVue = allFiles.some(p => p.endsWith(".vue")) || allFiles.some(p => p.endsWith("vue.config.js"));
    const hasModernJsFramework = hasAngular || hasReact || hasVue;
    return hasStaticAssets || hasThymeleaf || hasJspFiles || hasHtmlTemplates || hasWebXml || hasModernJsFramework;
  }, [repoAnalysis]);

  const localApiTestCases = useMemo(() => {
    const eps = (repoAnalysis as any)?.api_endpoints || [];
    return eps.slice(0, 50).map((ep: any, idx: number) => {
      const method = (ep.method || "GET").toUpperCase();
      const path = ep.path || "/";
      const parts = path.split("/").filter((p: string) => p && !p.startsWith("{") && !p.startsWith(":"));
      const resource = parts[parts.length - 1] || "resource";
      const subject = resource.replace(/_/g, " ").replace(/-/g, " ").replace(/\b\w/g, (l: string) => l.toUpperCase());
      const hasIdParam = path.toLowerCase().includes("id") || path.includes("{") || path.includes(":");
      const status = method === "POST" ? 201 : (method === "DELETE" ? 204 : 200);
      let scenario = "";
      if (method === "GET") {
        scenario = hasIdParam
          ? `The application asks the server for details about a specific ${subject} using its reference number. The server finds the matching record and returns its information.`
          : `The application asks the server for the full list of ${subject} entries. The server looks up the data and sends back the list.`;
      } else if (method === "POST") {
        scenario = `The application sends new ${subject} information to create a record. The server checks the information, saves it, and sends back a confirmation.`;
      } else if (method === "PUT") {
        scenario = `The application sends updated ${subject} information to replace the existing record. The server finds the record, updates it, and saves the changes.`;
      } else if (method === "PATCH") {
        scenario = `The application sends partial updates for a ${subject} record. Only the fields that need changing are sent; everything else stays the same.`;
      } else if (method === "DELETE") {
        scenario = `The application asks the server to remove a ${subject} record. The server finds the record, deletes it, and cleans up any related data.`;
      } else {
        scenario = `The application performs an operation on ${subject}.`;
      }
      return {
        id: idx + 1, method, path,
        controller: ep.controller || (ep.source_file ? ep.source_file.replace(".java", "").split("/").pop() || "-" : "-"),
        scenario,
        expectedStatus: status,
      };
    });
  }, [repoAnalysis]);

  const _recommendedTool = useMemo(() => {
    if (!functionalTestingTools || functionalTestingTools.length === 0) return "REST_ASSURED";
    
    // Find the tool with the highest confidence score
    const bestTool = [...functionalTestingTools].sort((a, b) => b.confidence - a.confidence)[0];
    return bestTool?.id || "REST_ASSURED";
  }, [functionalTestingTools]);

  const renderConfidenceCircle = (percentage: number, color: string) => {
    const radius = 36;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percentage / 100) * circumference;
    const percentColor = percentage >= 80 ? "#16a34a" : percentage >= 60 ? "#2563eb" : percentage >= 40 ? "#d97706" : "#dc2626";

    return (
      <div style={{ position: "relative", width: 90, height: 90, margin: "0 auto" }}>
        <svg width="90" height="90" viewBox="0 0 100 100">
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="transparent"
            stroke="#f1f5f9"
            strokeWidth="8"
          />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="transparent"
            stroke={color}
            strokeWidth="8"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform="rotate(-90 50 50)"
            style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1), stroke 0.4s ease" }}
          />
        </svg>
        <div style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          textAlign: "center"
        }}>
          <div style={{ fontWeight: 800, fontSize: 16, color: percentColor, transition: "color 0.3s ease" }}>{percentage}%</div>
          <div style={{ fontSize: 9, color: "#64748b", fontWeight: 600, marginTop: -2 }}>Confidence</div>
        </div>
      </div>
    );
  };
  const currentIndicatorStep = getIndicatorStep(step);

  useEffect(() => {
    setDependencyRiskFilter("all");
  }, [repoAnalysis?.dependencies]);

  const migrationApproachOptions: Array<{
    value: MigrationApproachValue;
    label: string;
    desc: string;
    tooltip: string;
    icon: React.ReactNode;
    color: string;
  }> = [
    {
      value: "fork",
      label: "Create New Repository",
      desc: "Push migrated code to a new repository under the Javaapex GitHub owner",
      tooltip: "Creates an entirely new repository with the migrated code under the Javaapex GitHub owner by default.",
      icon: <FaRocket />,
      color: "#f59e0b",
    },
    {
      value: "branch",
      label: "Existing Repository (New Branch)",
      desc: "Push migrated code to a new branch in the source repository",
      tooltip: "Keeps the existing repository and publishes the migrated code on a separate branch for review and merge.",
      icon: <FaProjectDiagram />,
      color: "#22c55e",
    },
    {
      value: "local",
      label: "Store In Local Folder",
      desc: "Save migrated code into a local folder on this machine",
      tooltip: "Creates a local folder such as {repo-name}-Migrated under the backend migration workspace instead of pushing to GitHub.",
      icon: <FaFolderOpen />,
      color: "#2563eb",
    },
  ];

  const documentPrefetchKeyRef = useRef<string>("");
  const documentPrefetchPromiseRef = useRef<Promise<PrefetchedBrdDocument | null> | null>(null);
  const migrationPollingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const migrationPollingInFlightRef = useRef(false);
  const migrationPollingErrorCountRef = useRef(0);
  const fossaLoadedJobIdRef = useRef<string | null>(null);
  const detailFetchGenRef = useRef(0);

  const toggleMicroserviceAccordion = (section: MicroserviceAccordionKey) => {
    setMicroserviceAccordionState((current) => ({
      ...current,
      [section]: !current[section],
    }));
  };

  const _uniqueTextItems = (items: string[] = []) =>
    Array.from(
      new Set(
        items
          .map((item) => item?.trim())
          .filter((item): item is string => Boolean(item))
      )
    );

  const toggleMicroserviceExpandedSection = (sectionKey: string) => {
    setMicroserviceExpandedSections((current) => ({
      ...current,
      [sectionKey]: !current[sectionKey],
    }));
  };

  const _renderMicroserviceEvidenceBlock = ({
    sectionKey,
    title,
    items,
    emptyText,
    previewCount = 3,
    accentColor = "#334155",
    background = "#ffffff",
    borderColor = "#e2e8f0",
    subtitle,
  }: {
    sectionKey: string;
    title: string;
    items: string[];
    emptyText: string;
    previewCount?: number;
    accentColor?: string;
    background?: string;
    borderColor?: string;
    subtitle?: string;
  }) => {
    const isExpanded = microserviceExpandedSections[sectionKey];
    const visibleItems = isExpanded ? items : items.slice(0, previewCount);

    return (
      <div style={{ ...styles.microserviceInsightCard, background, borderColor }}>
        <div style={{ ...styles.microserviceInsightTitle, color: accentColor }}>{title}</div>
        {subtitle && <div style={styles.microserviceEvidenceSubtitle}>{subtitle}</div>}
        {items.length > 0 ? (
          <>
            {visibleItems.map((item, index) => (
              <div key={`${sectionKey}-${index}`} style={{ ...styles.microserviceBulletItem, color: accentColor }}>
                - {item}
              </div>
            ))}
            {items.length > previewCount && (
              <div style={styles.microserviceEvidenceFooter}>
                <button
                  type="button"
                  style={styles.microserviceEvidenceToggle}
                  onClick={() => toggleMicroserviceExpandedSection(sectionKey)}
                >
                  {isExpanded ? "View less" : `View more (${items.length - previewCount} more)`}
                </button>
              </div>
            )}
          </>
        ) : (
          <div style={{ ...styles.microservicePreviewEmpty, color: accentColor }}>{emptyText}</div>
        )}
      </div>
    );
  };

  const getMicroserviceAccordionTone = (
    tone: "slate" | "green" | "red" | "amber" | "blue" | "violet" = "slate"
  ) => {
    switch (tone) {
      case "green":
        return { bg: "#f0fdf4", border: "#bbf7d0", accent: "#166534", muted: "#15803d" };
      case "red":
        return { bg: "#fef2f2", border: "#fecaca", accent: "#991b1b", muted: "#b91c1c" };
      case "amber":
        return { bg: "#fff7ed", border: "#fdba74", accent: "#9a3412", muted: "#c2410c" };
      case "blue":
        return { bg: "#eff6ff", border: "#bfdbfe", accent: "#1d4ed8", muted: "#2563eb" };
      case "violet":
        return { bg: "#faf5ff", border: "#d8b4fe", accent: "#6b21a8", muted: "#7e22ce" };
      default:
        return { bg: "#f8fafc", border: "#e2e8f0", accent: "#0f172a", muted: "#475569" };
    }
  };

  const renderMicroserviceAccordion = ({
    section,
    title,
    subtitle,
    meta,
    tone = "slate",
    children,
  }: {
    section: MicroserviceAccordionKey;
    title: string;
    subtitle: string;
    meta?: string;
    tone?: "slate" | "green" | "red" | "amber" | "blue" | "violet";
    children: React.ReactNode;
  }) => {
    const palette = getMicroserviceAccordionTone(tone);
    const isOpen = microserviceAccordionState[section];

    return (
      <div
        style={{
          ...styles.microserviceAccordionCard,
          background: palette.bg,
          borderColor: palette.border,
        }}
      >
        <button
          type="button"
          style={styles.microserviceAccordionToggle}
          onClick={() => toggleMicroserviceAccordion(section)}
        >
          <div style={styles.microserviceAccordionContentBlock}>
            <div style={{ ...styles.microserviceAccordionTitle, color: palette.accent }}>{title}</div>
            <div style={{ ...styles.microserviceAccordionSubtitle, color: palette.muted }}>{subtitle}</div>
          </div>
          <div style={styles.microserviceAccordionMeta}>
            {meta && (
              <span
                style={{
                  ...styles.microserviceAccordionMetaPill,
                  color: palette.accent,
                  borderColor: palette.border,
                  background: "#ffffff",
                }}
              >
                {meta}
              </span>
            )}
            <span style={{ ...styles.microserviceAccordionChevron, color: palette.accent }}>
              {isOpen ? "Hide" : "Show"}
            </span>
          </div>
        </button>
        {isOpen && <div style={styles.microserviceAccordionBody}>{children}</div>}
      </div>
    );
  };


  const getDocumentRepositoryUrl = () =>
    selectedRepo?.url || repoUrl || migrationJob?.source_repo || "";
  const technicalDocumentFallbackRepoName = selectedRepo?.name || repoAnalysis?.name || "repository";

  const resolveGeneratedDocumentAsset = async (result: GithubDocumentResponse) => {
    if (result.url) {
      try {
        const response = await fetch(result.url);

        if (response.ok) {
          const documentBlob = await response.blob();

          const htmlFromUrl = await documentBlob.text();
          if (htmlFromUrl.trim()) {
            return { html: htmlFromUrl } as const;
          }
        }
      } catch {
        // Fall back to inline HTML when the backend download URL is unavailable.
      }
    }

    if (result.html?.trim()) {
      return { html: result.html } as const;
    }

    throw new Error("Generated BRD document did not include HTML content or a download URL.");
  };

  const handleGenerateBrdDocument = async () => {
    const repoReference = getDocumentRepositoryUrl();

    if (!repoReference) {
      setError("Repository URL is required before generating the BRD document.");
      return;
    }

    setDocumentGenerationLoading("brd");
    setError("");

    try {
      const prefetchedAssetReady = prefetchedBrdDocument && documentPrefetchStatus === "ready";
      const activePrefetchPromise =
        !prefetchedAssetReady && documentPrefetchStatus === "loading"
          ? documentPrefetchPromiseRef.current
          : null;
      const generatedAsset = prefetchedAssetReady
        ? prefetchedBrdDocument
        : await (async () => {
            if (activePrefetchPromise) {
              const prefetchedAsset = await activePrefetchPromise;
              if (prefetchedAsset) {
                return prefetchedAsset;
              }
            }

            const result = isLocalRepoRef(repoReference)
              ? await generateLocalProjectDocument({
                  repo_url: repoReference,
                  repository_url: repoReference,
                  source_repo_url: repoReference,
                  source_repo: selectedRepo?.name || repoAnalysis?.name || repoReference,
                  target_repo: migrationJob?.target_repo || null,
                  source_java_version: repoAnalysis?.java_version || selectedSourceVersion || undefined,
                  target_java_version: effectiveTargetVersion || undefined,
                  document_type: "BRD",
                  analysis: repoAnalysis as unknown as Record<string, unknown>,
                })
              : await generateGithubDocument("brd", {
                  repo_url: repoReference,
                  repository_url: repoReference,
                  source_repo_url: repoReference,
                  token: currentToken || undefined,
                  github_token: currentToken || undefined,
                  job_id: migrationJob?.job_id || undefined,
                  migration_job_id: migrationJob?.job_id || undefined,
                  source_repo: migrationJob?.source_repo || repoReference,
                  target_repo: migrationJob?.target_repo || null,
                  source_java_version: repoAnalysis?.java_version || selectedSourceVersion || undefined,
                  target_java_version: effectiveTargetVersion || undefined,
                  document_type: "BRD",
                });

            const resolvedAsset = await resolveGeneratedDocumentAsset(result);
            const filename = buildHtmlFilename(result.filename, technicalDocumentFallbackRepoName);

            if (resolvedAsset.html) {
              return {
                filename,
                html: resolvedAsset.html,
              } satisfies PrefetchedBrdDocument;
            }

            throw new Error("Generated BRD document did not include HTML content or a download URL.");
          })();

      if (!prefetchedAssetReady) {
        setPrefetchedBrdDocument(generatedAsset);
        setDocumentPrefetchStatus("ready");
      }

      if (generatedAsset.html) {
        await downloadHtmlDocument(generatedAsset.html, generatedAsset.filename);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate BRD document");
    } finally {
      setDocumentGenerationLoading(null);
    }
  };

  const detectJavaVersionFromPomContent = (pomContent: string): string | null => {
    const normalize = (version: string) => {
      const trimmed = version.trim();
      return trimmed.startsWith("1.") ? trimmed.replace("1.", "") : trimmed;
    };

    const lookupProperty = (propertyName: string) => {
      const escapedProperty = propertyName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const match = pomContent.match(new RegExp(`<${escapedProperty}>\\s*(\\d+(?:\\.\\d+)?)\\s*</${escapedProperty}>`));
      return match ? normalize(match[1]) : null;
    };

    const directPatterns = [
      /<maven\.compiler\.source>\s*(\d+(?:\.\d+)?)\s*<\/maven\.compiler\.source>/,
      /<maven\.compiler\.target>\s*(\d+(?:\.\d+)?)\s*<\/maven\.compiler\.target>/,
      /<maven\.compiler\.release>\s*(\d+(?:\.\d+)?)\s*<\/maven\.compiler\.release>/,
      /<java\.version>\s*(\d+(?:\.\d+)?)\s*<\/java\.version>/,
      /<javaVersion>\s*(\d+(?:\.\d+)?)\s*<\/javaVersion>/,
      /<source>\s*(\d+(?:\.\d+)?)\s*<\/source>/,
    ];

    for (const pattern of directPatterns) {
      const match = pomContent.match(pattern);
      if (match) return normalize(match[1]);
    }

    const propertyPatterns = [
      /<maven\.compiler\.source>\s*\$\{([^}]+)\}\s*<\/maven\.compiler\.source>/,
      /<maven\.compiler\.target>\s*\$\{([^}]+)\}\s*<\/maven\.compiler\.target>/,
      /<maven\.compiler\.release>\s*\$\{([^}]+)\}\s*<\/maven\.compiler\.release>/,
      /<source>\s*\$\{([^}]+)\}\s*<\/source>/,
    ];

    for (const pattern of propertyPatterns) {
      const match = pomContent.match(pattern);
      if (!match) continue;
      const resolved = lookupProperty(match[1]);
      if (resolved) return resolved;
    }

    return null;
  };

  const handleCheckMicroserviceEligibility = useCallback(async () => {
    if (!repoAnalysis || !selectedRepo?.url) return;
    setMicroserviceLoading(true);
    setMicroserviceAssessmentResolved(false);
    try {
      setMicroserviceResult(null);
      setMicroserviceAccordionState(createDefaultMicroserviceAccordionState());
      setIsMicroserviceEligibilityCollapsed(false);
      setShowAllMicroserviceServices(false);
      setActiveScoreTooltip(null);
      setMicroserviceExpandedSections({});
      const result = isLocalRepoRef(selectedRepo.url)
        ? await getLocalProjectMicroserviceEligibility(extractLocalRepoPath(selectedRepo.url), repoAnalysis)
        : await getMicroserviceEligibility(selectedRepo.url, currentToken, repoAnalysis);
      setMicroserviceResult(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("Failed to fetch microservice eligibility", message);
      setError("Unable to determine microservice eligibility from backend. Please try again.");
    } finally {
      setMicroserviceAssessmentResolved(true);
      setMicroserviceLoading(false);
    }
  }, [
    currentToken,
    repoAnalysis,
    selectedRepo?.url,
    setActiveScoreTooltip,
    setIsMicroserviceEligibilityCollapsed,
    setMicroserviceAccordionState,
    setMicroserviceAssessmentResolved,
    setMicroserviceExpandedSections,
    setMicroserviceLoading,
    setMicroserviceResult,
    setShowAllMicroserviceServices,
  ]);

  const handleDownloadMicroserviceReport = async () => {
    if (!microserviceResult) return;
    const JsPdf = await loadJsPdf();
    const pdf = new JsPdf({
      orientation: "portrait",
      unit: "pt",
      format: "a4",
    });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const marginX = 42;
    const topMargin = 44;
    const bottomMargin = 44;
    const contentWidth = pageWidth - marginX * 2;
    const fileSafeProjectName = (microserviceResult.projectName || "microservice-readiness-report")
      .replace(/[^a-z0-9-_]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase();
    const filename = `${fileSafeProjectName || "microservice-readiness-report"}-assessment.pdf`;

    let cursorY = topMargin;

    const ensureSpace = (requiredHeight: number) => {
      if (cursorY + requiredHeight <= pageHeight - bottomMargin) return;
      pdf.addPage();
      cursorY = topMargin;
    };

    const addParagraph = (
      text: string,
      {
        fontSize = 10,
        color = "#334155",
        indent = 0,
        gapAfter = 10,
        bold = false,
      }: {
        fontSize?: number;
        color?: string;
        indent?: number;
        gapAfter?: number;
        bold?: boolean;
      } = {}
    ) => {
      const lines = pdf.splitTextToSize(text || "-", contentWidth - indent);
      const lineHeight = fontSize + 4;
      ensureSpace(lines.length * lineHeight + gapAfter);
      pdf.setFont("helvetica", bold ? "bold" : "normal");
      pdf.setFontSize(fontSize);
      pdf.setTextColor(color);
      pdf.text(lines, marginX + indent, cursorY);
      cursorY += lines.length * lineHeight + gapAfter;
    };

    const addSectionHeading = (title: string) => {
      ensureSpace(28);
      pdf.setDrawColor(226, 232, 240);
      pdf.setLineWidth(1);
      if (cursorY > topMargin) {
        pdf.line(marginX, cursorY - 8, pageWidth - marginX, cursorY - 8);
      }
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(13);
      pdf.setTextColor("#0f172a");
      pdf.text(title, marginX, cursorY + 8);
      cursorY += 24;
    };

    const addBulletList = (items: string[], emptyText: string) => {
      if (!items.length) {
        addParagraph(emptyText, { color: "#64748b", gapAfter: 12 });
        return;
      }
      items.forEach((item) => addParagraph(`- ${item}`, { indent: 4, gapAfter: 6 }));
      cursorY += 2;
    };

    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(18);
    pdf.setTextColor("#0f172a");
    pdf.text("Microservice Readiness Assessment", marginX, cursorY);
    cursorY += 24;

    addParagraph(`Project: ${microserviceResult.projectName}`, { fontSize: 12, bold: true, color: "#1e293b", gapAfter: 6 });
    addParagraph(
      `Score: ${microserviceResult.score}/100   |   Eligibility: ${microserviceResult.eligibility}   |   Recommended Architecture: ${microserviceResult.recommendedArchitecture}`,
      { fontSize: 10, color: "#475569", gapAfter: 6 }
    );
    addParagraph(
      `Generated: ${microserviceResult.reportGeneratedAt ? new Date(microserviceResult.reportGeneratedAt).toLocaleString() : new Date().toLocaleString()}`,
      { fontSize: 9, color: "#64748b", gapAfter: 16 }
    );

    addSectionHeading("Assessment Summary");
    addParagraph(microserviceResult.summary, { fontSize: 10, color: "#334155", gapAfter: 14 });

    addSectionHeading("Score Breakdown");
    (microserviceResult.scoreBreakdown || []).forEach((metric) => {
      addParagraph(`${metric.name} - ${metric.score}% (${metric.weight}% weight)`, { bold: true, color: "#1e293b", gapAfter: 4 });
      addParagraph(metric.summary, { color: "#475569", gapAfter: 8, indent: 8 });
    });

    addSectionHeading("Strengths");
    addBulletList(microserviceResult.strengths || [], "No major strengths were highlighted.");

    addSectionHeading("Risks");
    addBulletList(microserviceResult.risks || [], "No major risks were highlighted.");

    addSectionHeading("Suggested Service Boundaries");
    if ((microserviceResult.serviceCandidates || []).length === 0) {
      addParagraph("No clear service candidates were identified.", { color: "#64748b", gapAfter: 12 });
    } else {
      microserviceResult.serviceCandidates.forEach((candidate, index) => {
        addParagraph(`${index + 1}. ${candidate.name}`, { bold: true, color: "#1d4ed8", gapAfter: 4 });
        if (candidate.packages?.length) {
          addParagraph(`Packages: ${candidate.packages.join(", ")}`, { color: "#475569", indent: 10, gapAfter: 4 });
        }
        if (candidate.evidence?.length) {
          candidate.evidence.forEach((item) => addParagraph(`- ${item}`, { indent: 16, gapAfter: 4 }));
        }
        if (candidate.scaling_signals?.length) {
          addParagraph(`Scaling signals: ${candidate.scaling_signals.join(", ")}`, { color: "#0f766e", indent: 10, gapAfter: 4 });
        }
        if (candidate.external_integrations?.length) {
          addParagraph(`External integrations: ${candidate.external_integrations.join(", ")}`, { color: "#7c2d12", indent: 10, gapAfter: 4 });
        }
        if (candidate.transactional) {
          addParagraph("Transactional boundary detected.", { color: "#92400e", indent: 10, gapAfter: 6 });
        }
        cursorY += 2;
      });
    }

    addSectionHeading("Coupling Issues");
    addBulletList(microserviceResult.couplingIssues || [], "No major coupling issues detected.");

    addSectionHeading("Database Concerns");
    addBulletList(microserviceResult.databaseConcerns || [], "No major database boundary concerns detected.");

    addSectionHeading("Scaling Candidates");
    addBulletList(microserviceResult.scalingCandidates || [], "No clear independent scaling targets were highlighted.");

    addSectionHeading("Recommended Migration Strategy");
    addBulletList(microserviceResult.recommendedMigrationStrategy || [], "No migration strategy guidance available.");

    addSectionHeading("Architectural Observations");
    addBulletList(
      [...(microserviceResult.observations || []), ...(microserviceResult.architecturalObservations || [])].slice(0, 20),
      "No additional architectural observations were recorded."
    );

    if (microserviceResult.detailedEligibilityReport) {
      addSectionHeading("Detailed Eligibility Report");
      const detailSections: Array<[string, string[]]> = [
        ["Project structure", microserviceResult.detailedEligibilityReport.project_structure || []],
        ["Package structure", microserviceResult.detailedEligibilityReport.package_structure || []],
        ["Module boundaries", microserviceResult.detailedEligibilityReport.module_boundaries || []],
        ["Dependency coupling", microserviceResult.detailedEligibilityReport.dependency_coupling || []],
        ["Database access patterns", microserviceResult.detailedEligibilityReport.database_access_patterns || []],
        ["Communication analysis", microserviceResult.detailedEligibilityReport.communication_analysis || []],
        ["Deployment independence", microserviceResult.detailedEligibilityReport.deployment_independence || []],
        ["Scalability indicators", microserviceResult.detailedEligibilityReport.scalability_indicators || []],
      ];
      detailSections.forEach(([title, items]) => {
        addParagraph(title, { bold: true, color: "#0f172a", gapAfter: 4 });
        addBulletList(items, "No additional findings.");
      });
    }

    pdf.save(filename);
  };

  useEffect(() => {
    if (repoAnalysis && selectedRepo?.url && !microserviceAssessmentResolved && !microserviceLoading) {
      void handleCheckMicroserviceEligibility();
    }
  }, [repoAnalysis, selectedRepo?.url, microserviceAssessmentResolved, microserviceLoading, handleCheckMicroserviceEligibility]);

  const parseJavaVersion = (version: string) => {
    const parsed = parseInt(version, 10);
    return Number.isNaN(parsed) ? null : parsed;
  };

  const shouldHideGeneratedDiffPath = (filePath: string) => {
    const normalized = (filePath || "").replace(/\\/g, "/").toLowerCase();
    return [
      "/.javaapex-cache/",
      "/.scannerwork/",
      "/node_modules/",
      "/target/",
      "/build/",
      "/out/",
      "/dist/",
      "/.gradle/",
    ].some((segment) => normalized.includes(segment)) || normalized.startsWith(".javaapex-cache/") || normalized.startsWith(".scannerwork/");
  };

  const buildCodeChangesFromPreviewDiffs = (fileDiffs: PreviewFileDiff[]): CodeChangeEntry[] => {
    return fileDiffs.flatMap((fileDiff) => {
      const diffLinesRaw = fileDiff.diff.split(/\r?\n/);
      const parsedDiffLines: CodeChangeEntry["diffLines"] = [];
      let oldLineNumber = 0;
      let newLineNumber = 0;
      const fromLine = diffLinesRaw.find((line) => line.startsWith("--- "));
      const toLine = diffLinesRaw.find((line) => line.startsWith("+++ "));

      const changeType: CodeChangeEntry["changeType"] =
        diffLinesRaw.some((line) => line.startsWith("new file mode")) || fromLine?.includes("/dev/null")
          ? "added"
          : diffLinesRaw.some((line) => line.startsWith("deleted file mode")) || toLine?.includes("/dev/null")
            ? "deleted"
            : "modified";

      diffLinesRaw.forEach((line) => {
        if (
          !line ||
          line.startsWith("diff --git") ||
          line.startsWith("index ") ||
          line.startsWith("new file mode") ||
          line.startsWith("deleted file mode") ||
          line.startsWith("rename from ") ||
          line.startsWith("rename to ") ||
          line.startsWith("similarity index ") ||
          line.startsWith("---") ||
          line.startsWith("+++")
        ) {
          return;
        }

        if (line.startsWith("@@")) {
          const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
          parsedDiffLines.push({
            type: "hunk",
            oldLineNumber: null,
            newLineNumber: null,
            content: line,
          });
          if (match) {
            oldLineNumber = Number(match[1]);
            newLineNumber = Number(match[2]);
          }
          return;
        }

        if (line.startsWith("+")) {
          parsedDiffLines.push({
            type: "add",
            oldLineNumber: null,
            newLineNumber,
            content: line.slice(1),
          });
          newLineNumber += 1;
          return;
        }

        if (line.startsWith("-")) {
          parsedDiffLines.push({
            type: "remove",
            oldLineNumber,
            newLineNumber: null,
            content: line.slice(1),
          });
          oldLineNumber += 1;
          return;
        }

        const content = line.startsWith(" ") ? line.slice(1) : line;
        parsedDiffLines.push({
          type: "context",
          oldLineNumber,
          newLineNumber,
          content,
        });
        oldLineNumber += 1;
        newLineNumber += 1;
      });

      const additions = diffLinesRaw.filter((line) => line.startsWith("+") && !line.startsWith("+++")).length;
      const deletions = diffLinesRaw.filter((line) => line.startsWith("-") && !line.startsWith("---")).length;
      const normalizedPath =
        fileDiff.file_path ||
        (toLine && !toLine.includes("/dev/null")
          ? toLine.replace(/^\+\+\+\s+b\//, "")
          : fromLine?.replace(/^---\s+a\//, "")) ||
        "unknown-file";

      if (shouldHideGeneratedDiffPath(normalizedPath)) {
        return [];
      }

      return [{
        fileName: normalizedPath.split("/").pop() || normalizedPath,
        filePath: normalizedPath,
        changeType,
        additions,
        deletions,
        oldContent: "",
        newContent: "",
        diffLines: parsedDiffLines,
      }];
    });
  };

  /*
  const renderCodeChangesViewer = ({
    changes,
    title,
    emptyMessage,
    maxHeight = 420,
    collapsible = false,
  }: {
    changes: CodeChangeEntry[];
    title: string;
    emptyMessage: string;
    maxHeight?: number;
    collapsible?: boolean;
  }) => {
    const isExpanded = collapsible ? showCodeChanges : true;
    const totalAdditions = changes.reduce((sum, change) => sum + change.additions, 0);
    const totalDeletions = changes.reduce((sum, change) => sum + change.deletions, 0);

    const renderLineNumber = (value: number | null) => (value === null ? "" : value);

    return (
      <div
        style={{
          border: "1px solid #d0d7de",
          borderRadius: 8,
          overflow: "hidden",
          backgroundColor: "#fff",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            padding: "12px 16px",
            backgroundColor: "#f6f8fa",
            borderBottom: "1px solid #d0d7de",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
            <span style={{ fontWeight: 600, color: "#1e293b" }}>{title}</span>
            <span style={{ color: "#334155", fontSize: 13 }}>{changes.length} files changed</span>
            <span style={{ color: "#16a34a", fontSize: 13 }}>+{totalAdditions}</span>
            <span style={{ color: "#dc2626", fontSize: 13 }}>-{totalDeletions}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                fontSize: 11,
                padding: "4px 10px",
                backgroundColor: "#ddf4ff",
                borderRadius: 999,
                color: "#0969da",
              }}
            >
              Read only
            </span>
            {collapsible && (
              <button
                onClick={() => setShowCodeChanges(!showCodeChanges)}
                style={{
                  background: "none",
                  border: "1px solid #d0d7de",
                  borderRadius: 6,
                  padding: "6px 12px",
                  cursor: "pointer",
                  fontSize: 12,
                  color: "#24292f",
                }}
              >
                {showCodeChanges ? "Collapse" : "Expand"}
              </button>
            )}
          </div>
        </div>

        {isExpanded &&
          (changes.length > 0 ? (
            <div style={{ maxHeight, overflowY: "auto" }}>
              {changes.map((change, idx) => (
                <div key={`${change.filePath}-${idx}`}>
                  <div
                    onClick={() =>
                      setSelectedDiffFile(selectedDiffFile === change.filePath ? null : change.filePath)
                    }
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "10px 16px",
                      backgroundColor: selectedDiffFile === change.filePath ? "#f0f6fc" : "#fafbfc",
                      borderBottom: "1px solid #d0d7de",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                      <span style={{ fontSize: 14 }}>{selectedDiffFile === change.filePath ? "v" : ">"}</span>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 6px",
                          borderRadius: 999,
                          fontSize: 11,
                          fontWeight: 700,
                          backgroundColor:
                            change.changeType === "added"
                              ? "#dcfce7"
                              : change.changeType === "deleted"
                                ? "#fee2e2"
                                : "#fef3c7",
                          color:
                            change.changeType === "added"
                              ? "#166534"
                              : change.changeType === "deleted"
                                ? "#991b1b"
                                : "#92400e",
                        }}
                      >
                        {change.changeType.toUpperCase()}
                      </span>
                      <span
                        style={{
                          fontFamily: "'JetBrains Mono', 'Consolas', monospace",
                          fontSize: 13,
                          color: "#0969da",
                          wordBreak: "break-all",
                        }}
                      >
                        {change.filePath}
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                      <span style={{ color: "#16a34a", fontSize: 12, fontWeight: 600 }}>+{change.additions}</span>
                      <span style={{ color: "#dc2626", fontSize: 12, fontWeight: 600 }}>-{change.deletions}</span>
                    </div>
                  </div>

                  {selectedDiffFile === change.filePath && (
                    <div
                      style={{
                        backgroundColor: "#0d1117",
                        borderBottom: "1px solid #d0d7de",
                        overflowX: "auto",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "8px 16px",
                          backgroundColor: "#161b22",
                          borderBottom: "1px solid #30363d",
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "'JetBrains Mono', 'Consolas', monospace",
                            fontSize: 12,
                            color: "#8b949e",
                          }}
                        >
                          {change.fileName}
                        </span>
                        <div style={{ display: "flex", gap: 12 }}>
                          <span style={{ fontSize: 11, color: "#3fb950" }}>+{change.additions} lines</span>
                          <span style={{ fontSize: 11, color: "#f85149" }}>-{change.deletions} lines</span>
                        </div>
                      </div>

                      <div
                        style={{
                          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
                          fontSize: 12,
                          lineHeight: 1.5,
                        }}
                      >
                        {change.diffLines.length > 0 ? (
                          change.diffLines.map((line, lineIdx) => {
                            if (line.type === "hunk") {
                              return (
                                <div
                                  key={lineIdx}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    backgroundColor: "#111827",
                                    color: "#93c5fd",
                                    borderTop: "1px solid #30363d",
                                    borderBottom: "1px solid #30363d",
                                  }}
                                >
                                  <span
                                    style={{
                                      minWidth: 60,
                                      padding: "2px 10px",
                                      color: "#6e7681",
                                      borderRight: "1px solid #30363d",
                                      userSelect: "none",
                                    }}
                                  />
                                  <span
                                    style={{
                                      minWidth: 60,
                                      padding: "2px 10px",
                                      color: "#6e7681",
                                      borderRight: "1px solid #30363d",
                                      userSelect: "none",
                                    }}
                                  />
                                  <span
                                    style={{
                                      minWidth: 24,
                                      padding: "2px 6px",
                                      textAlign: "center",
                                      color: "#93c5fd",
                                      userSelect: "none",
                                    }}
                                  >
                                    @
                                  </span>
                                  <span
                                    style={{
                                      flex: 1,
                                      padding: "2px 10px",
                                      whiteSpace: "pre",
                                    }}
                                  >
                                    {line.content}
                                  </span>
                                </div>
                              );
                            }

                            const backgroundColor =
                              line.type === "add"
                                ? "rgba(63, 185, 80, 0.15)"
                                : line.type === "remove"
                                  ? "rgba(248, 81, 73, 0.15)"
                                  : "transparent";

                            const contentColor =
                              line.type === "add"
                                ? "#aff5b4"
                                : line.type === "remove"
                                  ? "#ffa198"
                                  : "#c9d1d9";

                            const symbolColor =
                              line.type === "add"
                                ? "#3fb950"
                                : line.type === "remove"
                                  ? "#f85149"
                                  : "#8b949e";

                            return (
                              <div
                                key={lineIdx}
                                style={{
                                  display: "flex",
                                  backgroundColor,
                                  borderLeft: `4px solid ${
                                    line.type === "add"
                                      ? "#3fb950"
                                      : line.type === "remove"
                                        ? "#f85149"
                                        : "transparent"
                                  }`,
                                }}
                              >
                                <span
                                  style={{
                                    minWidth: 60,
                                    padding: "2px 10px",
                                    textAlign: "right",
                                    color: "#6e7681",
                                    backgroundColor:
                                      line.type === "add"
                                        ? "rgba(63, 185, 80, 0.1)"
                                        : line.type === "remove"
                                          ? "rgba(248, 81, 73, 0.1)"
                                          : "#161b22",
                                    borderRight: "1px solid #30363d",
                                    userSelect: "none",
                                  }}
                                >
                                  {renderLineNumber(line.oldLineNumber)}
                                </span>
                                <span
                                  style={{
                                    minWidth: 60,
                                    padding: "2px 10px",
                                    textAlign: "right",
                                    color: "#6e7681",
                                    backgroundColor:
                                      line.type === "add"
                                        ? "rgba(63, 185, 80, 0.1)"
                                        : line.type === "remove"
                                          ? "rgba(248, 81, 73, 0.1)"
                                          : "#161b22",
                                    borderRight: "1px solid #30363d",
                                    userSelect: "none",
                                  }}
                                >
                                  {renderLineNumber(line.newLineNumber)}
                                </span>
                                <span
                                  style={{
                                    minWidth: 24,
                                    padding: "2px 6px",
                                    textAlign: "center",
                                    color: symbolColor,
                                    fontWeight: 600,
                                    userSelect: "none",
                                  }}
                                >
                                  {line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}
                                </span>
                                <span
                                  style={{
                                    flex: 1,
                                    padding: "2px 10px",
                                    color: contentColor,
                                    whiteSpace: "pre",
                                  }}
                                >
                                  {line.content || " "}
                                </span>
                              </div>
                            );
                          })
                        ) : (
                          <div
                            style={{
                              padding: "12px 16px",
                              color: "#8b949e",
                              fontFamily: "'JetBrains Mono', 'Consolas', monospace",
                            }}
                          >
                            No line-level diff is available for this file.
                          </div>
                        )}
                      </div>
                    </div>

                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: 40, textAlign: "center", color: "#57606a" }}>{emptyMessage}</div>
          ))}
      </div>
    );
  };
  */

  const isDetectedDependencyStatus = (status: string) => {
    const normalizedStatus = status.trim().toLowerCase();
    return normalizedStatus === "upgraded" || normalizedStatus.startsWith("analyzing");
  };

  const getDependencyStatusLabel = (status: string) => {
    return isDetectedDependencyStatus(status)
      ? "ANALYZED"
      : status.replace(/_/g, " ").toUpperCase();
  };

  const parseVersionParts = (version: string | null | undefined) => {
    const normalized = (version || "").trim();
    const match = normalized.match(/(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
    if (!match) {
      return null;
    }

    return {
      major: Number.parseInt(match[1], 10),
      minor: Number.parseInt(match[2] || "0", 10),
      patch: Number.parseInt(match[3] || "0", 10),
      raw: normalized,
    };
  };

  const classifyDependencyCategory = (dep: DependencyInfo): DependencyCategory => {
    const artifactId = (dep.artifact_id || "").toLowerCase();
    const groupId = (dep.group_id || "").toLowerCase();
    const coordinate = `${groupId}:${artifactId}`;

    if (
      artifactId.includes("junit") ||
      artifactId.includes("mockito") ||
      artifactId.includes("assertj") ||
      artifactId.includes("testng") ||
      artifactId.includes("surefire")
    ) {
      return "Testing";
    }
    if (
      artifactId.includes("log4j") ||
      artifactId.includes("slf4j") ||
      artifactId.includes("logback") ||
      artifactId.includes("commons-logging")
    ) {
      return "Logging";
    }
    if (
      artifactId.includes("hibernate") ||
      artifactId.includes("jpa") ||
      artifactId.includes("jdbc") ||
      artifactId.includes("mybatis") ||
      artifactId.includes("dynamodb") ||
      artifactId.includes("persistence")
    ) {
      return "Persistence";
    }
    if (
      artifactId.includes("security") ||
      coordinate.includes("spring-security") ||
      artifactId.includes("oauth") ||
      artifactId.includes("jwt") ||
      artifactId.includes("auth")
    ) {
      return "Security";
    }
    if (
      artifactId.includes("maven") ||
      artifactId.includes("gradle") ||
      artifactId.includes("plugin") ||
      artifactId.includes("wrapper")
    ) {
      return "Build";
    }
    if (
      groupId.startsWith("javax.") ||
      artifactId.startsWith("javax.") ||
      groupId.startsWith("jakarta.") ||
      artifactId.startsWith("jakarta.") ||
      artifactId.includes("servlet") ||
      artifactId.includes("jaxb")
    ) {
      return "Jakarta / Java EE";
    }
    if (
      artifactId.includes("jackson") ||
      artifactId.includes("gson") ||
      artifactId.includes("json") ||
      artifactId.includes("xml") ||
      artifactId.includes("yaml")
    ) {
      return "Data / JSON";
    }
    if (
      artifactId.includes("commons") ||
      artifactId.includes("guava") ||
      artifactId.includes("lombok") ||
      artifactId.includes("lang3") ||
      artifactId.includes("collections")
    ) {
      return "Utilities";
    }
    if (
      coordinate.includes("spring") ||
      coordinate.includes("apache") ||
      coordinate.includes("struts") ||
      coordinate.includes("quarkus") ||
      coordinate.includes("micronaut")
    ) {
      return "Framework";
    }
    return "Other";
  };

  const classifyDependencyRisk = (dep: DependencyInfo): { risk: DependencyRiskLevel; reason: string } => {
    const artifactId = (dep.artifact_id || "").toLowerCase();
    const groupId = (dep.group_id || "").toLowerCase();
    const status = (dep.status || "").toLowerCase();
    const version = dep.current_version || "";
    const parsedVersion = parseVersionParts(version);
    const coordinate = `${groupId}:${artifactId}`;
    const unknownVersion = !version || version.toLowerCase() === "unknown";
    const snapshotVersion = /snapshot|alpha|beta|rc|milestone|release/i.test(version);
    const isLegacyJavax = groupId.startsWith("javax.") || artifactId.startsWith("javax.");
    const isLegacyLog4j = artifactId.includes("log4j") && parsedVersion && parsedVersion.major < 2;
    const isLegacyStruts = coordinate.includes("struts");
    const isCommonsLogging = coordinate.includes("commons-logging");
    const dependencyLabel = coordinate !== ":" ? coordinate : dep.artifact_id || dep.group_id || "This dependency";
    const versionContext = unknownVersion
      ? "Version information could not be resolved from the repository metadata."
      : version
        ? `Current version: ${version}.`
        : "";

    if (isLegacyJavax) {
      return {
        risk: "critical",
        reason: `${dependencyLabel} is marked critical because it still relies on the legacy javax namespace, which usually needs explicit Jakarta migration work. ${versionContext}`.trim(),
      };
    }

    if (isLegacyLog4j) {
      return {
        risk: "critical",
        reason: `${dependencyLabel} is marked critical because it appears to be on Log4j 1.x, a legacy logging stack that usually needs urgent replacement before migration. ${versionContext}`.trim(),
      };
    }

    if (isLegacyStruts) {
      return {
        risk: "critical",
        reason: `${dependencyLabel} is marked critical because Struts-era dependencies are highly migration-sensitive and often require code changes, not just a version bump. ${versionContext}`.trim(),
      };
    }

    if (isCommonsLogging) {
      return {
        risk: "critical",
        reason: `${dependencyLabel} is marked critical because commons-logging is a legacy logging abstraction that frequently needs replacement or bridge cleanup during modernization. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("junit") && parsedVersion && parsedVersion.major < 5) {
      return {
        risk: "high",
        reason: `${dependencyLabel} is marked high because it appears to be on a pre-JUnit 5 generation, which commonly needs test migration updates and runner changes. ${versionContext}`.trim(),
      };
    }

    if (status === "outdated") {
      return {
        risk: "high",
        reason: `${dependencyLabel} is marked high because the repository analysis already flagged it as outdated, so it deserves manual review before migration. ${versionContext}`.trim(),
      };
    }

    if (unknownVersion) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because its version could not be identified from repository metadata, so compatibility needs to be validated during migration.`,
      };
    }

    if (snapshotVersion) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because it uses a pre-release version tag such as snapshot, alpha, beta, or release candidate, which can introduce migration instability. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("spring")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because Spring dependencies usually need coordinated version alignment with the broader application stack during migration. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("hibernate")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because Hibernate upgrades often require ORM compatibility checks, dialect validation, and configuration review. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("jpa")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because JPA-related dependencies can be affected by persistence API and Jakarta namespace changes during migration. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("servlet")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because servlet APIs are often impacted by container compatibility and javax-to-jakarta migration changes. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("jackson")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because Jackson libraries sit on the serialization path and should be compatibility-checked for runtime behavior changes. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("security")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because security libraries are configuration-sensitive and should be reviewed carefully for authentication or authorization changes. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("dynamodb")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because AWS DynamoDB client libraries are runtime-facing and may need API or SDK compatibility validation during migration. ${versionContext}`.trim(),
      };
    }

    if (artifactId.includes("jdbc")) {
      return {
        risk: "medium",
        reason: `${dependencyLabel} is marked medium because JDBC drivers are tightly coupled to database connectivity and should be validated for driver and runtime compatibility. ${versionContext}`.trim(),
      };
    }

    return {
      risk: "low",
      reason: `${dependencyLabel} is marked low because no strong migration-risk indicators were detected from the repository metadata. ${versionContext}`.trim(),
    };
  };

  const categorizeDependencies = (dependencies: DependencyInfo[]): CategorizedDependency[] => {
    return dependencies.map((dep) => {
      const { risk, reason } = classifyDependencyRisk(dep);
      return {
        ...dep,
        displayName: `${dep.group_id}:${dep.artifact_id}`,
        category: classifyDependencyCategory(dep),
        risk,
        reason,
      };
    });
  };

  const getDependencyRiskColors = (risk: DependencyRiskLevel) => {
    if (risk === "critical") {
      return {
        background: "linear-gradient(180deg, #fef2f2 0%, #fee2e2 100%)",
        border: "#fca5a5",
        badgeBackground: "#dc2626",
        badgeColor: "#fff",
        textColor: "#991b1b",
      };
    }
    if (risk === "high") {
      return {
        background: "linear-gradient(180deg, #fff7ed 0%, #ffedd5 100%)",
        border: "#fdba74",
        badgeBackground: "#f97316",
        badgeColor: "#fff",
        textColor: "#9a3412",
      };
    }
    if (risk === "medium") {
      return {
        background: "linear-gradient(180deg, #fffbeb 0%, #fef3c7 100%)",
        border: "#fcd34d",
        badgeBackground: "#f59e0b",
        badgeColor: "#fff",
        textColor: "#92400e",
      };
    }
    return {
      background: "linear-gradient(180deg, #ecfdf5 0%, #dcfce7 100%)",
      border: "#86efac",
      badgeBackground: "#22c55e",
      badgeColor: "#fff",
      textColor: "#166534",
    };
  };

  const handleTargetVersionChange = (value: string) => {
    setSelectedTargetVersion(value);
    if (value) {
      setTargetVersionRequiredError(false);
    }
  };

  const validateTargetBranchName = (branchName: string) => {
    const trimmed = branchName.trim();
    if (!trimmed) {
      return "Target branch name is required.";
    }
    if (/\s/.test(trimmed)) {
      return "Branch names cannot contain spaces.";
    }
    const hasInvalidBranchCharacters = ["\\", "^", ":", "?", "*", "[", "]", "~"].some((char) =>
      trimmed.includes(char)
    );
    if (
      trimmed.startsWith("/") ||
      trimmed.endsWith("/") ||
      trimmed.endsWith(".") ||
      trimmed.endsWith(".lock") ||
      trimmed.includes("..") ||
      trimmed.includes("//") ||
      trimmed.includes("@{") ||
      hasInvalidBranchCharacters
    ) {
      return "Enter a valid Git branch name.";
    }
    return "";
  };

  const validateTargetRepositoryName = (targetValue: string) => {
    const trimmed = targetValue.trim().replace(/\.git$/, "").replace(/\/+$/, "");
    if (!trimmed) {
      return "Target repository name is required.";
    }

    const platform = sourceRepositoryContext?.platform || "github";
    const repoNamePattern = /^[A-Za-z0-9._-]+$/;

    if (repoNamePattern.test(trimmed)) {
      return "";
    }

    const shortFormatMatch = trimmed.match(/^([^/\s]+)\/([^/\s]+)$/);
    if (shortFormatMatch) {
      const [, , repo] = shortFormatMatch;
      if (!repoNamePattern.test(repo)) {
        return "Enter a valid repository name.";
      }
      return "";
    }

    if (!/^https?:\/\//i.test(trimmed)) {
      return "Enter a full repository URL or a repository name.";
    }

    try {
      const parsed = new URL(trimmed);
      const pathParts = parsed.pathname.split("/").filter(Boolean);
      if (pathParts.length !== 2) {
        return "Repository URL must include both owner and repository name.";
      }

      const [, repo] = pathParts;
      if (!repoNamePattern.test(repo)) {
        return "Enter a valid repository name.";
      }
      if (platform === "gitlab" && !parsed.hostname.includes("gitlab")) {
        return "Use a GitLab repository URL for GitLab migrations.";
      }
      if (platform === "github" && !parsed.hostname.includes("github")) {
        return "Use a GitHub repository URL for GitHub migrations.";
      }
      return "";
    } catch {
      return "Enter a valid repository URL.";
    }
  };

  const validateTargetLocalFolderName = (targetValue: string) => {
    const trimmed = targetValue.trim();
    if (!trimmed) {
      return "Target local folder is required.";
    }

    const isWindowsAbsolutePath = /^[A-Za-z]:[\\/]/.test(trimmed);
    const isUnixAbsolutePath = trimmed.startsWith("/");

    if (!isWindowsAbsolutePath && !isUnixAbsolutePath && /[\\/]/.test(trimmed)) {
      return "Enter either a folder name or a full absolute path.";
    }

    const normalizedPath = trimmed.replace(/[\\/]+$/, "");
    const segments = isWindowsAbsolutePath
      ? normalizedPath.slice(2).split(/[\\/]+/).filter(Boolean)
      : isUnixAbsolutePath
        ? normalizedPath.split(/[\\/]+/).filter(Boolean)
        : [normalizedPath];

    if (segments.length === 0) {
      return "Enter a valid local folder path.";
    }

    for (const segment of segments) {
      const hasControlCharacter = [...segment].some((char) => char.charCodeAt(0) < 32);
      if (hasControlCharacter || /[<>:"/\\|?*]/.test(segment)) {
        return "Enter a valid local folder path.";
      }
      if (/[. ]$/.test(segment)) {
        return "Folder names cannot end with a space or period.";
      }
    }

    return "";
  };

  const continueWithTargetVersion = (nextStep: number) => {
    if (!effectiveTargetVersion) {
      setTargetVersionRequiredError(true);
      return;
    }

    const targetNameError =
      currentMigrationApproach === "branch"
        ? validateTargetBranchName(targetRepoName)
        : currentMigrationApproach === "local"
          ? validateTargetLocalFolderName(targetRepoName)
          : validateTargetRepositoryName(targetRepoName);
    if (targetNameError) {
      setTargetRepoNameError(targetNameError);
      return;
    }

    setTargetVersionRequiredError(false);
    setTargetRepoNameError("");
    setStep(nextStep);
  };

  const renderCategorizedDependencies = (dependencies: DependencyInfo[]) => {
    const categorizedDependencies = categorizeDependencies(dependencies);
    const riskCounts = categorizedDependencies.reduce(
      (acc, dep) => {
        acc[dep.risk] += 1;
        return acc;
      },
      { critical: 0, high: 0, medium: 0, low: 0 } as Record<DependencyRiskLevel, number>
    );
    const visibleDependencies =
      dependencyRiskFilter === "all"
        ? categorizedDependencies
        : categorizedDependencies.filter((dep) => dep.risk === dependencyRiskFilter);
    const attentionDependencies = visibleDependencies.filter((dep) => dep.risk !== "low");
    const otherDependencies = visibleDependencies.filter((dep) => dep.risk === "low");
    const dominantRisk: DependencyRiskLevel =
      riskCounts.critical > 0 ? "critical" : riskCounts.high > 0 ? "high" : riskCounts.medium > 0 ? "medium" : "low";
    const topAttentionNames = attentionDependencies.slice(0, 5).map((dep) => dep.artifact_id).join(", ");
    const activeFilterLabel = dependencyRiskFilter === "all" ? "All Dependencies" : `${dependencyRiskFilter.toUpperCase()} Only`;

    const getSummaryCardStyle = (risk: DependencyRiskFilter) => {
      const isActive = dependencyRiskFilter === risk;
      const colors = risk === "all" ? getDependencyRiskColors(dominantRisk) : getDependencyRiskColors(risk);

      return {
        ...styles.dependencySummaryCard,
        borderColor: colors.border,
        background: isActive ? colors.background : "#fff",
        boxShadow: isActive ? `0 0 0 2px ${colors.border}33` : styles.dependencySummaryCard.boxShadow,
        cursor: "pointer",
      };
    };

    const handleRiskFilterClick = (risk: DependencyRiskFilter) => {
      if (risk === "all") {
        setDependencyRiskFilter("all");
        return;
      }

      setDependencyRiskFilter((currentFilter) => (currentFilter === risk ? "all" : risk));
    };

    const renderDependencyCard = (dep: CategorizedDependency, idx: number) => {
      const colors = getDependencyRiskColors(dep.risk);
      return (
        <div
          key={`${dep.displayName}:${idx}`}
          style={{
            ...styles.categorizedDependencyCard,
            background: colors.background,
            borderColor: colors.border,
          }}
          title={dep.reason}
        >
          <div style={styles.categorizedDependencyHeader}>
            <div style={styles.categorizedDependencyName}>{dep.displayName}</div>
            <span
              style={{
                ...styles.dependencyRiskBadge,
                backgroundColor: colors.badgeBackground,
                color: colors.badgeColor,
              }}
            >
              {dep.risk.toUpperCase()}
            </span>
          </div>
          <div style={styles.categorizedDependencyVersion}>{dep.current_version || "Unknown version"}</div>
          <div style={styles.dependencyMetaRow}>
            <span style={styles.dependencyCategoryBadge}>{dep.category}</span>
            {dep.status && (
              <span style={{ ...styles.dependencyStatusPill, color: colors.textColor }}>
                {getDependencyStatusLabel(dep.status)}
              </span>
            )}
          </div>
          <div style={{ ...styles.dependencyReasonText, color: colors.textColor }}>{dep.reason}</div>
        </div>
      );
    };

    return (
      <div style={styles.dependencyInsightsPanel}>
        <div style={styles.dependencyInsightsHeader}>
          <div style={styles.dependencyInsightsTitle}>Total Dependencies ({categorizedDependencies.length})</div>
          <div style={styles.dependencyInsightsSubtitle}>
            Categorized from repository analysis. Risk levels are heuristic migration signals, not live CVE results.
          </div>
        </div>

        <div style={styles.dependencySummaryGrid}>
          <div style={getSummaryCardStyle("all")} onClick={() => handleRiskFilterClick("all")}>
            <div style={styles.dependencySummaryLabel}>Overall Risk</div>
            <div style={styles.dependencySummaryValue}>{dominantRisk.toUpperCase()}</div>
          </div>
          <div style={getSummaryCardStyle("critical")} onClick={() => handleRiskFilterClick("critical")}>
            <div style={styles.dependencySummaryLabel}>Critical</div>
            <div style={{ ...styles.dependencySummaryValue, color: "#dc2626" }}>{riskCounts.critical}</div>
          </div>
          <div style={getSummaryCardStyle("high")} onClick={() => handleRiskFilterClick("high")}>
            <div style={styles.dependencySummaryLabel}>High</div>
            <div style={{ ...styles.dependencySummaryValue, color: "#f97316" }}>{riskCounts.high}</div>
          </div>
          <div style={getSummaryCardStyle("medium")} onClick={() => handleRiskFilterClick("medium")}>
            <div style={styles.dependencySummaryLabel}>Medium</div>
            <div style={{ ...styles.dependencySummaryValue, color: "#d97706" }}>{riskCounts.medium}</div>
          </div>
          <div style={getSummaryCardStyle("low")} onClick={() => handleRiskFilterClick("low")}>
            <div style={styles.dependencySummaryLabel}>Low</div>
            <div style={{ ...styles.dependencySummaryValue, color: "#16a34a" }}>{riskCounts.low}</div>
          </div>
        </div>

        <div style={styles.dependencyFilterBar}>
          <span style={styles.dependencyFilterLabel}>Showing: {activeFilterLabel}</span>
          {dependencyRiskFilter !== "all" && (
            <button
              type="button"
              style={styles.dependencyFilterClearButton}
              onClick={() => setDependencyRiskFilter("all")}
            >
              Clear Filter
            </button>
          )}
        </div>

        {attentionDependencies.length > 0 && (
          <>
            <div style={styles.dependencyAlertBox}>
              <div style={styles.dependencyAlertTitle}>Warning: {attentionDependencies.length} dependencies need migration attention</div>
              <div style={styles.dependencyAlertText}>
                Review runtime-facing, legacy, or incomplete-version dependencies first.
                {topAttentionNames ? ` Priority artifacts: ${topAttentionNames}${attentionDependencies.length > 5 ? "..." : ""}` : ""}
              </div>
            </div>
            <div style={styles.categorizedDependenciesSection}>
              <div style={styles.categorizedDependenciesSectionTitle}>Dependencies Requiring Attention ({attentionDependencies.length})</div>
              <div style={styles.categorizedDependenciesGrid}>
                {attentionDependencies.map(renderDependencyCard)}
              </div>
            </div>
          </>
        )}

        {otherDependencies.length > 0 && (
          <div style={styles.categorizedDependenciesSection}>
            <div style={{ ...styles.categorizedDependenciesSectionTitle, color: "#166534" }}>
              Other Dependencies ({otherDependencies.length})
            </div>
            <div style={styles.categorizedDependenciesGrid}>
              {otherDependencies.map(renderDependencyCard)}
            </div>
          </div>
        )}

        {visibleDependencies.length === 0 && (
          <div style={styles.dependencyEmptyState}>
            No dependencies match the selected risk filter.
          </div>
        )}
      </div>
    );
  };

  const enrichAnalysisWithPomVersion = useCallback(async (
    analysis: RepoAnalysis,
    repoUrlToAnalyze: string,
    token: string
  ) => {
    const javaVersionFromAnalysis = analysis.java_version || analysis.java_version_from_build;
    const needsPomFallback =
      (analysis.build_tool === "maven" || analysis.structure?.has_pom_xml) &&
      (!javaVersionFromAnalysis || javaVersionFromAnalysis === "unknown" || javaVersionFromAnalysis === "not_specified");

    if (!needsPomFallback) {
      return analysis;
    }

    try {
      const response = isLocalRepoRef(repoUrlToAnalyze)
        ? await getLocalProjectFileContent(extractLocalRepoPath(repoUrlToAnalyze), "pom.xml")
        : await getFileContent(repoUrlToAnalyze, "pom.xml", token);
      const fallbackJavaVersion = detectJavaVersionFromPomContent(response.content || "");
      if (!fallbackJavaVersion) {
        return analysis;
      }

      return {
        ...analysis,
        java_version: fallbackJavaVersion,
        java_version_from_build: fallbackJavaVersion,
        java_version_detected_from_build: true,
      };
    } catch {
      return analysis;
    }
  }, []);

  const applyRepositoryAnalysis = useCallback((analysis: RepoAnalysis) => {
    setRepoAnalysis(analysis);
    const javaVersionFromBuild = analysis.java_version || analysis.java_version_from_build || null;
    const hasJavaIndicators =
      (Array.isArray(analysis.java_files) && analysis.java_files.length > 0) ||
      (javaVersionFromBuild !== "unknown" && javaVersionFromBuild !== null) ||
      analysis.build_tool === "maven" || analysis.build_tool === "gradle" ||
      analysis.structure?.has_pom_xml || analysis.structure?.has_build_gradle ||
      (analysis.dependencies && analysis.dependencies.length > 0);
    setIsJavaProject(hasJavaIndicators);

    const hasBuildConfig = analysis.structure?.has_pom_xml || analysis.structure?.has_build_gradle ||
      analysis.build_tool === "maven" || analysis.build_tool === "gradle";
    const hasKnownJavaVersion = javaVersionFromBuild && javaVersionFromBuild !== "unknown";

    if (hasJavaIndicators && (!hasBuildConfig || !hasKnownJavaVersion)) {
      setIsHighRiskProject(true);
      if (hasKnownJavaVersion) {
        setSuggestedJavaVersion(javaVersionFromBuild!);
        setSourceVersionStatus("detected");
      } else {
        setSuggestedJavaVersion("17");
        setSourceVersionStatus("unknown");
      }
    } else {
      setIsHighRiskProject(false);
    }

    const frameworks: { name: string; path: string; type: string }[] = [];
    if (analysis.dependencies) {
      analysis.dependencies.forEach((dep: DependencyInfo & { file_path?: string }) => {
        const artifactId = dep.artifact_id?.toLowerCase() || "";
        const groupId = dep.group_id?.toLowerCase() || "";

        if (artifactId.includes("junit") || groupId.includes("junit")) {
          frameworks.push({ name: "JUnit", path: dep.file_path || "pom.xml", type: "Testing Framework" });
        }
        if (artifactId.includes("spring") || groupId.includes("springframework")) {
          frameworks.push({ name: "Spring Framework", path: dep.file_path || "pom.xml", type: "Application Framework" });
        }
        if (artifactId.includes("hibernate") || groupId.includes("hibernate")) {
          frameworks.push({ name: "Hibernate", path: dep.file_path || "pom.xml", type: "ORM Framework" });
        }
        if (artifactId.includes("lombok")) {
          frameworks.push({ name: "Lombok", path: dep.file_path || "pom.xml", type: "Code Generation" });
        }
        if (artifactId.includes("mockito")) {
          frameworks.push({ name: "Mockito", path: dep.file_path || "pom.xml", type: "Mocking Framework" });
        }
        if (artifactId.includes("log4j") || artifactId.includes("slf4j") || artifactId.includes("logback")) {
          frameworks.push({ name: dep.artifact_id, path: dep.file_path || "pom.xml", type: "Logging" });
        }
        if (artifactId.includes("jackson") || artifactId.includes("gson")) {
          frameworks.push({ name: dep.artifact_id, path: dep.file_path || "pom.xml", type: "JSON Processing" });
        }
        if (artifactId.includes("apache-commons") || groupId.includes("commons-")) {
          frameworks.push({ name: dep.artifact_id, path: dep.file_path || "pom.xml", type: "Utility Library" });
        }
      });
    }

    const uniqueFrameworks = frameworks.filter((fw, index, self) =>
      index === self.findIndex(f => f.name === fw.name)
    );
    setDetectedFrameworks(uniqueFrameworks);

    if (javaVersionFromBuild && javaVersionFromBuild !== "unknown") {
      setSelectedSourceVersion(javaVersionFromBuild);
    }

    const hasTests = analysis.has_tests;
    const hasBuildTool = analysis.build_tool !== null;
    if (hasTests && hasBuildTool) setRiskLevel("low");
    else if (hasBuildTool) setRiskLevel("medium");
    else setRiskLevel("high");
  }, [
    setDetectedFrameworks,
    setIsHighRiskProject,
    setIsJavaProject,
    setRepoAnalysis,
    setRiskLevel,
    setSelectedSourceVersion,
    setSourceVersionStatus,
    setSuggestedJavaVersion,
  ]);

  function resetRepositorySelectionState() {
    setError("");
    resetDiscoverySelectionState();
    setPrefetchedBrdDocument(null);
    setDocumentPrefetchStatus("idle");
    documentPrefetchKeyRef.current = "";
    documentPrefetchPromiseRef.current = null;
    resetTargetRepoNaming();
  }

  const handleOpenFrameworkFile = useCallback(async (framework: { name: string; path: string; type: string }) => {
    if (!selectedRepo) return;

    setFrameworkFileLoading(true);
    setViewingFrameworkFile({ name: framework.name, path: framework.path, content: "" });
    try {
      const response = isLocalRepoRef(selectedRepo.url)
        ? await getLocalProjectFileContent(extractLocalRepoPath(selectedRepo.url), framework.path)
        : await getFileContent(selectedRepo.url, framework.path, currentToken);
      setViewingFrameworkFile({ name: framework.name, path: framework.path, content: response.content });
    } catch {
      setViewingFrameworkFile({ name: framework.name, path: framework.path, content: `// Error loading file: ${framework.path}` });
    } finally {
      setFrameworkFileLoading(false);
    }
  }, [currentToken, selectedRepo, setFrameworkFileLoading, setViewingFrameworkFile]);

  const technicalSpecificationButtonLabel =
    documentGenerationLoading === "brd"
      ? "Generating Document..."
      : documentPrefetchStatus === "loading"
          ? "Preparing Document..."
          : "Generate Document";

  const technicalSpecificationHelperText = documentPrefetchStatus === "loading"
      ? "Preparing the Technical Specification Document in the background."
      : documentPrefetchStatus === "ready"
          ? "The Technical Specification Document is ready to download."
          : "The Technical Specification Document will be generated when you choose to download it.";

  useEffect(() => {
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const fetchVersions = () => {
      getJavaVersions()
        .then((versions) => {
          if (!cancelled) {
            setTargetVersions(versions.target_versions);
          }
        })
        .catch(() => {
          // Backend may not be running yet — retry after 5 seconds
          if (!cancelled) {
            retryTimeout = setTimeout(fetchVersions, 5000);
          }
        });
    };

    fetchVersions();

    return () => {
      cancelled = true;
      if (retryTimeout) clearTimeout(retryTimeout);
    };
  }, [setTargetVersions]);

  useEffect(() => {
    const routeStep = getStepFromPath(location.pathname);
    setStep((currentStep) => (routeStep !== currentStep ? routeStep : currentStep));
  }, [location.pathname]);

  useEffect(() => {
    setMaxVisitedIndicatorStep((currentMax) =>
      Math.max(currentMax, getIndicatorStep(step))
    );
  }, [step]);

  useEffect(() => {
  window.scrollTo({ top: 0, behavior: "auto" });
  }, [step]);

  useEffect(() => {
    const targetRoute = STEP_ROUTES[step] || "/";
    const currentRoute = location.pathname.replace(/\/+$/, "") || "/";

    // if (currentRoute !== targetRoute) {
    //   navigate(targetRoute);
    // }
    if (currentRoute !== targetRoute) {
  navigate(targetRoute, { replace: step === 7 });
}

  }, [step, location.pathname, navigate]);

  const persistedWizardFormState = useMemo(
    () =>
      ({
      maxVisitedIndicatorStep,
      isPrivateRepo,
      patToken,
      currentPath,
      targetRepoName,
      targetRepoNamesByApproach,
      targetRepoNameEditedByApproach,
      targetRepoTimestamp,
      selectedSourceVersion,
      selectedTargetVersion,
      selectedConversions,
      runTests,
      runSonar,
      runFossa,
      fixBusinessLogic,
      functionalTestToolMethod,
      migrationApproach,
      riskLevel,
      selectedFrameworks,
      isJavaProject,
      pathHistory,
      isHighRiskProject,
      highRiskConfirmed,
      suggestedJavaVersion,
      detectedFrameworks,
      userSelectedVersion,
      sourceVersionStatus,
      updateSourceVersion,
      analysisCompletedSeconds,
    } satisfies PersistedWizardFormState),
    [
    maxVisitedIndicatorStep,
    isPrivateRepo,
    patToken,
    currentPath,
    targetRepoName,
    targetRepoNamesByApproach,
    targetRepoNameEditedByApproach,
    targetRepoTimestamp,
    selectedSourceVersion,
    selectedTargetVersion,
    selectedConversions,
    runTests,
    runSonar,
    runFossa,
    fixBusinessLogic,
    migrationApproach,
    riskLevel,
    selectedFrameworks,
    isJavaProject,
    pathHistory,
    isHighRiskProject,
    highRiskConfirmed,
    suggestedJavaVersion,
    detectedFrameworks,
    userSelectedVersion,
    sourceVersionStatus,
    updateSourceVersion,
    analysisCompletedSeconds,
    ]
  );

  useMigrationWizardPersistence({
    repoUrl,
    selectedRepo,
    repoAnalysis,
    migrationJob,
    formState: persistedWizardFormState,
  });

  useEffect(() => {
    if (migrationJob?.fossa_report) {
      setFossaResult(migrationJob.fossa_report);
      fossaLoadedJobIdRef.current = migrationJob.job_id;
      return;
    }

    if (fossaResult && migrationJob?.job_id !== fossaLoadedJobIdRef.current) {
      setFossaResult(null);
    }
  }, [fossaResult, migrationJob?.job_id, migrationJob?.fossa_report, setFossaResult]);

  // Load detailed FOSSA results only when the report view needs them.
  useEffect(() => {
    const jobId = migrationJob?.job_id;
    const shouldLoadFossa =
      Boolean(jobId) &&
      step === 7 &&
      reportAccordionState.fossa &&
      (runFossa ||
        migrationJob?.fossa_policy_status != null ||
        migrationJob?.fossa_scan_mode != null ||
        migrationJob?.fossa_error_message != null ||
        migrationJob?.fossa_report != null);

    if (!jobId || !shouldLoadFossa) {
      return;
    }

    if (migrationJob?.fossa_report || fossaLoadedJobIdRef.current === jobId) {
      return;
    }

    let cancelled = false;
    setFossaLoading(true);

    getMigrationFossa(jobId)
      .then(({ fossa }) => {
        if (cancelled) return;

        fossaLoadedJobIdRef.current = jobId;
        setFossaResult(fossa);
        setMigrationJob((prev) =>
          prev
            ? {
                ...prev,
                fossa_policy_status: fossa.compliance_status ?? prev.fossa_policy_status,
                fossa_total_dependencies: fossa.total_dependencies ?? prev.fossa_total_dependencies,
                fossa_license_issues: fossa.license_issues ?? prev.fossa_license_issues,
                fossa_vulnerabilities:
                  typeof fossa.vulnerabilities === "number"
                    ? fossa.vulnerabilities
                    : fossa.vulnerabilities && typeof fossa.vulnerabilities === "object"
                      ? Object.values(fossa.vulnerabilities).reduce((sum, value) => sum + (Number(value) || 0), 0)
                      : prev.fossa_vulnerabilities,
                fossa_outdated_dependencies: fossa.outdated_dependencies ?? prev.fossa_outdated_dependencies,
                fossa_scan_mode: fossa.scan_mode ?? prev.fossa_scan_mode,
                fossa_real_scan: fossa.real_scan ?? prev.fossa_real_scan,
                fossa_analysis_url: fossa.analysis_url ?? prev.fossa_analysis_url,
                fossa_error_message: fossa.error_message ?? prev.fossa_error_message,
                fossa_report: fossa,
              }
            : prev
        );
      })
      .catch(() => {
        if (!cancelled) {
          fossaLoadedJobIdRef.current = null;
        }
      })
      .finally(() => {
        if (!cancelled) {
          setFossaLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    migrationJob?.fossa_error_message,
    migrationJob?.fossa_policy_status,
    migrationJob?.fossa_report,
    migrationJob?.fossa_scan_mode,
    migrationJob?.job_id,
    reportAccordionState.fossa,
    runFossa,
    setFossaLoading,
    setFossaResult,
    setMigrationJob,
    step,
  ]);

  const reportCodeChanges = useMemo(
    () => buildCodeChangesFromPreviewDiffs(migrationJob?.file_diffs || []),
    [migrationJob?.file_diffs]
  );
  const visibleReportCodeChanges = useMemo(
    () => reportCodeChanges.slice(0, visibleReportDiffCount),
    [reportCodeChanges, visibleReportDiffCount]
  );
  const hasMoreReportCodeChanges = visibleReportDiffCount < reportCodeChanges.length;

  useEffect(() => {
    setVisibleReportDiffCount(REPORT_DIFFS_PAGE_SIZE);
  }, [migrationJob?.job_id, setVisibleReportDiffCount]);

  useEffect(() => {
    setReportDependencyPage(1);
  }, [migrationJob?.dependencies?.length, migrationJob?.job_id, setReportDependencyPage]);

  useEffect(() => {
    if (step !== 7 || !migrationJob?.job_id) {
      return;
    }

    const gen = ++detailFetchGenRef.current;

    getMigrationDetail(migrationJob.job_id)
      .then((job) => {
        if (detailFetchGenRef.current !== gen) return;
        setMigrationJob(job);
        setMigrationDetailLoadedJobId(job.job_id);
      })
      .catch(() => {});
  }, [migrationJob?.job_id, setMigrationDetailLoadedJobId, setMigrationJob, step]);

  useEffect(() => {
    if (step !== 5 || !migrationJob?.job_id) {
      return;
    }

    const currentStepText = (migrationJob?.current_step || "").toLowerCase();
    const testPhaseActive =
      currentStepText.includes("test") ||
      currentStepText.includes("sonar") ||
      currentStepText.includes("fossa") ||
      currentStepText.includes("push") ||
      migrationJob?.status === "completed" ||
      migrationJob?.status === "failed";

    if (!testPhaseActive) {
      return;
    }

    const gen = ++detailFetchGenRef.current;

    getMigrationDetail(migrationJob.job_id)
      .then((job) => {
        if (detailFetchGenRef.current !== gen) return;
        setMigrationJob(job);
        setMigrationDetailLoadedJobId(job.job_id);
      })
      .catch(() => {});
  }, [migrationJob?.job_id, migrationJob?.current_step, migrationJob?.status, setMigrationDetailLoadedJobId, setMigrationJob, step]);

  useEffect(() => {
    const activeChanges = step === 7 ? visibleReportCodeChanges : codeChanges;

    if (activeChanges.length === 0) {
      if (selectedDiffFile !== null) {
        setSelectedDiffFile(null);
      }
      return;
    }

    const selectedStillExists =
      selectedDiffFile !== null &&
      activeChanges.some((change) => change.filePath === selectedDiffFile);

    if (!selectedStillExists) {
      setSelectedDiffFile(activeChanges[0].filePath);
    }
  }, [codeChanges, selectedDiffFile, setSelectedDiffFile, step, visibleReportCodeChanges]);

  const detectedJavaVersion = (repoAnalysis?.java_version || repoAnalysis?.java_version_from_build || "").toString().trim();
  const detectedJavaStructureLabel = detectedJavaVersion ? `Java ${detectedJavaVersion}` : "Java version missing";
  const detectedSourceBuildTool = repoAnalysis?.build_tool ||
    // (repoAnalysis?.structure?.has_pom_xml ? "maven" : repoAnalysis?.structure?.has_build_gradle ? "gradle" : null);
    (repoAnalysis?.structure?.has_pom_xml ? "maven" : (repoAnalysis?.structure?.has_build_gradle || repoAnalysis?.structure?.has_build_gradle_kts) ? "gradle" : null);

  // const plannedBuildTool =
  //   selectedConversions.includes("maven_to_gradle")
  //     ? "gradle"
  //     : selectedConversions.includes("gradle_to_maven")
  //       ? "maven"
  //       : detectedSourceBuildTool;
  // const buildToolDisplayLabel =
  //   detectedSourceBuildTool && plannedBuildTool && detectedSourceBuildTool !== plannedBuildTool
  //     ? `${detectedSourceBuildTool} -> ${plannedBuildTool}`
  //     : plannedBuildTool || "Not Detected";
  
  const buildToolDisplayLabel = detectedSourceBuildTool || "Not Detected";
  const strategyRiskExplanation =
    riskLevel === "low"
      ? "The project is already on a modern migration path with build tooling and tests detected."
      : riskLevel === "medium"
        ? "The project has build tooling, but tests are missing or limited."
        : "The project needs extra review because build tooling or Java metadata was not detected.";
  const selectedSourceVersionNumber = parseJavaVersion(selectedSourceVersion);
  const highestSupportedTargetVersion = useMemo(() => {
    return targetVersions.reduce<number | null>((highest, version) => {
      const parsed = parseJavaVersion(version.value);
      if (parsed === null) {
        return highest;
      }
      return highest === null || parsed > highest ? parsed : highest;
    }, null);
  }, [targetVersions]);
  const sourceAlreadyAtLatestSupportedVersion =
    selectedSourceVersionNumber !== null &&
    highestSupportedTargetVersion !== null &&
    selectedSourceVersionNumber >= highestSupportedTargetVersion;

  const availableTargetVersions = useMemo(() => {
    if (selectedSourceVersionNumber === null) {
      return [];
    }

    return targetVersions.filter((version) => {
      const targetVersionNumber = parseJavaVersion(version.value);
      return targetVersionNumber !== null && targetVersionNumber > selectedSourceVersionNumber;
    });
  }, [selectedSourceVersionNumber, targetVersions]);
  const effectiveTargetVersion = sourceAlreadyAtLatestSupportedVersion
    ? selectedSourceVersion
    : selectedTargetVersion;

  const versionRecommendationCards = useMemo(() => {
    if (!versionRecommendation) {
      return [];
    }

    const ltsJavaVersions = new Set(["8", "11", "17", "21", "25"]);

    const orderedVersions = [
      ...(versionRecommendation.recommended_versions?.length
        ? versionRecommendation.recommended_versions
        : [versionRecommendation.recommended_target_version]),
      ...versionRecommendation.alternatives,
    ].filter(
      (value, index, values) =>
        Boolean(value) &&
        values.indexOf(value) === index &&
        ltsJavaVersions.has(value)
    );

    const cards = orderedVersions
      .map((version, index) => {
        const matchedVersion = availableTargetVersions.find((item) => item.value === version);
        if (!matchedVersion) {
          return null;
        }

        const alternativeDetail = versionRecommendation.alternative_options?.find((option) => option.version === version);
        const isPrimary = version === versionRecommendation.recommended_target_version;
        const isLts = ltsJavaVersions.has(version);
        const description = isPrimary
          ? versionRecommendation.rationale.slice(0, 2).join(" ")
          : alternativeDetail?.reason || `Compatible upgrade path from Java ${selectedSourceVersion}.`;

        return {
          version,
          label: matchedVersion.label,
          eyebrow: isPrimary ? (isLts ? "Recommended LTS" : "Recommended") : (isLts ? "LTS" : "Feature Release"),
          description,
          helper: isPrimary
            ? `Confidence: ${versionRecommendation.confidence}`
            : alternativeDetail?.risk
              ? `Risk: ${alternativeDetail.risk}`
              : `Click to select Java ${version}`,
          badgeBackground: isLts ? "#dcfce7" : "#ffedd5",
          badgeColor: isLts ? "#15803d" : "#c2410c",
          rank: index,
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));

    if (cards.length > 0) {
      return cards;
    }

    const fallbackTarget =
      availableTargetVersions.find((item) => ltsJavaVersions.has(item.value)) ||
      availableTargetVersions[availableTargetVersions.length - 1];

    if (!fallbackTarget) {
      return [];
    }

    return [
      {
        version: fallbackTarget.value,
        label: fallbackTarget.label,
        eyebrow: "Recommended LTS",
        description:
          versionRecommendation.rationale.slice(0, 2).join(" ") ||
          `Recommended upgrade path from Java ${selectedSourceVersion}.`,
        helper: `Confidence: ${versionRecommendation.confidence}`,
        badgeBackground: "#dcfce7",
        badgeColor: "#15803d",
        rank: 0,
      },
    ];
  }, [availableTargetVersions, selectedSourceVersion, versionRecommendation]);

  const categorizedStrategyDependencies = useMemo(() => categorizeDependencies(repoAnalysis?.dependencies || []), [repoAnalysis?.dependencies]);
  const dependencyRiskSummary = useMemo(() => {
    return categorizedStrategyDependencies.reduce(
      (acc, dependency) => {
        acc[dependency.risk] += 1;
        return acc;
      },
      { critical: 0, high: 0, medium: 0, low: 0 } as Record<DependencyRiskLevel, number>
    );
  }, [categorizedStrategyDependencies]);
  const attentionStrategyDependencies = useMemo(
    () =>
      categorizedStrategyDependencies
        .filter((dependency) => dependency.risk !== "low")
        .slice(0, 8)
        .map((dependency) => ({
          display_name: dependency.displayName,
          current_version: dependency.current_version,
          risk: dependency.risk,
          reason: dependency.reason,
          status: dependency.status,
          category: dependency.category,
        })),
    [categorizedStrategyDependencies]
  );

  const strategyAssistantContext = useMemo<StrategyPageContext>(() => {
    const dependencyOverview = (repoAnalysis?.dependencies || [])
      .slice(0, 6)
      .map((dependency) => ({
        group_id: dependency.group_id,
        artifact_id: dependency.artifact_id,
        current_version: dependency.current_version,
        status: dependency.status,
      }));

    const recommendation = versionRecommendation
      ? {
          recommended_target_version: versionRecommendation.recommended_target_version,
          recommended_versions: versionRecommendation.recommended_versions?.slice(0, 3) ?? [],
          confidence: versionRecommendation.confidence,
          rationale: versionRecommendation.rationale.slice(0, 2),
          alternatives: versionRecommendation.alternatives.slice(0, 2),
          alternative_options: versionRecommendation.alternative_options?.slice(0, 3) ?? [],
        }
      : undefined;

    return {
      page: "Assessment & Migration Strategy",
      repository: {
        name: selectedRepo?.name ?? repoAnalysis?.name ?? null,
        full_name: selectedRepo?.full_name ?? repoAnalysis?.full_name ?? null,
        url: selectedRepo?.url ?? repoUrl ?? null,
        language: repoAnalysis?.language ?? null,
      },
      assessment: {
        risk_level: riskLevel || "unknown",
        risk_reason: strategyRiskExplanation,
        build_tool: buildToolDisplayLabel,
        java_version: repoAnalysis?.java_version || repoAnalysis?.java_version_from_build || null,
        has_tests: typeof repoAnalysis?.has_tests === "boolean" ? repoAnalysis.has_tests : null,
        dependency_count: repoAnalysis?.dependencies?.length ?? 0,
      },
      strategy: {
        source_java_version: selectedSourceVersion || null,
        target_java_version: effectiveTargetVersion || null,
        selected_conversions: selectedConversions.slice(0, 5),
        source_already_at_latest_supported_version: sourceAlreadyAtLatestSupportedVersion,
      },
      migration_destination: {
        approach: currentMigrationApproach,
        label:
          migrationApproachOptions.find((option) => option.value === currentMigrationApproach)?.label ||
          null,
        description:
          migrationApproachOptions.find((option) => option.value === currentMigrationApproach)?.desc ||
          null,
        target_repo_name: targetRepoName || getAutoGeneratedTargetName(currentMigrationApproach),
        target_repo_owner: targetRepositoryOwner,
        target_repo_host: targetRepositoryHost,
        target_repo_name_editable: currentMigrationApproach !== "fork",
        target_repo_name_source: targetRepoNameEditedByApproach[currentMigrationApproach]
          ? "manual"
          : "auto-generated",
      },
      migration_approach_options: migrationApproachOptions.map((option) => ({
        value: option.value,
        label: option.label,
        desc: option.desc,
        tooltip: option.tooltip,
      })),
      recommendation,
      dependency_overview: dependencyOverview,
      dependency_risk_summary: dependencyRiskSummary,
      attention_dependencies: attentionStrategyDependencies,
      conversion_options: [
        {
          key: "java_version",
          title: "Java Version Upgrade",
          status: "active",
          description: "Upgrade Java version with dependency updates",
        },
        {
          key: "build_conversion",
          title: "Maven -> Gradle | Gradle -> Maven",
          status: "coming_soon",
          description: "Convert pom.xml to build.gradle with dependency mapping",
        },
        {
          key: "business_logic",
          title: "Business Logic Refactoring",
          status: "coming_soon",
          description: "Analyze and rewrite migration-sensitive code paths",
        },
      ],
    };
  }, [
    buildToolDisplayLabel,
    effectiveTargetVersion,
    repoAnalysis?.dependencies,
    repoAnalysis?.full_name,
    repoAnalysis?.java_version,
    repoAnalysis?.java_version_from_build,
    repoAnalysis?.language,
    repoAnalysis?.name,
    repoUrl,
    riskLevel,
    selectedConversions,
    selectedRepo?.full_name,
    selectedRepo?.name,
    selectedRepo?.url,
    selectedSourceVersion,
    sourceAlreadyAtLatestSupportedVersion,
    strategyRiskExplanation,
    dependencyRiskSummary,
    attentionStrategyDependencies,
    versionRecommendation,
    currentMigrationApproach,
    targetRepoName,
    targetRepoNameEditedByApproach,
    targetRepositoryHost,
    targetRepositoryOwner,
    migrationApproachOptions,
    getAutoGeneratedTargetName,
  ]);

  const plannedCodeRefactoringTooltip = useMemo(() => {
    const previewDescriptions = migrationPreview
      ? Array.from(
          new Map(
            Object.values(migrationPreview.changes.file_changes)
              .flatMap((fileChanges) => fileChanges)
              .map((change) => [change.description, change])
          ).values()
        )
      : [];

    const refactoringSteps = previewDescriptions.length > 0
      ? previewDescriptions.slice(0, 5).map((change) => {
          const occurrences = change.occurrences && change.occurrences > 1
            ? ` (${change.occurrences} matches)`
            : "";
          return `${change.description}${occurrences}`;
        })
      : [
          `Upgrade Java language and build compatibility from Java ${selectedSourceVersion} to Java ${effectiveTargetVersion || "the selected target version"}`,
          "Refactor deprecated or incompatible Java APIs to supported equivalents",
          "Modernize exception handling, imports, and resource-management patterns",
          "Adjust framework and dependency usage for target-version compatibility",
        ];

    if (migrationPreview?.changes.dependencies_to_update?.length) {
      refactoringSteps.push(
        `Update ${migrationPreview.changes.dependencies_to_update.length} dependency version${migrationPreview.changes.dependencies_to_update.length === 1 ? "" : "s"} for compatibility`
      );
    } else if (repoAnalysis?.dependencies?.length) {
      refactoringSteps.push("Adjust framework and dependency usage for target-version compatibility");
    }

    if (fixBusinessLogic && !refactoringSteps.some((stepItem) => stepItem.toLowerCase().includes("business logic"))) {
      refactoringSteps.push("Apply business-logic-safe fixes where migration introduces risky behavior changes");
    }

    const endpointCount = repoAnalysis?.api_endpoints?.length ?? 0;
    if (endpointCount > 0) {
      refactoringSteps.push(`Preserve and validate ${endpointCount} detected API endpoint${endpointCount === 1 ? "" : "s"} during refactoring`);
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#0f172a" }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Planned refactoring</div>
        <div style={{ fontSize: 12, lineHeight: 1.45 }}>
          {refactoringSteps.map((stepItem, index) => (
            <div key={index} style={{ marginBottom: index === refactoringSteps.length - 1 ? 0 : 6 }}>
              {index + 1}. {stepItem}
            </div>
          ))}
        </div>
      </div>
    );
  }, [
    fixBusinessLogic,
    migrationPreview,
    repoAnalysis?.api_endpoints,
    repoAnalysis?.dependencies?.length,
    effectiveTargetVersion,
    selectedSourceVersion,
  ]);

  const plannedDependenciesTooltip = useMemo(() => {
    const dependencyUpdateCount = migrationPreview?.changes.dependencies_to_update?.length ?? 0;
    const discoveredDependencyCount = repoAnalysis?.dependencies?.length ?? 0;
    const dependencyHighlights = dependencyUpdateCount > 0
      ? migrationPreview!.changes.dependencies_to_update.slice(0, 5).map((dependency) => {
          const targetVersion = dependency.new_version || "latest compatible version";
          return `${dependency.dependency}: ${dependency.current_version} -> ${targetVersion}`;
        })
      : [
          `Review ${discoveredDependencyCount} detected dependenc${discoveredDependencyCount === 1 ? "y" : "ies"} for target-version compatibility`,
          "Upgrade framework, plugin, and build-tool packages that block the migration",
          "Preserve safe versions while removing deprecated or conflicting transitive libraries",
          "Validate dependency alignment before code generation and testing",
        ];

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#0f172a" }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Dependency upgrade plan</div>
        <div style={{ fontSize: 12, lineHeight: 1.45 }}>
          {dependencyHighlights.map((item, index) => (
            <div key={index} style={{ marginBottom: index === dependencyHighlights.length - 1 ? 0 : 6 }}>
              {index + 1}. {item}
            </div>
          ))}
        </div>
      </div>
    );
  }, [migrationPreview, repoAnalysis?.dependencies]);

  const plannedBusinessLogicTooltip = useMemo(() => {
    const endpointCount = repoAnalysis?.api_endpoints?.length ?? 0;
    const businessLogicSteps = [
      "Protect runtime behavior while upgrading null handling, error handling, and resource usage",
      "Reduce migration regressions by tightening reliability-sensitive paths before final validation",
      "Modernize risky code patterns only where the migration introduces compatibility pressure",
    ];

    if (endpointCount > 0) {
      businessLogicSteps.push(`Keep ${endpointCount} detected API endpoint${endpointCount === 1 ? "" : "s"} stable during modernization`);
    }

    if (runTests) {
      businessLogicSteps.push("Verify behavior changes against the configured test suite after refactoring");
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8, color: "#0f172a" }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Business logic safeguards</div>
        <div style={{ fontSize: 12, lineHeight: 1.45 }}>
          {businessLogicSteps.map((item, index) => (
            <div key={index} style={{ marginBottom: index === businessLogicSteps.length - 1 ? 0 : 6 }}>
              {index + 1}. {item}
            </div>
          ))}
        </div>
      </div>
    );
  }, [repoAnalysis?.api_endpoints, runTests]);

  const formattedAnalysisElapsed = `${Math.floor(analysisElapsedSeconds / 60)
    .toString()
    .padStart(2, "0")}:${(analysisElapsedSeconds % 60).toString().padStart(2, "0")}`;
   
  const formattedAnalysisCompleted = `${Math.floor(analysisCompletedSeconds / 60)
  .toString()
  .padStart(2, "0")}:${(analysisCompletedSeconds % 60).toString().padStart(2, "0")}`;
  const isTechnicalDocumentWarmPending =
    Boolean(repoAnalysis) &&
    documentPrefetchStatus !== "ready" &&
    documentPrefetchStatus !== "error";
  const isDiscoveryPending =
    analysisLoading ||
    Boolean(
      repoAnalysis &&
      (!repoPreviewInitialized || !microserviceAssessmentResolved || isTechnicalDocumentWarmPending)
    );
 
  useEffect(() => {
    if (!isDiscoveryPending) {
      return;
    }

    const startedAt = analysisStartedAtMs ?? Date.now();
    if (!analysisStartedAtMs) {
      setAnalysisStartedAtMs(startedAt);
      setAnalysisElapsedSeconds(0);
    }

    const updateElapsed = () => {
      setAnalysisElapsedSeconds(Math.max(1, Math.floor((Date.now() - startedAt) / 1000)));
    };

    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);

    return () => window.clearInterval(interval);
  }, [isDiscoveryPending, analysisStartedAtMs, setAnalysisElapsedSeconds, setAnalysisStartedAtMs]);

  useEffect(() => {
    if (!isDiscoveryPending && analysisStartedAtMs) {
      const elapsed = Math.max(1, Math.floor((Date.now() - analysisStartedAtMs) / 1000));
      setAnalysisCompletedSeconds(elapsed);
      setAnalysisStartedAtMs(null);
    }
  }, [isDiscoveryPending, analysisStartedAtMs, setAnalysisCompletedSeconds, setAnalysisStartedAtMs]);

  useEffect(() => {
    setMigrationTimerNow(Date.now());

    if (!(step >= 5 && step <= 6 && migrationJob?.started_at)) {
      return;
    }

    if (isTerminalMigrationStatus(migrationJob.status)) {
      return;
    }

    const interval = window.setInterval(() => {
      setMigrationTimerNow(Date.now());
    }, 1000);

    return () => window.clearInterval(interval);
  }, [migrationJob?.completed_at, migrationJob?.started_at, migrationJob?.status, setMigrationTimerNow, step]);

  // Keep the progress bar aligned with the backend-reported migration phase.
  useEffect(() => {
    if (step === 5 && migrationJob) {
      const actualProgress = migrationJob.progress_percent || 0;
      if (migrationJob.status === "completed") {
        setAnimationProgress(100);
      } else if (migrationJob.status === "failed") {
        setAnimationProgress(Math.min(Math.max(actualProgress, 5), 99));
      } else {
        setAnimationProgress(Math.min(Math.max(actualProgress, 5), 99));
      }
    } else if (step !== 5) {
      setAnimationProgress(0);
    }
  }, [migrationJob, migrationJob?.progress_percent, migrationJob?.status, setAnimationProgress, step]);

  useEffect(() => {
    if (step === 2 && selectedRepo && !repoAnalysis) {
      setAnalysisLoading(true);
      setError("");

      const analyzePromise = isLocalRepoRef(selectedRepo.url)
          ? analyzeLocalProject(extractLocalRepoPath(selectedRepo.url))
            .then(async (result) => enrichAnalysisWithPomVersion(result.analysis, selectedRepo.url, ""))
        : analyzeRepoUrl(selectedRepo.url, currentToken, true)
            .then(async (result) => enrichAnalysisWithPomVersion(result.analysis, selectedRepo.url, currentToken));

      analyzePromise
        .then((analysis) => applyRepositoryAnalysis(analysis))
        .catch((err) => {
          const message = err?.message || "Failed to analyze repository.";
          if (isPrivateRepoAccessError(message)) {
            setIsPrivateRepo(true);
            setStep(1);
            setError("");
            if (currentToken.trim()) {
              // Token was provided but still failed — may be insufficient scope or expired
              setAccessTokenValidationState("invalid");
              setAccessTokenValidationMessage(
                "The provided PAT could not access this repository. Verify that your token has 'repo' scope and has not expired."
              );
            } else {
              setAccessTokenValidationState("invalid");
              setAccessTokenValidationMessage(
                "Add a GitHub Personal Access Token with repo scope to continue analyzing this private repository."
              );
            }
            return;
          }
          setError(message);
        })
        .finally(() => setAnalysisLoading(false));
    }
  }, [
    applyRepositoryAnalysis,
    currentToken,
    enrichAnalysisWithPomVersion,
    repoAnalysis,
    selectedRepo,
    setAccessTokenValidationMessage,
    setAccessTokenValidationState,
    setAnalysisLoading,
    setIsPrivateRepo,
    showEnterpriseToken,
    step,
  ]);

  useEffect(() => {
    if (step !== 3 || !repoAnalysis || !selectedSourceVersion || sourceAlreadyAtLatestSupportedVersion) {
      if (sourceAlreadyAtLatestSupportedVersion) {
        setVersionRecommendation(null);
        setVersionRecommendationLoading(false);
        setVersionRecommendationError("");
      }
      if (step !== 3) {
        setVersionRecommendation(null);
        setVersionRecommendationLoading(false);
        setVersionRecommendationError("");
      }
      return;
    }

    let cancelled = false;
    setVersionRecommendationLoading(true);
    setVersionRecommendationError("");

    getJavaVersionRecommendation({
      source_java_version: selectedSourceVersion,
      detected_java_version: repoAnalysis.java_version,
      build_tool: repoAnalysis.build_tool,
      dependencies: repoAnalysis.dependencies || [],
      has_tests: repoAnalysis.has_tests,
      api_endpoint_count: repoAnalysis.api_endpoints?.length ?? 0,
      risk_level: riskLevel || "unknown",
      llm_provider: "openai",
    })
      .then((recommendation) => {
        if (cancelled) return;
        setVersionRecommendation(recommendation);
      })
      .catch((err) => {
        if (cancelled) return;
        setVersionRecommendation(null);
        setVersionRecommendationError(err?.message || "Failed to get Java version recommendation.");
      })
      .finally(() => {
        if (!cancelled) {
          setVersionRecommendationLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [step, repoAnalysis, selectedSourceVersion, riskLevel, sourceAlreadyAtLatestSupportedVersion]);

  useEffect(() => {
    if (step !== 1 || !urlValidation.valid || showEnterpriseToken || patToken.trim()) {
      setRepoAccessCheckLoading(false);
      return;
    }

    const normalizedUrl = urlValidation.normalizedUrl;
    let cancelled = false;

    // Show loading immediately so the "Have a PAT?" hyperlink doesn't flash
    // before the debounced visibility check starts.
    setRepoAccessCheckLoading(true);

    const timer = setTimeout(() => {

        getRepoVisibility(normalizedUrl, currentToken)
        .then((visibility) => {
          if (cancelled) return;
          if (visibility.requires_token || visibility.visibility === "private") {
            setIsPrivateRepo(true);
            setError("");
            resetAccessTokenValidationState();
            return;
          }

          setIsPrivateRepo(false);
          setError("");
        })
        .catch((err) => {
          if (cancelled) return;
          // If the backend returned 400 (invalid URL parse), don't show PAT card.
          // For all other errors (network failures, 500, timeouts, etc.),
          // conservatively treat as private — the backend's anonymous fallback
          // succeeds for public repos, so reaching here means the repo is
          // genuinely private/inaccessible or the server couldn't be reached.
          const isUrlError = err?.status === 400;
          const message = err instanceof Error ? err.message : "";
          const shouldShowPrivateRepoState = !isUrlError && isPrivateRepoAccessError(message);
          setIsPrivateRepo(shouldShowPrivateRepoState);
          setError(shouldShowPrivateRepoState ? "" : message || "");
          if (shouldShowPrivateRepoState) {
            resetAccessTokenValidationState();
          }
        })
        .finally(() => {
          if (!cancelled) {
            setRepoAccessCheckLoading(false);
          }
        });
    }, 700);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    currentToken,
    patToken,
    resetAccessTokenValidationState,
    setIsPrivateRepo,
    setRepoAccessCheckLoading,
    showEnterpriseToken,
    step,
    urlValidation.normalizedUrl,
    urlValidation.valid,
  ]);

  useEffect(() => {
    if (step === 2 && selectedRepo && repoAnalysis && !analysisLoading) {
      const filesPromise = isLocalRepoRef(selectedRepo.url)
        ? listLocalProjectFiles(extractLocalRepoPath(selectedRepo.url), currentPath)
        : listRepoFiles(selectedRepo.url, currentToken, currentPath);
      filesPromise
        .then((response) => {
          setRepoFiles(response.files);
        })
        .catch((err) => setError(err.message || "Failed to list repository files."))
        .finally(() => {
          if (!currentPath) {
            setRepoPreviewInitialized(true);
          }
        });
    }
  }, [
    analysisLoading,
    currentPath,
    currentToken,
    repoAnalysis,
    selectedRepo,
    setRepoFiles,
    setRepoPreviewInitialized,
    step,
  ]);

  useEffect(() => {
    const repoReference = selectedRepo?.url || repoUrl || migrationJob?.source_repo || "";

    if (!repoAnalysis || !repoReference) {
      return;
    }

    const prefetchKey = [
      repoReference,
      currentToken || "",
      migrationJob?.job_id || "",
      repoAnalysis?.java_version || "",
      String(repoAnalysis?.java_files?.length || 0),
      String(repoAnalysis?.dependencies?.length || 0),
      String(repoAnalysis?.api_endpoints?.length || 0),
      selectedSourceVersion || "",
      effectiveTargetVersion || "",
    ].join("::");
    if (documentPrefetchKeyRef.current === prefetchKey) {
      return;
    }

    documentPrefetchKeyRef.current = prefetchKey;
    setDocumentPrefetchStatus("loading");
    setPrefetchedBrdDocument(null);

    let cancelled = false;
    const githubRequest = {
      repo_url: repoReference,
      repository_url: repoReference,
      source_repo_url: repoReference,
      token: currentToken || undefined,
      github_token: currentToken || undefined,
      job_id: migrationJob?.job_id || undefined,
      migration_job_id: migrationJob?.job_id || undefined,
      source_repo: migrationJob?.source_repo || repoReference,
      target_repo: migrationJob?.target_repo || null,
      source_java_version: repoAnalysis?.java_version || selectedSourceVersion || undefined,
      target_java_version: effectiveTargetVersion || undefined,
      document_type: "BRD",
    };
    const localProjectRequest = {
      repo_url: repoReference,
      repository_url: repoReference,
      source_repo_url: repoReference,
      source_repo: selectedRepo?.name || repoAnalysis?.name || repoReference,
      target_repo: migrationJob?.target_repo || null,
      source_java_version: repoAnalysis?.java_version || selectedSourceVersion || undefined,
      target_java_version: effectiveTargetVersion || undefined,
      document_type: "BRD",
      analysis: repoAnalysis as unknown as Record<string, unknown>,
    };

    const prefetchPromise = (isLocalRepoRef(repoReference)
      ? generateLocalProjectDocument(localProjectRequest)
      : generateGithubDocument("brd", githubRequest))
      .then(async (result) => {
        if (cancelled) return null;
        const generatedAsset = await resolveGeneratedDocumentAsset(result);
        const filename = buildHtmlFilename(result.filename, technicalDocumentFallbackRepoName);
        if (cancelled) return null;

        if (generatedAsset.html) {
          return {
            filename,
            html: generatedAsset.html,
          } satisfies PrefetchedBrdDocument;
        }

        throw new Error("Generated BRD document did not include HTML content or a download URL.");
      })
      .then((preparedAsset) => {
        if (cancelled || !preparedAsset) return null;
        setPrefetchedBrdDocument(preparedAsset);
        setDocumentPrefetchStatus("ready");
        return preparedAsset;
      })
      .catch((err) => {
        if (cancelled) return null;
        console.error("Failed to prefetch technical specification document", err);
        setDocumentPrefetchStatus("error");
        return null;
      })
      .finally(() => {
        if (documentPrefetchPromiseRef.current === prefetchPromise) {
          documentPrefetchPromiseRef.current = null;
        }
      });
    documentPrefetchPromiseRef.current = prefetchPromise;

    return () => {
      cancelled = true;
    };
  }, [
    currentToken,
    effectiveTargetVersion,
    migrationJob?.job_id,
    migrationJob?.source_repo,
    migrationJob?.target_repo,
    repoAnalysis,
    repoUrl,
    selectedRepo?.name,
    selectedRepo?.url,
    selectedSourceVersion,
    setDocumentPrefetchStatus,
    setPrefetchedBrdDocument,
    technicalDocumentFallbackRepoName,
  ]);

  // Auto-fill target names for each migration approach until the user customizes them.
  useEffect(() => {
    setTargetRepoNamesByApproach((prev) => {
      let hasChanges = false;
      const next = { ...prev };

      (["fork", "branch", "local"] as MigrationApproachValue[]).forEach((approach) => {
        if (targetRepoNameEditedByApproach[approach]) {
          return;
        }

        const generatedValue = getAutoGeneratedTargetName(approach);
        if (next[approach] !== generatedValue) {
          next[approach] = generatedValue;
          hasChanges = true;
        }
      });

      return hasChanges ? next : prev;
    });
  }, [
    getAutoGeneratedTargetName,
    setTargetRepoNamesByApproach,
    targetRepoNameEditedByApproach,
  ]);

  useEffect(() => {
    if (sourceAlreadyAtLatestSupportedVersion) {
      if (selectedTargetVersion !== selectedSourceVersion) {
        setSelectedTargetVersion(selectedSourceVersion);
      }
      if (targetVersionRequiredError) {
        setTargetVersionRequiredError(false);
      }
      return;
    }

    if (!selectedTargetVersion || targetVersions.length === 0) {
      return;
    }

    const isStillValid = availableTargetVersions.some((version) => version.value === selectedTargetVersion);
    if (!isStillValid) {
      setSelectedTargetVersion("");
    }
  }, [
    availableTargetVersions,
    selectedSourceVersion,
    selectedTargetVersion,
    setSelectedTargetVersion,
    setTargetVersionRequiredError,
    sourceAlreadyAtLatestSupportedVersion,
    targetVersionRequiredError,
    targetVersions.length,
  ]);

  useEffect(() => {
    const jobId = migrationJob?.job_id;

    if (
      step < 5 ||
      step > 6 ||
      !jobId ||
      isTerminalMigrationStatus(migrationJob?.status)
    ) {
      if (migrationPollingTimerRef.current) {
        clearTimeout(migrationPollingTimerRef.current);
        migrationPollingTimerRef.current = null;
      }
      migrationPollingInFlightRef.current = false;
      migrationPollingErrorCountRef.current = 0;
      return;
    }

    let cancelled = false;

    const clearScheduledPoll = () => {
      if (migrationPollingTimerRef.current) {
        clearTimeout(migrationPollingTimerRef.current);
        migrationPollingTimerRef.current = null;
      }
    };

    const scheduleNextPoll = (delayMs: number) => {
      clearScheduledPoll();
      migrationPollingTimerRef.current = window.setTimeout(() => {
        void pollSummary();
      }, delayMs);
    };

    const pollSummary = async () => {
      if (cancelled || migrationPollingInFlightRef.current) {
        return;
      }

      migrationPollingInFlightRef.current = true;

      try {
        const summary = await getMigrationStatusSummary(jobId);
        if (cancelled) {
          return;
        }

        migrationPollingErrorCountRef.current = 0;
        setError("");
        setMigrationJob((prev) => mergeMigrationSummaryIntoJob(prev, summary));
        getMigrationLogs(summary.job_id)
          .then((logs) => {
            if (cancelled) return;
            const nextLogs = logs.logs || [];
            setMigrationLogs(nextLogs);
            setMigrationJob((prev) =>
              prev ? { ...prev, migration_log: nextLogs } : prev
            );
          })
          .catch(() => undefined);

        const isTerminal = isTerminalMigrationStatus(summary.status);
        if (summary.status === "completed") {
          setMigrationDetailLoadedJobId(null);
          setStep(7);
        }

        if (isTerminal) {
          clearScheduledPoll();
          return;
        }

        scheduleNextPoll(getMigrationPollingDelayMs(summary.status, summary.started_at));
      } catch (err) {
        if (cancelled) {
          return;
        }

        if (err instanceof ApiError && err.status === 404 && err.code === "MIGRATION_JOB_NOT_FOUND") {
          setMigrationJob((prev) =>
            prev
              ? {
                  ...prev,
                  status: "failed",
                  current_step: "Migration session expired",
                }
              : prev
          );
          setError(
            "Migration status is no longer available. The backend likely restarted and lost the in-memory job state. Please restart the migration."
          );
          clearScheduledPoll();
          return;
        }

        migrationPollingErrorCountRef.current += 1;
        const retryDelayMs = Math.min(15000, 2000 * migrationPollingErrorCountRef.current);
        setError("Failed to fetch migration status.");
        scheduleNextPoll(retryDelayMs);
      } finally {
        migrationPollingInFlightRef.current = false;
      }
    };

    scheduleNextPoll(0);

    return () => {
      cancelled = true;
      clearScheduledPoll();
      migrationPollingInFlightRef.current = false;
    };
  }, [migrationJob?.job_id, migrationJob?.status, setMigrationJob, setMigrationLogs, step]);

  /* useEffect(() => {
      
      // Check if migration appears to be stuck (same status for > 30 seconds)
      stuckCheckInterval = setInterval(() => {
        const timeSinceLastUpdate = Date.now() - lastUpdateTime;
        if (timeSinceLastUpdate > 30000 && migrationJob?.status === "cloning") {
          setError("Warning: migration appears to be stuck on cloning. This may be due to a large repository or network issues. Please wait a bit longer or restart the migration.");
        }
      }, 15000);
    }
    
    return () => { 
      if (interval) clearInterval(interval);
      if (stuckCheckInterval) clearInterval(stuckCheckInterval);
    };
    }, [step, migrationJob?.job_id, migrationJob?.status]);
  */
  useEffect(() => {
      if ((step === 5 || step === 6) && migrationJob?.status === "completed") {
        setStep(7);
      }
    }, [step, migrationJob?.status]);

  const buildMigrationRequest = useCallback(() => {
    const repoName = sourceRepositoryName;
    const finalTargetRepoName = targetRepoName.trim() || getAutoGeneratedTargetName(currentMigrationApproach, repoName);

    const detectPlatform = (url: string) => {
      if (url.includes("gitlab.com")) return "gitlab";
      if (url.includes("github.com")) return "github";
      return "github";
    };

    return {
      source_repo_url: selectedRepo?.url || repoUrl,
      target_repo_name: finalTargetRepoName,
      platform: detectPlatform(selectedRepo?.url || repoUrl),
      source_java_version: userSelectedVersion || selectedSourceVersion,
      target_java_version: effectiveTargetVersion,
      token: currentToken,
      github_token: currentToken,
      build_tool: repoAnalysis?.build_tool || null,
      migration_approach: migrationApproach,
      conversion_types: selectedConversions,
      run_tests: runTests,
      use_llm_tests: runTests && useLLMTests,
      llm_test_provider: selectedLLMProvider,
      run_sonar: runSonar,
      run_fossa: runFossa,
      fix_business_logic: fixBusinessLogic,
      functional_test_method: functionalTestToolMethod.length > 0 ? functionalTestToolMethod : undefined,
    };
  }, [
    sourceRepositoryName,
    targetRepoName,
    getAutoGeneratedTargetName,
    currentMigrationApproach,
    selectedRepo?.url,
    repoUrl,
    userSelectedVersion,
    selectedSourceVersion,
    effectiveTargetVersion,
    currentToken,
    repoAnalysis?.build_tool,
    migrationApproach,
    selectedConversions,
    runTests,
    useLLMTests,
    selectedLLMProvider,
    runSonar,
    runFossa,
    fixBusinessLogic,
    functionalTestToolMethod,
  ]);

  useEffect(() => {
    if (step !== 4 || !effectiveTargetVersion || (!selectedRepo && !repoUrl)) {
      return;
    }

    let cancelled = false;

    previewMigration(buildMigrationRequest())
      .then((preview) => {
        if (cancelled) return;
        setMigrationPreview(preview);
        const previewCodeChanges = buildCodeChangesFromPreviewDiffs(preview.file_diffs || []);
        setCodeChanges(previewCodeChanges);
        setSelectedDiffFile((current) => current ?? previewCodeChanges[0]?.filePath ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setMigrationPreview(null);
        setCodeChanges([]);
        setSelectedDiffFile(null);
      })

    return () => {
      cancelled = true;
    };
  }, [
    buildMigrationRequest,
    effectiveTargetVersion,
    currentToken,
    fixBusinessLogic,
    migrationApproach,
    repoUrl,
    runFossa,
    runSonar,
    runTests,
    selectedConversions,
    selectedRepo,
    selectedSourceVersion,
    selectedTargetVersion,
    setCodeChanges,
    setMigrationPreview,
    setSelectedDiffFile,
    step,
    targetRepoName,
    targetRepoTimestamp,
    userSelectedVersion,
  ]);

  const handleStartMigration = () => {
    if (!selectedRepo && !repoUrl) {
      setError("Please select a repository or enter a repository URL");
      return;
    }

    if (!effectiveTargetVersion) {
      setError("Please select a target Java version before starting the migration.");
      return;
    }

    // Require at least one analysis tool selected before starting migration
    // if (!runSonar && !runFossa) {
    //   setError("Please select SonarQube or FOSSA before starting migration.");
    //   return;
    // }

    setLoading(true);
    setError("");
    setMigrationLogs([]);
    setMigrationJob(null);
    setMigrationDetailLoadedJobId(null);
    setStep(5);

    const migrationRequest = buildMigrationRequest();

    startMigration(migrationRequest)
      .then((job) => {
        setMigrationJob(job);
        setMigrationDetailLoadedJobId(null);

        if (job.status === "completed") {
          setStep(7);
          getMigrationLogs(job.job_id).then((logs) => setMigrationLogs(logs.logs || []));
          return;
        }

        setStep(5); // Go to Migration Progress step
      })
      .catch((err) => {
        console.error("Migration error:", err);
        setMigrationJob(null);
        setStep(4);
        setError(err.message || "Failed to start migration.");
        setLoading(false);
      })
      .finally(() => setLoading(false));
  };

  const resetWizard = () => {
    setStep(1);
    setMaxVisitedIndicatorStep(1);
    setRepoUrl("");
    setSelectedRepo(null);
    setRepoAnalysis(null);
    setRepoFiles([]);
    setCurrentPath("");
    setTargetRepoNamesByApproach({ fork: "", branch: "", local: "" });
    setTargetRepoNameEditedByApproach({ fork: false, branch: false, local: false });
    setTargetRepoTimestamp(generateRepoTimestamp());
    setSelectedSourceVersion("8");
    setSelectedTargetVersion("17");
    setSelectedConversions(["java_version"]);
    setRunTests(true);
    setRunSonar(false);
    setRunFossa(false);
    setLoading(false);
    setAnalysisLoading(false);
    setMigrationJob(null);
    setMigrationDetailLoadedJobId(null);
    setFossaResult(null);
    setFossaLoading(false);
    setMigrationPreview(null);
    setMigrationLogs([]);
    setError("");
    setTargetVersionRequiredError(false);
    setTargetRepoNameError("");
    setMigrationApproach("fork");
    setRiskLevel("");
    setSelectedFrameworks([]);
    setIsJavaProject(null);
    setSelectedFile(null);
    setFileContent("");
    setEditedContent("");
    setIsEditing(false);
    setPathHistory([""]);
    setShowFileExplorer(true);
    // Reset high-risk project states
    setIsHighRiskProject(false);
    setHighRiskConfirmed(false);
    setSuggestedJavaVersion("17");
    setDetectedFrameworks([]);
    setViewingFrameworkFile(null);
   // Reset code diff states
    setCodeChanges([]);
    setSelectedDiffFile(null);
    setShowCodeChanges(true);
    setVisibleReportDiffCount(REPORT_DIFFS_PAGE_SIZE);

    clearWizardStorage();
  };

  const renderStepIndicator = () => (
    <div style={styles.stepIndicator}>
      {MIGRATION_STEPS.map((s, index) => {
        const isCompleted = currentIndicatorStep > s.id;
        const isActive = currentIndicatorStep === s.id;
        const isUnlocked = s.id <= maxVisitedIndicatorStep;

        return (
        <React.Fragment key={s.id}>
          <div 
            style={{ 
              display: "flex", 
              flexDirection: "column", 
              alignItems: "center", 
              gap: 8,
              opacity: 1,
              cursor: isUnlocked && !isActive ? "pointer" : "default",
              transition: "all 0.3s ease"
            }} 
            onClick={() => isUnlocked && !isActive && setStep(s.id)}
          >
            <div
              className={`wizard-step-circle${isCompleted ? " is-complete" : isActive ? " is-active" : ""}`}
              style={buildWizardAccentVars(s.accent)}
            >
              {s.icon}
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ 
                fontWeight: isActive ? 700 : 500, 
                fontSize: 13, 
                color: isActive ? "#3b82f6" : isCompleted ? "#22c55e" : "#64748b",
                marginBottom: 2
              }}>
                {s.name}
              </div>
              <div style={{ 
                fontSize: 10, 
                color: isActive ? "#64748b" : "#94a3b8",
                maxWidth: 100,
                lineHeight: 1.3
              }}>
                {s.description}
              </div>
            </div>
          </div>
          {/* Connector Line */}
          {index < MIGRATION_STEPS.length - 1 && (
            <div style={{
              flex: 1,
              height: 3,
              backgroundColor: currentIndicatorStep > s.id ? "#22c55e" : "#e5e7eb",
              marginTop: -50,
              marginLeft: -10,
              marginRight: -10,
              borderRadius: 2,
              transition: "background-color 0.3s ease"
            }} />
          )}
        </React.Fragment>
        );
      })}
    </div>
  );


  return {
    step,
    setStep,
    error,
    setError,
    selectedRepo,
    setSelectedRepo,
    setRepoUrl,
    repoUrl,
    strategyAssistantContext,
    connectState,
    setRepoAnalysis,
    discoveryState,
    currentToken,
    isLocalRepoRef,
    extractLocalRepoPath,
    sourceVersionStatus,
    applyDetectedSourceVersion,
    setUserSelectedVersion,
    documentGenerationLoading,
    conversionDecision,
    setConversionDecision,
    showFolderStructure,
    setShowFolderStructure,
    handleCheckMicroserviceEligibility,
    handleGenerateBrdDocument,
    handleOpenFrameworkFile,
    isDiscoveryPending,
    formattedAnalysisElapsed,
    formattedAnalysisCompleted,
    detectedJavaStructureLabel,
    technicalSpecificationButtonLabel,
    technicalSpecificationHelperText,
    strategyState,
    repoAnalysis,
    riskLevel,
    buildToolDisplayLabel,
    renderCategorizedDependencies,
    sourceAlreadyAtLatestSupportedVersion,
    effectiveTargetVersion,
    handleTargetVersionChange,
    targetVersions,
    versionRecommendationLoading,
    versionRecommendationError,
    versionRecommendation,
    versionRecommendationCards,
    migrationApproachOptions,
    targetRepoName,
    handleTargetRepoNameChange,
    getAutoGeneratedTargetName,
    targetRepositoryHost,
    targetRepositoryOwner,
    continueWithTargetVersion,
    modernizationState,
    functionalTestToolMethod,
    setFunctionalTestToolMethod,
    functionalTestingTools,
    hasUI,
    localApiTestCases,
    loading,
    handleStartMigration,
    migrationJob,
    migrationTimerNow,
    animationProgress,
    runFossa,
    runSonar,
    runTests,
    selectedSourceVersion,
    resetWizard,
    resultExecState,
    selectedLLMProvider,
    useLLMTests,
    renderStepIndicator,
  };
}

