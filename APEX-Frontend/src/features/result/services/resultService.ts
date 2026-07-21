import { API_BASE_URL, APP_BASE_URL } from "@/services/config/env";
import { ApiError, performRequest, requestJson, requestBlob, readErrorDetail } from "@/services/http/client";
import type { DependencyInfo } from "@/shared/types/domain";
import type { PreviewFileDiff, MigrationRequest } from "@/features/modernization/services/modernizationService";

export interface MigrationIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  status: 'detected' | 'fixed' | 'manual_review' | 'ignored';
  category: string;
  message: string;
  file_path: string;
  line_number: number | null;
  column: number | null;
  code_snippet: string | null;
  suggested_fix: string | null;
  fixed_at: string | null;
  conversion_type: string;
}

export interface SonarIssueDetail {
  key?: string | null;
  type?: string | null;
  severity?: string | null;
  component?: string | null;
  line?: number | null;
  message?: string | null;
  rule?: string | null;
  status?: string | null;
  resolution?: string | null;
  effort?: string | null;
  debt?: string | null;
  author?: string | null;
  tags?: string[];
  creation_date?: string | null;
  update_date?: string | null;
}

export interface SonarHotspotDetail {
  key?: string | null;
  component?: string | null;
  line?: number | null;
  message?: string | null;
  rule?: string | null;
  status?: string | null;
  security_category?: string | null;
  vulnerability_probability?: string | null;
  author?: string | null;
  creation_date?: string | null;
  update_date?: string | null;
}

export interface SonarReport {
  quality_gate?: string | null;
  bugs?: number;
  vulnerabilities?: number;
  code_smells?: number;
  coverage?: number;
  duplications?: number;
  security_hotspots?: number;
  analysis_url?: string | null;
  bug_details?: SonarIssueDetail[];
  vulnerability_details?: SonarIssueDetail[];
  code_smell_details?: SonarIssueDetail[];
  security_hotspot_details?: SonarHotspotDetail[];
  [key: string]: unknown;
}

export interface FossaVulnerabilityDetail {
  id: string;
  title: string;
  severity: string;
  package?: string | null;
  package_version?: string | null;
  fixed_version?: string | null;
  description?: string | null;
  reference?: string | null;
}

export interface FossaScanResult {
  scan_mode?: string | null;
  real_scan?: boolean;
  simulated?: boolean;
  ready?: boolean;
  details_available?: boolean;
  permission_limited?: boolean;
  compliance_status?: string | null;
  total_dependencies?: number | null;
  issue_count?: number | null;
  license_issues?: number | null;
  licenses?: Record<string, number>;
  vulnerabilities?: Record<string, number> | number | null;
  vulnerability_details?: FossaVulnerabilityDetail[];
  dependencies?: Array<Record<string, unknown>>;
  outdated_dependencies?: number | null;
  analysis_url?: string | null;
  error_message?: string | null;
  enrichment_error_message?: string | null;
  raw_summary?: string | null;
}

export interface FunctionalTesting {
      status?: string;
      application_type?: string;
      recommended_tools?: string[];
      allocated_port?: number;
      base_url?: string;
      generated_files?: string[];
      test_cases?: Array<{
        name?: string;
        tool?: string;
        type?: string;
        method?: string;
        path?: string;
        route?: string;
        schema?: string;
        expectedStatus?: number;
        status?: string;
        validation_reason?: string;
        source_file?: string;
        controller?: string;
      }>;
      planning?: Record<string, unknown>;
      total_tests?: number;
      execution_mode?: string;
      fallback_reason?: string;
      container_required?: boolean;
      container_available?: boolean;
      app_start_command?: string | null;
      runner_commands?: Array<Record<string, unknown>>;
      execution?: {
        status?: string;
        message?: string;
        tests_run?: number;
        tests_passed?: number;
        tests_failed?: number;
        startup?: Record<string, unknown>;
        runners?: Array<{
          tool?: string;
          status?: string;
          executed?: boolean;
          tests_run?: number;
          tests_passed?: number;
          tests_failed?: number;
          message?: string;
          output_tail?: string;
          execution_mode?: string;
          report_available?: boolean;
          report_tool?: string;
          report_type?: string;
        }>;
      };
      message?: string;
}

