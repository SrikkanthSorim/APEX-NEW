import { requestJson } from "@/services/http/client";

export interface ConversionType {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
}

export interface PreviewFileChange {
  type: string;
  pattern?: string;
  replacement?: string;
  description: string;
  occurrences?: number;
}

export interface PreviewFileDiff {
  file_path: string;
  diff: string;
  change_count: number;
}

export interface MigrationPreview {
  repository: string;
  platform: string;
  source_version: string;
  target_version: string;
  conversions: string[];
  business_logic_fixes: boolean;
  summary: {
    files_to_modify: number;
    files_to_create: number;
    files_to_remove: number;
    total_changes: number;
  };
  changes: {
    files_to_modify: string[];
    files_to_create: string[];
    files_to_remove: string[];
    file_changes: Record<string, PreviewFileChange[]>;
    dependencies_to_update: Array<{
      dependency: string;
      current_version: string;
      new_version: string;
      status?: string;
    }>;
    issues_to_fix: Array<{
      type: string;
      severity: string;
      description: string;
      file: string;
    }>;
  };
  file_diffs: PreviewFileDiff[];
}

export interface MigrationRequest {
  source_repo_url: string;
  target_repo_name: string;
  migration_approach?: string;
  platform?: string;
  source_java_version: string;
  target_java_version: string;
  token?: string;
  github_token?: string;
  build_tool?: string | null;
  conversion_types: string[];
  email?: string;
  run_tests: boolean;
  use_llm_tests?: boolean;
  llm_test_provider?: string;
  run_sonar: boolean;
  run_fossa?: boolean;
  fix_business_logic: boolean;
  functional_test_method?: string[];
  functional_test_execution_mode?: string;
}

export interface FunctionalTestScopePreview {
  uiScopeHtml: string;
  apiScopeHtml: string;
  uiTestCount: number;
  apiTestCount: number;
  uiTestCases: {
    id: number;
    route: string;
    type: string;
    scenario: string;
    fields: string;
    actions: string;
    hasForm: boolean;
    hasTable: boolean;
  }[];
  apiTestCases: {
    id: number;
    method: string;
    path: string;
    controller: string;
    scenario: string;
    expectedStatus: number;
  }[];
}

export interface ToolRecommendationsResponse {
  recommendations: Record<string, { passage: string }>;
}

export interface UpdateJavaVersionResponse {
  success: boolean;
  file_path: string;
  java_version: string;
  message: string;
}

// Get available conversion types
export async function getConversionTypes(): Promise<ConversionType[]> {
  return requestJson<ConversionType[]>("/conversion-types", "Failed to fetch conversion types");
}

export async function previewMigration(request: MigrationRequest): Promise<MigrationPreview> {
  return requestJson<MigrationPreview>("/migration/preview", "Failed to preview migration changes", {
    method: "POST",
    body: request,
  });
}

/* -------------------------------------------------------------------------- */
/* Migration Config stage (Step 4) — POST /api/v1/migration-config/{jobId}     */
/*                                                                              */
/* Saves the chosen migration destination + options for the job. Migrated      */
/* repositories are published under the configured GitHub owner (Javaapex) for */
/* the "Create New Repository" mode. No repo creation / push happens here —     */
/* that is the Start Migration stage.                                           */
/* -------------------------------------------------------------------------- */

export type MigrationDestinationMode =
  | "CREATE_NEW_REPO"
  | "EXISTING_REPO_BRANCH"
  | "LOCAL_FOLDER";

export interface MigrationDestinationConfig {
  mode: MigrationDestinationMode;
  targetOwner?: string;
  targetHost?: string;
  targetRepoName?: string;
  targetRepoUrl?: string;
  targetBranch?: string;
  localFolder?: string;
}

export interface MigrationConfigPayload {
  destination: MigrationDestinationConfig;
  sourceRepoUrl?: string;
  sourceJavaVersion?: string;
  targetJavaVersion?: string;
  buildTool?: string | null;
  conversionTypes?: string[];
  options?: {
    runTests: boolean;
    runSonar: boolean;
    runFossa: boolean;
    fixBusinessLogic: boolean;
  };
}

export interface MigrationConfigResult {
  jobId: string;
  status: string;
  message: string;
  destination: MigrationDestinationConfig;
  nextStep: string;
}

export async function saveMigrationConfig(
  jobId: string,
  config: MigrationConfigPayload
): Promise<MigrationConfigResult> {
  return requestJson<MigrationConfigResult>(
    `/v1/migration-config/${encodeURIComponent(jobId)}`,
    "Failed to save migration configuration",
    { method: "POST", body: config }
  );
}

export async function previewFunctionalTestScope(
  projectName: string,
  endpoints: { path: string; method: string; file?: string; controller?: string }[],
  uiRoutes: { route: string; source_file?: string; page_type?: string; component?: string }[],
  pageData: Record<string, unknown>,
  selectedTools: string[] = [],
  repoUrl: string = "",
  token: string = "",
): Promise<FunctionalTestScopePreview> {
  return requestJson<FunctionalTestScopePreview>(
    `/functional-test-scope/preview`,
    "Failed to generate functional test scope preview",
    {
      method: "POST",
      body: {
        project_name: projectName,
        endpoints,
        uiRoutes,
        page_data: pageData,
        selected_tools: selectedTools,
        repo_url: repoUrl,
        token: token,
      },
    },
  );
}

export async function getToolRecommendations(
  projectName: string,
  analysis: unknown,
  tools: string[],
): Promise<ToolRecommendationsResponse> {
  return requestJson<ToolRecommendationsResponse>(
    `/functional-test-tool-recommendations`,
    "Failed to generate tool recommendations",
    {
      method: "POST",
      body: {
        project_name: projectName,
        analysis,
        tools,
      },
    },
  );
}

export async function updateJavaVersion(
  repoUrl: string,
  javaVersion: string,
  filePath: string,
  token: string = ""
): Promise<UpdateJavaVersionResponse> {
  return requestJson<UpdateJavaVersionResponse>(
    "/github/update-java-version",
    "Failed to update Java version",
    {
      method: "POST",
      query: {
        repo_url: repoUrl,
        java_version: javaVersion,
        file_path: filePath,
        token,
      },
    }
  );
}
