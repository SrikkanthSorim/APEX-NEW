import { requestJson } from "@/services/http/client";

export interface MigrationStrategySection {
  target_java_version: string | null;
  migration_approach: string | null;
  conversion_types: string[];
  recipes_executed: unknown[];
  recipe_selection_reasons: unknown[];
  build_modernization: unknown[];
  dependency_upgrades: unknown[];
  import_changes: unknown[];
  source_changes: unknown[];
  retry_attempts: unknown[];
  build_status: string | null;
  build_success: boolean | null;
  migration_summary: string | null;
  has_migration_run: boolean;
}

export interface ProjectDocsResponse {
  job_id: string;
  project_name: string | null;
  repo_url: string | null;
  has_repository_analysis: boolean;
  detected_java_version: string | null;
  target_java_version: string | null;
  build_tool: string | null;
  project_type: string | null;
  frameworks: string[];
  dependencies: unknown[];
  modules: string[];
  frontend: Record<string, unknown> | null;
  generated_at: string;
  strategy: MigrationStrategySection;
}

export interface ProjectDocsHtmlResponse {
  job_id: string;
  filename: string;
  html: string;
}

export async function getProjectDocs(jobId: string): Promise<ProjectDocsResponse> {
  return requestJson<ProjectDocsResponse>(`/v1/docs/${jobId}`, "Failed to load project documentation");
}

export async function getProjectDocsHtml(jobId: string): Promise<ProjectDocsHtmlResponse> {
  return requestJson<ProjectDocsHtmlResponse>(
    `/v1/docs/${jobId}/html`,
    "Failed to prepare documentation for download"
  );
}