export interface MigrationResult {
  job_id: string;
  status: string;
  source_repo: string;
  target_repo: string | null;
  source_java_version: string;
  target_java_version: string;
  conversion_types: string[];
  started_at: string;
  worker_started_at?: string | null;
  completed_at: string | null;
  progress_percent: number;
  current_step: string;
  dependencies: DependencyInfo[];
  files_modified: number;
  issues_fixed: number;
  api_endpoints_validated: number;
  api_endpoints_working: number;
  sonar_quality_gate: string | null;
  sonar_bugs: number;
  sonar_vulnerabilities: number;
  sonar_code_smells: number;
  sonar_coverage: number;
  sonar_duplications?: number;
  sonar_security_hotspots?: number;
  sonar_scan_mode?: string | null;
  sonar_real_scan?: boolean;
  sonar_analysis_url?: string | null;
  sonar_error_message?: string | null;
  sonar_report?: SonarReport | null;
  tests_run: number;
  tests_passed: number;
  tests_failed: number;
  test_summary?: string | null;
  test_insights?: string[];
  test_llm_model?: string | null;
  bl_coverage?: number;
  test_pipeline?: {
    provider: string;
    project_kind: string;
    generated_tests_relative: string;
    test_strategy?: string | null;
    existing_tests_detected?: number;
    existing_test_files?: string[];
    migrated_test_files?: string[];
    generated_test_files: string[];
    test_summary_metrics?: Record<string, unknown> | null;
    runner: Record<string, unknown>;
    functional_testing?: FunctionalTesting | null;
    manual_test_plan_path?: string | null;
    migration_patch_path?: string | null;
    deepeval_result?: Record<string, unknown> | null;
    garak_result?: Record<string, unknown> | null;
    coverage_result?: Record<string, unknown> | null;
  } | null;
  functional_pipeline?: FunctionalTesting | null;
  // FOSSA scan results (optional)
  fossa_policy_status?: string | null;
  fossa_total_dependencies?: number;
  fossa_license_issues?: number;
  fossa_vulnerabilities?: number;
  fossa_outdated_dependencies?: number;
  fossa_scan_mode?: string | null;
  fossa_real_scan?: boolean;
  fossa_analysis_url?: string | null;
  fossa_error_message?: string | null;
  fossa_report?: FossaScanResult | null;
  error_message: string | null;
  migration_log: string[];
  file_diffs?: PreviewFileDiff[];
  issues: MigrationIssue[];
  total_errors: number;
  total_warnings: number;
  errors_fixed: number;
  warnings_fixed: number;
  dependency_count?: number;
  // --- migration engine report fields (OpenRewrite recipe selection, dependency/import changes) ---
  recipes_executed?: string[];
  recipe_selection_reasons?: string[];
  build_modernization?: string[];
  dependency_upgrades?: Array<{ coordinate: string; oldVersion: string | null; newVersion: string }>;
  used_fallback?: boolean;
  already_compatible?: boolean;
  build_status?: string | null;
  build_success?: boolean | null;
  migration_summary?: string;
  modified_files?: string[];
  import_changes?: Array<{ file: string; added: string[]; removed: string[] }>;
  source_changes?: Array<{ file: string; linesChanged: number }>;
  retry_attempts?: Array<{ attempt: number; rootCause: string; recipesAdded: string[]; buildStatus: string }>;
  spring_source_framework?: string;
  spring_target_framework?: string;
  spring_boot_version_before?: string | null;
  spring_boot_version_after?: string | null;
  spring_conversion_requested?: boolean;
  spring_conversion_supported?: boolean | null;
  spring_conversion_note?: string | null;
}

