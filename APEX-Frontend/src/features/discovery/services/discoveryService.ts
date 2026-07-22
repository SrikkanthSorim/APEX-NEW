import { authHeader, performRequest, requestJson, ABSOLUTE_URL_PATTERN } from "@/services/http/client";
import { APP_BASE_URL } from "@/services/config/env";
import type { RepoFilesResponse, FileContentResponse } from "@/features/connect/services/connectService";
import type {
  DependencyInfo,
  RepoAnalysis,
  MicroserviceEligibilityResult,
  RepoFile,
  SpringBootConversionEligibility,
} from "@/shared/types/domain";

/* -------------------------------------------------------------------------- */
/* Discovery stage (Step 2) — POST /api/v1/discovery/{jobId}                    */
/*                                                                              */
/* Clones the connected repo into the backend workspace and analyzes it        */
/* (read-only). Returns a clean summary which we map onto the RepoAnalysis      */
/* shape the existing Discovery UI renders.                                     */
/* -------------------------------------------------------------------------- */

export interface DiscoveryDependency {
  groupId: string;
  artifactId: string;
  version: string | null;
}

export interface DiscoveryProject {
  buildTool: string;
  currentJavaVersion: string;
  springBootVersion: string | null;
  projectType: string;
  multiModule: boolean;
  modules: string[];
  dependenciesCount: number;
  frontendDetected: boolean;
  frontendType: string | null;
  // extras used to faithfully populate the existing UI
  dependencies?: DiscoveryDependency[];
  hasTests?: boolean;
  javaFileCount?: number;
  defaultBranch?: string;
  buildWarning?: string | null;
  frontend?: { detected: boolean; type: string; path: string | null; packageManager: string | null };
  detectedFiles?: { pomXml: boolean; buildGradle: boolean; buildGradleKts: boolean; packageJson: boolean };
  sourceLayout?: { hasSrcMain: boolean; hasSrcTest: boolean };
  springFrameworkVersion?: string | null;
  springEntryClass?: string | null;
  javaMigrationEligible?: boolean;
  javaMigrationReason?: string;
  springDetected?: boolean;
  springBootDetected?: boolean;
  springBootConversionEligible?: boolean;
  springBootUpgradeEligible?: boolean;
  eligibilityReason?: string;
  springBootConversion?: SpringBootConversionEligibility;
}

export interface DiscoveryResponse {
  jobId: string;
  status: string;
  message: string;
  repository: { repoUrl: string; owner: string; repoName: string; visibility: string };
  project: DiscoveryProject;
  nextStep: string;
}

export type DiscoveryStatus =
  | "DISCOVERY_COMPLETED"
  | "CONNECT_REPORT_NOT_FOUND"
  | "CLONE_FAILED"
  | "UNSUPPORTED_PROJECT"
  | "DISCOVERY_FAILED";

export class DiscoveryApiError extends Error {
  status: DiscoveryStatus | string;
  httpStatus: number;

  constructor(message: string, status: DiscoveryStatus | string, httpStatus: number) {
    super(message);
    this.name = "DiscoveryApiError";
    this.status = status;
    this.httpStatus = httpStatus;
  }
}

export interface DiscoveryAnalysisResult {
  repo_url: string;
  owner: string;
  repo: string;
  analysis: RepoAnalysis;
  discovery: DiscoveryResponse;
}

function normalizeBuildTool(buildTool: string): string | null {
  const value = (buildTool || "").toUpperCase();
  if (value === "MAVEN") return "maven";
  if (value === "GRADLE") return "gradle";
  return null;
}

function normalizeJavaVersion(version: string | null | undefined): string | null {
  if (!version) return null;
  const value = version.trim();
  return value && value.toUpperCase() !== "UNKNOWN" ? value : null;
}

