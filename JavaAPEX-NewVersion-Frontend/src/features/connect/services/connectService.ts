import { requestJson } from "@/services/http/client";
import type { RepoAnalysis, RepoFile, RepoInfo } from "@/shared/types/domain";

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