export interface MigrationJobSummary {
  job_id: string;
  status: string;
  source_repo: string;
  target_repo: string | null;
  source_java_version: string;
  target_java_version: string;
  conversion_types: string[];
  started_at: string;
  worker_started_at?: string | null;
  completed_at: string | null;
  progress_percent: number;
  current_step: string;
  files_modified: number;
  issues_fixed: number;
  api_endpoints_validated: number;
  api_endpoints_working: number;
  tests_run: number;
  tests_passed: number;
  tests_failed: number;
  sonar_quality_gate?: string | null;
  sonar_bugs: number;
  sonar_vulnerabilities: number;
  sonar_code_smells: number;
  sonar_coverage: number;
  sonar_duplications?: number;
  sonar_security_hotspots?: number;
  sonar_scan_mode?: string | null;
  sonar_real_scan?: boolean;
  sonar_analysis_url?: string | null;
  sonar_error_message?: string | null;
  fossa_policy_status?: string | null;
  fossa_total_dependencies?: number;
  fossa_license_issues?: number;
  fossa_vulnerabilities?: number;
  fossa_outdated_dependencies?: number;
  fossa_scan_mode?: string | null;
  fossa_real_scan?: boolean;
  fossa_analysis_url?: string | null;
  fossa_error_message?: string | null;
  error_message: string | null;
  total_errors: number;
  total_warnings: number;
  errors_fixed: number;
  warnings_fixed: number;
  dependency_count: number;
  api_endpoint_count: number;
  issue_count: number;
  log_entry_count: number;
  file_diff_count: number;
  has_test_pipeline: boolean;
  has_sonar_report: boolean;
  has_fossa_report: boolean;
  has_testcase_doc: boolean;
  has_clone_path: boolean;
  // --- migration engine report fields ---
  recipes_executed?: string[];
  recipe_selection_reasons?: string[];
  build_modernization?: string[];
  dependency_upgrades?: Array<{ coordinate: string; oldVersion: string | null; newVersion: string }>;
  used_fallback?: boolean;
  already_compatible?: boolean;
  build_status?: string | null;
  build_success?: boolean | null;
  migration_summary?: string;
  retry_attempts?: Array<{ attempt: number; rootCause: string; recipesAdded: string[]; buildStatus: string }>;
  spring_source_framework?: string;
  spring_target_framework?: string;
  spring_boot_version_before?: string | null;
  spring_boot_version_after?: string | null;
  spring_conversion_requested?: boolean;
  spring_conversion_supported?: boolean | null;
  spring_conversion_note?: string | null;
}

// Start migration
// Start Migration (Step 4) — OpenRewrite migration + publish to Javaapex.
// Runs under the layered backend at /api/v1/migration/{jobId}/... and reuses the
// Connect jobId so all stages share one workspace.
export async function startMigration(jobId: string, request: MigrationRequest): Promise<MigrationResult> {
  return requestJson<MigrationResult>(`/v1/migration/${jobId}/start`, "Failed to start migration", {
    method: "POST",
    body: request,
  });
}

// Get lightweight migration status
export async function getMigrationStatus(jobId: string): Promise<MigrationJobSummary> {
  return requestJson<MigrationJobSummary>(`/v1/migration/${jobId}/summary`, "Failed to get migration status");
}

export async function getMigrationDetail(jobId: string): Promise<MigrationResult> {
  return requestJson<MigrationResult>(`/v1/migration/${jobId}/detail`, "Failed to get migration detail");
}

export async function getMigrationStatusSummary(jobId: string): Promise<MigrationJobSummary> {
  return requestJson<MigrationJobSummary>(`/v1/migration/${jobId}/summary`, "Failed to get migration summary");
}

// Get migration logs
export async function getMigrationLogs(jobId: string): Promise<{ job_id: string; logs: string[] }> {
  return requestJson<{ job_id: string; logs: string[] }>(
    `/v1/migration/${jobId}/logs`,
    "Failed to get migration logs"
  );
}

