/**
 * Cross-feature domain DTOs shared by connect/discovery/strategy/modernization.
 */

export interface RepoInfo {
  name: string;
  full_name: string;
  url: string;
  default_branch: string;
  language: string | null;
  description: string | null;
}

export interface RepoFile {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size: number;
  url: string;
}

export interface DependencyInfo {
  group_id: string;
  artifact_id: string;
  current_version: string;
  new_version: string | null;
  status: string;
}

export interface DetectedFramework {
  name: string;
  path: string;
  type: string;
}

/**
 * Spring -> Spring Boot conversion eligibility, computed by the backend from
 * the actual cloned-and-analyzed repository (never from the URL, repo name,
 * or mock data). Drives whether the Strategy step's conversion card is
 * enabled/disabled and what it displays.
 */
export interface SpringBootConversionEligibility {
  repositoryAnalyzed: boolean;
  javaMigrationEligible: boolean;
  javaMigrationReason: string;
  springDetected: boolean;
  springBootDetected: boolean;
  springVersion: string | null;
  springBootVersion: string | null;
  buildTool: string;
  springBootConversionEligible: boolean;
  springBootUpgradeEligible: boolean;
  eligibilityReason: string;
}

export interface RepoAnalysis {
  name: string;
  full_name: string;
  default_branch: string;
  language: string | null;
  build_tool: string | null;
  java_version: string | null;
  java_version_from_build?: string | null;
  // List of discovered Java source file paths
  java_files?: string[];
  jsp_files?: string[];
  jsf_files?: string[];
  jsp_count?: number;
  jsf_count?: number;
  detected_frameworks?: DetectedFramework[];
  has_tests: boolean;
  test_file_count?: number;
  unit_test_file_count?: number;
  functional_test_files?: {
    count: number;
    files: { path: string; tool: string }[];
    tools_detected: string[];
  };
  test_file_breakdown?: {
    tool: string;
    label: string;
    count: number;
    type: "unit" | "functional";
    files: string[];
  }[];
  test_file_list?: { path: string; tool: string }[];
  dependencies: DependencyInfo[];
  api_endpoints: { path: string; method: string; file: string }[];
  structure: {
    has_pom_xml: boolean;
    has_build_gradle: boolean;
    has_src_main: boolean;
    has_src_test: boolean;
    has_build_gradle_kts: boolean;
    jsp_count?: number;
    jsf_count?: number;
  };
  // backend-provided microservice eligibility assessment
  microservice_eligibility?: MicroserviceEligibilityResult;
  // backend-provided Spring -> Spring Boot conversion eligibility (Discovery stage)
  spring_boot_eligibility?: SpringBootConversionEligibility;
}

export interface MicroserviceScoreBreakdown {
  name: string;
  score: number;
  weight: number;
  summary: string;
}

export interface MicroserviceServiceCandidate {
  name: string;
  packages: string[];
  evidence: string[];
  scaling_signals: string[];
  external_integrations: string[];
  transactional: boolean;
}

export interface MicroserviceDetailedEligibilityReport {
  project_structure: string[];
  package_structure: string[];
  module_boundaries: string[];
  dependency_coupling: string[];
  database_access_patterns: string[];
  communication_analysis: string[];
  deployment_independence: string[];
  scalability_indicators: string[];
}

export interface MicroserviceAnalysisDiagnostics {
  java_files_total: number;
  java_files_scanned: number;
  package_count: number;
  detected_modules: number;
  cross_module_dependencies: number;
  circular_dependencies: number;
  external_integration_count: number;
  scan_truncated: boolean;
}

export interface MicroserviceEligibilityResult {
  projectName: string;
  score: number;
  eligibility: string;
  recommendedArchitecture: string;
  summary: string;
  strengths: string[];
  risks: string[];
  serviceCandidates: MicroserviceServiceCandidate[];
  couplingIssues: string[];
  databaseConcerns: string[];
  scalingCandidates: string[];
  recommendedMigrationStrategy: string[];
  observations: string[];
  scoreBreakdown?: MicroserviceScoreBreakdown[];
  detailedEligibilityReport?: MicroserviceDetailedEligibilityReport;
  architecturalObservations?: string[];
  analysisDiagnostics?: MicroserviceAnalysisDiagnostics;
  reportGeneratedAt?: string;
  metadata?: Record<string, unknown>;
}