/** Map the backend discovery summary onto the RepoAnalysis the Discovery UI reads. */
export function mapDiscoveryToRepoAnalysis(response: DiscoveryResponse): RepoAnalysis {
  const { repository, project } = response;
  const javaVersion = normalizeJavaVersion(project.currentJavaVersion);
  const springBootEligibility: SpringBootConversionEligibility | undefined =
    project.springBootConversion ??
    (typeof project.javaMigrationEligible === "boolean"
      ? {
          repositoryAnalyzed: true,
          javaMigrationEligible: project.javaMigrationEligible,
          javaMigrationReason: project.javaMigrationReason ?? "",
          springDetected: Boolean(project.springDetected),
          springBootDetected: Boolean(project.springBootDetected),
          springVersion: project.springFrameworkVersion ?? null,
          springBootVersion: project.springBootVersion ?? null,
          buildTool: project.buildTool,
          springBootConversionEligible: Boolean(project.springBootConversionEligible),
          springBootUpgradeEligible: Boolean(project.springBootUpgradeEligible),
          eligibilityReason: project.eligibilityReason ?? "",
        }
      : undefined);
  const dependencies: DependencyInfo[] = (project.dependencies ?? []).map((dep) => ({
    group_id: dep.groupId,
    artifact_id: dep.artifactId,
    current_version: dep.version ?? "",
    new_version: null,
    status: "detected",
  }));

  return {
    name: repository.repoName,
    full_name: `${repository.owner}/${repository.repoName}`,
    default_branch: project.defaultBranch || "main",
    language: "Java",
    build_tool: normalizeBuildTool(project.buildTool),
    java_version: javaVersion,
    java_version_from_build: javaVersion,
    java_files: [],
    has_tests: Boolean(project.hasTests),
    dependencies,
    api_endpoints: [],
    detected_frameworks: [],
    structure: {
      has_pom_xml: Boolean(project.detectedFiles?.pomXml),
      has_build_gradle: Boolean(project.detectedFiles?.buildGradle),
      has_build_gradle_kts: Boolean(project.detectedFiles?.buildGradleKts),
      has_src_main: Boolean(project.sourceLayout?.hasSrcMain),
      has_src_test: Boolean(project.sourceLayout?.hasSrcTest),
    },
    spring_boot_eligibility: springBootEligibility,
  };
}

/**
 * Run discovery for a job. Reads the response body on both success and error so
 * the backend's clean status/message are always surfaced. Returns the mapped
 * RepoAnalysis (plus the raw discovery summary) for the Discovery UI.
 */
export async function runDiscovery(jobId: string, githubToken?: string): Promise<DiscoveryAnalysisResult> {
  const response = await performRequest(`/v1/discovery/${encodeURIComponent(jobId)}`, {
    method: "POST",
    body: { githubToken: githubToken?.trim() ? githubToken.trim() : undefined },
  });

  const data = (await response.json().catch(() => null)) as
    | (Partial<DiscoveryResponse> & { status?: string; message?: string })
    | null;

  if (!response.ok || !data || data.status !== "DISCOVERY_COMPLETED" || !data.project) {
    const status = (data?.status as DiscoveryStatus) ?? "DISCOVERY_FAILED";
    const message = data?.message ?? "Repository discovery failed. Please try again.";
    throw new DiscoveryApiError(message, status, response.status);
  }

  const discovery = data as DiscoveryResponse;
  return {
    repo_url: discovery.repository.repoUrl,
    owner: discovery.repository.owner,
    repo: discovery.repository.repoName,
    analysis: mapDiscoveryToRepoAnalysis(discovery),
    discovery,
  };
}

interface MicroserviceEligibilityAnalysisSnapshot {
  build_tool: string | null;
  java_file_count: number;
  has_tests: boolean;
  dependencies: DependencyInfo[];
  structure: RepoAnalysis["structure"];
}

function buildMicroserviceEligibilityAnalysisSnapshot(repoAnalysis: RepoAnalysis): MicroserviceEligibilityAnalysisSnapshot {
  return {
    build_tool: repoAnalysis.build_tool ?? null,
    java_file_count: repoAnalysis.java_files?.length ?? 0,
    has_tests: repoAnalysis.has_tests,
    dependencies: repoAnalysis.dependencies || [],
    structure: repoAnalysis.structure,
  };
}

export type GithubDocumentType = "brd" | "kt";

