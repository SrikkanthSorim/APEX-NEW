import { performRequest, requestJson, ABSOLUTE_URL_PATTERN } from "@/services/http/client";
import { APP_BASE_URL } from "@/services/config/env";
import type { RepoFilesResponse, FileContentResponse } from "@/features/connect/services/connectService";
import type { DependencyInfo, RepoAnalysis, MicroserviceEligibilityResult } from "@/shared/types/domain";

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

// List files in a repository (works for public repos without token)
export async function listRepoFiles(repoUrl: string, token: string = "", path: string = ""): Promise<RepoFilesResponse> {
  return requestJson<RepoFilesResponse>("/github/list-files", "Failed to list files", {
    query: { repo_url: repoUrl, token, path },
  });
}

// Get file content (works for public repos without token)
export async function getFileContent(repoUrl: string, filePath: string, token: string = ""): Promise<FileContentResponse> {
  return requestJson<FileContentResponse>("/github/file-content", "Failed to get file content", {
    query: { repo_url: repoUrl, file_path: filePath, token },
  });
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
