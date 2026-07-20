import { performRequest, requestJson } from "@/services/http/client";
import type { RepoAnalysis, RepoFile, RepoInfo } from "@/shared/types/domain";

/**
 * Connect stage (Step 1) — talks to the new layered backend endpoint
 * `POST /api/v1/connect`. This only validates the repository URL, detects
 * PUBLIC/PRIVATE visibility, verifies access, and creates a migration job id.
 * No cloning or migration happens here.
 */
export type RepoVisibility = "PUBLIC" | "PRIVATE";

export type ConnectAccessStatus =
  | "ACCESS_GRANTED"
  | "ACCESS_DENIED"
  | "NOT_FOUND"
  | "INVALID_URL"
  | "SERVICE_ERROR";

export interface ConnectRepositoryResult {
  jobId: string;
  repoUrl: string;
  owner: string;
  repoName: string;
  repoVisibility: RepoVisibility;
  accessStatus: ConnectAccessStatus;
  message: string;
}

export class ConnectRepositoryApiError extends Error {
  accessStatus: ConnectAccessStatus;
  httpStatus: number;

  constructor(message: string, accessStatus: ConnectAccessStatus, httpStatus: number) {
    super(message);
    this.name = "ConnectRepositoryApiError";
    this.accessStatus = accessStatus;
    this.httpStatus = httpStatus;
  }
}

/**
 * Verify repository access and create a migration job.
 * Reads the response body on both success and error so the backend's clean,
 * user-friendly `message`/`accessStatus` are always surfaced.
 */
export async function connectRepository(
  repoUrl: string,
  githubToken?: string
): Promise<ConnectRepositoryResult> {
  const response = await performRequest("/v1/connect", {
    method: "POST",
    body: {
      repoUrl,
      githubToken: githubToken?.trim() ? githubToken.trim() : undefined,
    },
  });

  const data = (await response.json().catch(() => null)) as
    | (Partial<ConnectRepositoryResult> & { accessStatus?: ConnectAccessStatus; message?: string })
    | null;

  if (!response.ok || !data || !data.jobId) {
    const accessStatus = (data?.accessStatus as ConnectAccessStatus) ?? "SERVICE_ERROR";
    const message =
      data?.message ?? "We couldn't verify the repository right now. Please try again.";
    throw new ConnectRepositoryApiError(message, accessStatus, response.status);
  }

  return data as ConnectRepositoryResult;
}

export interface RepoUrlAnalysis {
  repo_url: string;
  owner: string;
  repo: string;
  analysis: RepoAnalysis;
}

export interface LocalProjectCapabilities {
  enabled: boolean;
  hosted_mode: boolean;
  allow_any_path: boolean;
  allowed_roots: string[];
  supports_upload?: boolean;
  message: string;
}

export interface LocalProjectAnalysisResponse {
  project_path: string;
  project_name: string;
  repo_url: string;
  owner: string;
  repo: string;
  analysis: RepoAnalysis;
}

export interface RepoVisibilityInfo {
  owner: string;
  repo: string;
  visibility: "public" | "private" | "private_or_inaccessible" | "unknown";
  requires_token: boolean;
  message: string;
}

export interface RepoFilesResponse {
  repo_url: string;
  owner: string;
  repo: string;
  path: string;
  files: RepoFile[];
}

export interface FileContentResponse {
  repo_url: string;
  owner: string;
  repo: string;
  file_path: string;
  content: string;
}

export async function fetchRepositories(token: string): Promise<RepoInfo[]> {
  return requestJson<RepoInfo[]>("/github/repos", "Failed to fetch repositories", {
    query: { token },
  });
}

export async function analyzeRepository(token: string, owner: string, repo: string): Promise<RepoAnalysis> {
  return requestJson<RepoAnalysis>(
    `/github/repo/${owner}/${repo}/analyze`,
    "Failed to analyze repository",
    {
      query: { token },
    }
  );
}

// Analyze repository directly by URL (works for public repos without token)
export async function analyzeRepoUrl(repoUrl: string, token: string = "", forceRefresh: boolean = false): Promise<RepoUrlAnalysis> {
  return requestJson<RepoUrlAnalysis>("/github/analyze-url", "Failed to analyze repository", {
    query: { repo_url: repoUrl, token, force_refresh: forceRefresh },
  });
}

export async function getRepoVisibility(repoUrl: string, token: string = ""): Promise<RepoVisibilityInfo> {
  return requestJson<RepoVisibilityInfo>("/github/repo-visibility", "Failed to check repository visibility", {
    query: { repo_url: repoUrl, token },
  });
}

export async function getLocalProjectCapabilities(): Promise<LocalProjectCapabilities> {
  return requestJson<LocalProjectCapabilities>(
    "/local-project/capabilities",
    "Failed to load local project capabilities"
  );
}

export async function analyzeLocalProject(projectPath: string): Promise<LocalProjectAnalysisResponse> {
  return requestJson<LocalProjectAnalysisResponse>(
    "/local-project/analyze",
    "Failed to analyze local project",
    {
      method: "POST",
      body: { project_path: projectPath },
    }
  );
}

export async function uploadLocalProject(formData: FormData): Promise<LocalProjectAnalysisResponse> {
  return requestJson<LocalProjectAnalysisResponse>("/local-project/upload", "Failed to upload local project", {
    method: "POST",
    body: formData,
  });
}

export async function uploadLocalProjectChunk(
  uploadId: string,
  chunkIndex: number,
  totalChunks: number,
  chunk: Blob,
  fileName: string,
  projectName: string | null = null,
): Promise<LocalProjectAnalysisResponse | { status: string; upload_id: string; chunk_index: number; total_chunks: number }> {
  const formData = new FormData();
  formData.append("upload_id", uploadId);
  formData.append("chunk_index", String(chunkIndex));
  formData.append("total_chunks", String(totalChunks));
  formData.append("file_name", fileName);
  if (projectName) {
    formData.append("project_name", projectName);
  }
  formData.append("file", new File([chunk], fileName, { type: "application/octet-stream" }));

  return requestJson<
    LocalProjectAnalysisResponse | { status: string; upload_id: string; chunk_index: number; total_chunks: number }
  >("/local-project/upload-chunk", "Failed to upload local project chunk", {
    method: "POST",
    body: formData,
  });
}

export async function listLocalProjectFiles(projectPath: string, path: string = ""): Promise<RepoFilesResponse> {
  return requestJson<RepoFilesResponse>("/local-project/list-files", "Failed to list local project files", {
    query: { project_path: projectPath, path },
  });
}

export async function getLocalProjectFileContent(projectPath: string, filePath: string): Promise<FileContentResponse> {
  return requestJson<FileContentResponse>(
    "/local-project/file-content",
    "Failed to get local project file content",
    {
      query: { project_path: projectPath, file_path: filePath },
    }
  );
}