export interface GithubDocumentRequest {
  repo_url?: string;
  repository_url?: string;
  source_repo_url?: string;
  token?: string;
  github_token?: string;
  job_id?: string;
  migration_job_id?: string;
  source_repo?: string;
  target_repo?: string | null;
  source_java_version?: string;
  target_java_version?: string;
  document_type?: string;
  analysis?: Record<string, unknown>;
}

export interface LocalProjectDocumentRequest extends GithubDocumentRequest {
  analysis: Record<string, unknown>;
}

export interface GithubDocumentResponse {
  html?: string;
  url?: string;
  filename: string;
}

function extractGithubDocumentHtml(data: Record<string, unknown>): string | undefined {
  const nestedData = data.data && typeof data.data === "object"
    ? (data.data as Record<string, unknown>)
    : undefined;
  const htmlCandidates = [
    data.html,
    data.document_html,
    data.html_content,
    data.content,
    data.document,
    data.markup,
    nestedData?.html,
    nestedData?.document_html,
    nestedData?.content,
  ];

  const htmlCandidate = htmlCandidates.find(
    (candidate): candidate is string => typeof candidate === "string" && candidate.trim().length > 0
  );

  return htmlCandidate;
}

function extractGithubDocumentUrl(data: Record<string, unknown>): string | undefined {
  const nestedData = data.data && typeof data.data === "object"
    ? (data.data as Record<string, unknown>)
    : undefined;
  const urlCandidates = [
    data.url,
    data.document_url,
    data.download_url,
    data.file_url,
    nestedData?.url,
    nestedData?.document_url,
    nestedData?.download_url,
  ];

  const urlCandidate = urlCandidates.find(
    (candidate): candidate is string => typeof candidate === "string" && candidate.trim().length > 0
  );

  return urlCandidate;
}

function resolveDocumentUrl(url: string | undefined): string | undefined {
  if (!url || !url.trim()) {
    return undefined;
  }

  return ABSOLUTE_URL_PATTERN.test(url)
    ? url
    : new URL(url.replace(/^\/+/, ""), `${APP_BASE_URL}/`).toString();
}

// List files in a repository (works for public repos without token). The GitHub
// PAT, when present, is sent as an Authorization header, never in the query string.
export async function listRepoFiles(repoUrl: string, token: string = "", path: string = ""): Promise<RepoFilesResponse> {
  return requestJson<RepoFilesResponse>("/github/list-files", "Failed to list files", {
    query: { repo_url: repoUrl, path },
    headers: authHeader(token),
  });
}

// Get file content (works for public repos without token). The GitHub PAT, when
// present, is sent as an Authorization header, never in the query string.
export async function getFileContent(repoUrl: string, filePath: string, token: string = ""): Promise<FileContentResponse> {
  return requestJson<FileContentResponse>("/github/file-content", "Failed to get file content", {
    query: { repo_url: repoUrl, file_path: filePath },
    headers: authHeader(token),
  });
}

/* -------------------------------------------------------------------------- */
/* Repository Files (Discovery page) — GET /api/v1/discovery/{jobId}/files      */
/* and GET /api/v1/discovery/{jobId}/file                                       */
/*                                                                              */
/* Reads the repository clone Discovery already made on disk (original-repo),  */
/* rather than re-fetching from GitHub. Works for any repo Discovery has run   */
/* on, with no GitHub API calls/rate limits. Folder contents are fetched one   */
/* level at a time (lazy), so large repos stay fast.                           */
/* -------------------------------------------------------------------------- */

export interface DiscoveryFilesResponse {
  jobId: string;
  path: string;
  files: RepoFile[];
}

export interface DiscoveryFileContentResponse {
  jobId: string;
  filePath: string;
  content: string;
  size: number;
}

export async function listDiscoveryFiles(jobId: string, path: string = ""): Promise<DiscoveryFilesResponse> {
  return requestJson<DiscoveryFilesResponse>(
    `/v1/discovery/${encodeURIComponent(jobId)}/files`,
    "Failed to list repository files",
    { query: { path } }
  );
}

export async function getDiscoveryFileContent(jobId: string, path: string): Promise<DiscoveryFileContentResponse> {
  return requestJson<DiscoveryFileContentResponse>(
    `/v1/discovery/${encodeURIComponent(jobId)}/file`,
    "Failed to load file content",
    { query: { path } }
  );
}