// Get FOSSA scan results for a migration (if available)
export async function getMigrationFossa(jobId: string): Promise<{
  job_id: string;
  fossa: FossaScanResult;
}> {
  const data = await requestJson<{ fossa?: FossaScanResult } | FossaScanResult>(
    `/v1/migration/${jobId}/fossa`,
    "Failed to get FOSSA results"
  );
  return {
    job_id: jobId,
    fossa:
      "fossa" in data && data.fossa
        ? data.fossa
        : (data as FossaScanResult),
  };
}

// Download migrated project as ZIP
export async function downloadMigratedProject(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/download-zip`, "Failed to download migrated project");
}

// Download migration report
export async function downloadMigrationReport(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/report`, "Failed to download migration report");
}

// Download testcase + change report (Markdown)
export async function downloadTestcaseDoc(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/testcase-doc`, "Failed to download testcase doc");
}

export async function downloadTestcaseDocx(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/testcase-docx`, "Failed to download testcase docx");
}

// Download testcase + change report (HTML)
export async function downloadTestcaseReport(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/testcase-report`, "Failed to download testcase report");
}

export async function downloadUnitTestReport(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/unit-test-report`, "Failed to download unit test report");
}

export async function downloadSonarReportPdf(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/sonar-report-pdf`, "Failed to download Sonar PDF report");
}

export async function downloadJMeterPlan(jobId: string, baseUrl: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/jmeter`, "Failed to download JMeter plan", {
    query: { base_url: baseUrl },
  });
}

export async function rerunMigrationTests(
  jobId: string,
  llmProvider: string = "huggingface",
  useLlmTests: boolean = true
): Promise<{
  job_id: string;
  tests_run: number;
  tests_passed: number;
  tests_failed: number;
  test_summary?: string | null;
  test_insights?: string[];
  test_llm_model?: string | null;
}> {
  return requestJson<{
    job_id: string;
    tests_run: number;
    tests_passed: number;
    tests_failed: number;
    test_summary?: string | null;
    test_insights?: string[];
    test_llm_model?: string | null;
  }>(`/migration/${jobId}/rerun-tests`, "Failed to re-run tests", {
    method: "POST",
    query: {
      llm_provider: llmProvider,
      use_llm_tests: useLlmTests ? "true" : "false",
    },
  });
}

// List all migrations
export async function listMigrations(): Promise<MigrationJobSummary[]> {
  return requestJson<MigrationJobSummary[]>("/migrations", "Failed to list migrations");
}

export async function listMigrationSummaries(): Promise<MigrationJobSummary[]> {
  return requestJson<MigrationJobSummary[]>("/migrations/summary", "Failed to list migration summaries");
}

// Get available recipes
export async function getRecipes(): Promise<{ id: string; name: string; description: string }[]> {
  return requestJson<{ id: string; name: string; description: string }[]>(
    "/openrewrite/recipes",
    "Failed to fetch recipes"
  );
}

// Health check
export async function healthCheck(): Promise<{ status: string; timestamp: string }> {
  return requestJson<{ status: string; timestamp: string }>(
    "/health",
    "Failed to reach backend health endpoint",
    {
      baseUrl: APP_BASE_URL,
    }
  );
}

// ==================== HUGGING FACE LLM API FUNCTIONS ====================

export interface HuggingFaceBusinessLogicRequest {
  repo_url: string;
  token?: string;
  source_java_version: string;
  target_java_version: string;
  java_files?: string[];
}

export interface FileAnalysisResult {
  file_path: string;
  file_name: string;
  total_lines: number;
  issues: Array<{
    line_number: number;
    type: string;
    severity: 'high' | 'medium' | 'low';
    description: string;
    code_snippet?: string;
    suggested_fix?: string;
  }>;
  suggestions: string[];
  old_patterns_found: Array<{
    pattern: string;
    message: string;
    category: string;
    occurrences: number;
  }>;
}

