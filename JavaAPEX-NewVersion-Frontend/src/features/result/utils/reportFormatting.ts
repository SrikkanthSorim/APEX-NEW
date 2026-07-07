import type { FossaScanResult } from "../services/resultService";
import type { SonarIssueDetail, SonarHotspotDetail } from "../services/resultService";

export type SonarFindingFilter = "all" | "bugs" | "vulnerabilities" | "code_smells" | "security_hotspots";
export type CodeSmellSeverityFilter = "all" | "low" | "medium" | "high" | "blocker";

export const SONAR_FINDINGS_PAGE_SIZE = 12;
export const REPORT_DEPENDENCIES_PAGE_SIZE = 7;

export interface TestSummaryMetrics {
  repo_total_files?: number;
  existing_test_files?: number;
  new_test_files?: number;
  existing_test_cases?: number;
  generated_test_cases?: number;
  total_test_cases?: number;
  java_migration_version?: string;
  [key: string]: unknown;
}

export const getTestSummaryMetrics = (value: unknown): TestSummaryMetrics | null => {
  if (!value || typeof value !== "object") {
    return null;
  }

  return value as TestSummaryMetrics;
};

export const getRepositoryLink = (repoValue: string | null | undefined) => {
  if (!repoValue) return null;
  if (repoValue.startsWith("local://")) return null;
  return repoValue.startsWith("http") ? repoValue : `https://github.com/${repoValue}`;
};

export const getFossaVulnerabilityTotal = (report: FossaScanResult | null | undefined, fallbackValue: number = 0) => {
  if (report?.details_available === false && report?.issue_count != null) return null;
  const value = report?.vulnerabilities;
  if (typeof value === "number") return value;
  if (value && typeof value === "object") {
    return Object.values(value).reduce((sum, item) => sum + (Number(item) || 0), 0);
  }
  return fallbackValue;
};

export const getFossaLicenseIssueCount = (report: FossaScanResult | null | undefined, fallbackValue: number = 0) => {
  if (report?.details_available === false && report?.issue_count != null) return null;
  if (typeof report?.license_issues === "number") return report.license_issues;
  if (report?.licenses && typeof report.licenses === "object") {
    return Number(report.licenses.UNKNOWN || 0);
  }
  return fallbackValue;
};

export const getFossaSeverityCounts = (report: FossaScanResult | null | undefined) => {
  if (!report?.vulnerabilities || typeof report.vulnerabilities !== "object") {
    return null;
  }
  return {
    critical: Number(report.vulnerabilities.critical || 0),
    high: Number(report.vulnerabilities.high || 0),
    medium: Number(report.vulnerabilities.medium || 0),
    low: Number(report.vulnerabilities.low || 0),
  };
};

export const getFossaScanModeLabel = (mode: string | null | undefined) => {
  switch (mode) {
    case "real":
      return "Real scan";
    case "real_limited":
      return "Real scan, limited details";
    case "simulated":
      return "Simulated result";
    case "unavailable":
      return "Unavailable";
    case "pending":
      return "Pending";
    default:
      return mode || "N/A";
  }
};

export const formatSonarTimestamp = (value: string | null | undefined) => {
  if (!value) return "N/A";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

export const getSonarSeverityColor = (severity: string | null | undefined) => {
  const normalized = (severity || "").toUpperCase();
  if (normalized === "BLOCKER" || normalized === "CRITICAL") return { background: "#fee2e2", color: "#991b1b" };
  if (normalized === "MAJOR" || normalized === "HIGH") return { background: "#ffedd5", color: "#9a3412" };
  if (normalized === "MINOR" || normalized === "MEDIUM") return { background: "#fef3c7", color: "#92400e" };
  return { background: "#e0f2fe", color: "#1d4ed8" };
};

export const getSonarStatusColor = (status: string | null | undefined) => {
  const normalized = (status || "").toUpperCase();
  if (normalized === "OPEN" || normalized === "TO_REVIEW") return { background: "#fee2e2", color: "#991b1b" };
  if (normalized === "CONFIRMED" || normalized === "IN_REVIEW") return { background: "#ffedd5", color: "#9a3412" };
  if (normalized === "ACCEPTED" || normalized === "SAFE") return { background: "#dcfce7", color: "#166534" };
  return { background: "#f1f5f9", color: "#475569" };
};

export const getSonarIssueSeverityValue = (issue: SonarIssueDetail | SonarHotspotDetail) =>
  ((issue as SonarHotspotDetail).vulnerability_probability ??
    (issue as SonarIssueDetail).severity ??
    null);

export const getCodeSmellSeverityBucket = (
  severity: string | null | undefined
): Exclude<CodeSmellSeverityFilter, "all"> => {
  const normalized = (severity || "").toUpperCase();
  if (normalized === "BLOCKER") return "blocker";
  if (normalized === "CRITICAL") return "high";
  if (normalized === "MAJOR") return "medium";
  return "low";
};