export async function getMicroserviceEligibility(
  repoUrl: string,
  token: string = "",
  repoAnalysis?: RepoAnalysis,
): Promise<MicroserviceEligibilityResult> {
  return requestJson<MicroserviceEligibilityResult>(
    "/github/microservice-eligibility",
    "Failed to get microservice eligibility",
    {
      method: "POST",
      body: {
        repo_url: repoUrl,
        token,
        analysis: repoAnalysis ? buildMicroserviceEligibilityAnalysisSnapshot(repoAnalysis) : undefined,
      },
    }
  );
}

// Real static analysis over the job's already-cloned repository (Discovery
// workspace) — detects controllers/services/repositories/entities, groups
// them into per-controller business chunks via their actual dependency
// graph, and scores each chunk. No GitHub API calls, no mock data.
export async function getDiscoveryMicroserviceEligibility(jobId: string): Promise<MicroserviceEligibilityResult> {
  return requestJson<MicroserviceEligibilityResult>(
    `/v1/discovery/${encodeURIComponent(jobId)}/microservice-eligibility`,
    "Failed to get microservice eligibility"
  );
}

export async function getLocalProjectMicroserviceEligibility(
  projectPath: string,
  repoAnalysis?: RepoAnalysis,
): Promise<MicroserviceEligibilityResult> {
  return requestJson<MicroserviceEligibilityResult>(
    "/local-project/microservice-eligibility",
    "Failed to get local project microservice eligibility",
    {
      method: "POST",
      body: {
        project_path: projectPath,
        analysis: repoAnalysis ? buildMicroserviceEligibilityAnalysisSnapshot(repoAnalysis) : undefined,
      },
    }
  );
}

export async function generateGithubDocument(
  documentType: GithubDocumentType,
  request: GithubDocumentRequest
): Promise<GithubDocumentResponse> {
  const response = await performRequest(`/github/generate-${documentType}-document`, {
    method: "POST",
    body: request,
  });

  const contentType = response.headers.get("content-type") || "";
  const bodyText = await response.text();
  const fallbackMessage = `Failed to generate ${documentType.toUpperCase()} document`;

  if (!response.ok) {
    if (contentType.includes("application/json")) {
      try {
        const data = JSON.parse(bodyText);
        const detail = data?.detail || data?.message || data?.error;
        throw new Error(
          typeof detail === "string" && detail.trim().length > 0 ? detail : fallbackMessage
        );
      } catch {
        throw new Error(bodyText || fallbackMessage);
      }
    }

    throw new Error(bodyText || fallbackMessage);
  }

  const repoNameCandidate =
    request.source_repo ||
    request.repository_url ||
    request.repo_url ||
    "repository";
  const repoName = repoNameCandidate
    .split("/")
    .filter(Boolean)
    .pop()
    ?.replace(/\.git$/i, "") || "repository";
  const filename = `${repoName.toUpperCase()}-TECHNICAL-DOCUMENT.html`;

  if (contentType.includes("application/json")) {
    const data = bodyText ? JSON.parse(bodyText) : {};
    const html = extractGithubDocumentHtml(data);
    const url = extractGithubDocumentUrl(data);

    if (!html && !url) {
      throw new Error(
        `${documentType.toUpperCase()} document endpoint responded without HTML or download URL`
      );
    }

    return {
      html,
      url: resolveDocumentUrl(url),
      filename:
        typeof data?.filename === "string" && data.filename.trim().length > 0
          ? data.filename
          : filename,
    };
  }

  if (!bodyText.trim()) {
    throw new Error(`${documentType.toUpperCase()} document endpoint returned empty content`);
  }

  return {
    html: bodyText,
    filename,
  };
}

export async function generateLocalProjectDocument(
  request: LocalProjectDocumentRequest
): Promise<GithubDocumentResponse> {
  const response = await requestJson<GithubDocumentResponse>(
    "/local-project/generate-brd-document",
    "Failed to generate BRD document",
    {
      method: "POST",
      body: request,
    }
  );
  return {
    ...response,
    url: resolveDocumentUrl(response.url),
  };
}