export interface HuggingFaceBusinessLogicResponse {
  success: boolean;
  repo_url: string;
  analysis_type: string;
  source_version: string;
  target_version: string;
  files_analyzed: number;
  total_issues: number;
  total_old_patterns: number;
  file_results: FileAnalysisResult[];
  llm_available: boolean;
  model_used: string;
}

export interface HuggingFaceSonarResponse {
  success: boolean;
  repo_url: string;
  analysis_type: string;
  quality_gate: string;
  bugs: number;
  vulnerabilities: number;
  code_smells: number;
  coverage: number;
  duplications: number;
  issues: Array<{
    file_path: string;
    category: string;
    severity: string;
    message: string;
    line_number: number;
  }>;
  llm_insights: string[];
  llm_available: boolean;
  model_used: string;
}

export interface HuggingFaceFileSuggestionRequest {
  code_snippet: string;
  issue_description: string;
}

export interface HuggingFaceFileSuggestionResponse {
  success: boolean;
  original_code: string;
  issue_description: string;
  improved_code: string;
  llm_available: boolean;
}

export interface HuggingFaceStatusResponse {
  available: boolean;
  api_key_configured: boolean;
  models: Record<string, string>;
  timestamp: string;
}

// Hugging Face LLM Business Logic Analysis
export async function analyzeBusinessLogicWithLLM(
  request: HuggingFaceBusinessLogicRequest
): Promise<HuggingFaceBusinessLogicResponse> {
  return requestJson<HuggingFaceBusinessLogicResponse>(
    "/ai/huggingface/business-logic",
    "Failed to analyze business logic with LLM",
    {
      method: "POST",
      body: request,
    }
  );
}

// Hugging Face LLM SonarQube Analysis
export async function analyzeSonarWithLLM(
  repoUrl: string,
  token: string = ""
): Promise<HuggingFaceSonarResponse> {
  return requestJson<HuggingFaceSonarResponse>(
    "/ai/huggingface/sonar",
    "Failed to analyze code quality with LLM",
    {
      method: "POST",
      body: { repo_url: repoUrl, token },
    }
  );
}

// Get AI improvement suggestion for specific code
export async function getFileImprovementSuggestion(
  request: HuggingFaceFileSuggestionRequest
): Promise<HuggingFaceFileSuggestionResponse> {
  return requestJson<HuggingFaceFileSuggestionResponse>(
    "/ai/huggingface/file-suggestion",
    "Failed to get code improvement suggestion",
    {
      method: "POST",
      body: request,
    }
  );
}

// Get Hugging Face LLM service status
export async function getHuggingFaceStatus(): Promise<HuggingFaceStatusResponse> {
  return requestJson<HuggingFaceStatusResponse>(
    "/ai/huggingface/status",
    "Failed to get Hugging Face status"
  );
}

// Fetch the content of a single generated functional test file for viewing or download
export async function getFunctionalTestFileContent(jobId: string, path: string): Promise<string> {
  const response = await performRequest(`/migration/${jobId}/functional-test-file`, {
    query: { path },
  });
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiError(detail || "Failed to fetch functional test file", response.status, undefined, detail);
  }
  return response.text();
}

// Download all generated functional test files as a ZIP archive
export async function downloadFunctionalTestsZip(jobId: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/functional-tests-zip`, "Failed to download functional tests ZIP archive");
}

// Download a single functional test case file as a blob
export async function downloadFunctionalTestFile(jobId: string, path: string): Promise<Blob> {
  return requestBlob(`/migration/${jobId}/functional-test-file`, "Failed to download functional test file", {
    query: { path },
  });
}

// Build the URL for a Playwright/Selenium HTML report (opened in a new tab)
export function getFunctionalTestReportUrl(jobId: string, tool: string): string {
  return `${API_BASE_URL}/migration/${jobId}/functional-test-report/${tool.toLowerCase()}`;
}
