import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";
import {
  connectRepository,
  ConnectRepositoryApiError,
  getLocalProjectCapabilities,
  getRepoVisibility,
  uploadLocalProject,
  uploadLocalProjectChunk,
  type ConnectRepositoryResult,
  type LocalProjectAnalysisResponse,
  type LocalProjectCapabilities,
} from "@/features/connect/services/connectService";
import { isPrivateRepoAccessError } from "@/shared/utils/repoAccessError";
import type { RepoAnalysis, RepoFile, RepoInfo } from "@/shared/types/domain";
import {
  readPersistedValue,
  readSessionJson,
  writeSessionValue,
  WIZARD_JOB_ID_KEY,
  WIZARD_REPO_URL_KEY,
  WIZARD_SELECTED_REPO_KEY,
} from "@/shared/utils/migrationWizardStorage";

type AccessTokenValidationState = "idle" | "validating" | "valid" | "invalid";

interface UseRepositoryConnectParams {
  persistedIsPrivateRepo?: boolean;
  persistedPatToken?: string;
  setRepoAnalysis: Dispatch<SetStateAction<RepoAnalysis | null>>;
  setRepoFiles: Dispatch<SetStateAction<RepoFile[]>>;
  setStep: Dispatch<SetStateAction<number>>;
  setError: Dispatch<SetStateAction<string>>;
  resetRepositorySelectionState: () => void;
  buildLocalRepoRef: (value: string) => string;
  getPathBasename: (value: string) => string;
  isLocalRepoRef: (value: string | null | undefined) => boolean;
  loadZipSync: () => Promise<typeof import("fflate")["zipSync"]>;
}

const MAX_LOCAL_PROJECT_UPLOAD_FILES = 25000;
const MAX_LOCAL_PROJECT_UPLOAD_SIZE_BYTES = 1024 * 1024 * 1024;
const AUTO_ZIP_LOCAL_PROJECT_UPLOAD_FILES = 15000;
const AUTO_ZIP_LOCAL_PROJECT_UPLOAD_SIZE_BYTES = 150 * 1024 * 1024;
const CHUNK_UPLOAD_SIZE_BYTES = 60 * 1024 * 1024;
const WARN_LOCAL_PROJECT_UPLOAD_FILES = 500;
const WARN_LOCAL_PROJECT_UPLOAD_SIZE_BYTES = 150 * 1024 * 1024;

const isEnterpriseGithub = (url: string) => {
  const match = url.match(/^https?:\/\/(www\.)?github\.([^.]+)\.com\//i);
  return match && match[2] !== "" && match[2] !== "com";
};

const normalizeGithubUrl = (url: string): { valid: boolean; normalizedUrl: string; message: string } => {
  if (!url.trim()) {
    return { valid: false, normalizedUrl: "", message: "URL is required" };
  }

  let normalized = url.trim();
  // Strip URL fragments (#...) and query strings (?...) — never part of a repo path
  normalized = normalized.replace(/[#?].*$/, "");
  normalized = normalized.replace(/\/tree\/[^/]+.*$/, "");
  normalized = normalized.replace(/\/blob\/[^/]+.*$/, "");
  normalized = normalized.replace(/\/src\/.*$/, "");
  normalized = normalized.replace(/\/$/, "");
  normalized = normalized.replace(/\.git$/, "");

  const isGithubUrl = /^https?:\/\/(www\.)?github(\.[^/]+)?\.com\/[^/]+\/[^/\s]+$/.test(normalized);
  const isGitlabUrl = /^https?:\/\/(www\.)?gitlab\.com\/[^/]+\/[^/\s]+$/.test(normalized);
  const isShortFormat = /^[^/]+\/[^/\s]+$/.test(normalized);

  if (isGithubUrl || isGitlabUrl || isShortFormat) {
    if (url !== normalized) {
      return {
        valid: true,
        normalizedUrl: normalized,
        message: "URL normalized (removed tree/blob paths)",
      };
    }
    return { valid: true, normalizedUrl: normalized, message: "" };
  }

  return {
    valid: false,
    normalizedUrl: "",
    message: "Invalid URL format. Use: https://github.com/owner/repo, https://github.<enterprise>.com/owner/repo, or owner/repo",
  };
};

/**
 * Build the URL sent to `POST /api/v1/connect`. The Connect backend currently
 * handles github.com repositories only; for GitLab / GitHub Enterprise / other
 * refs this returns null and the caller keeps the existing (non-backend) flow.
 */
const buildConnectUrl = (value: string): string | null => {
  const normalized = value.trim();
  if (!normalized) return null;

  if (/^https?:\/\//i.test(normalized)) {
    return /(^|\/\/)(www\.)?github\.com\//i.test(normalized) ? normalized : null;
  }

  // Short "owner/repo" form -> expand to a canonical github.com URL.
  if (/^[^/\s]+\/[^/\s]+$/.test(normalized)) {
    return `https://github.com/${normalized}`;
  }

  return null;
};

export function useRepositoryConnect({
  persistedIsPrivateRepo,
  persistedPatToken,
  setRepoAnalysis,
  setRepoFiles,
  setStep,
  setError,
  resetRepositorySelectionState,
  buildLocalRepoRef,
  getPathBasename,
  isLocalRepoRef,
  loadZipSync,
}: UseRepositoryConnectParams) {
  const [repoUrl, setRepoUrl] = useState(() => {
    if (typeof window === "undefined") return "";
    return readPersistedValue(WIZARD_REPO_URL_KEY) || "";
  });
  const [selectedRepo, setSelectedRepo] = useState<RepoInfo | null>(() =>
    readSessionJson<RepoInfo>(WIZARD_SELECTED_REPO_KEY)
  );
  const [githubToken, setGithubToken] = useState("");
  const [githubUserLogin] = useState("");
  const [isPrivateRepo, setIsPrivateRepo] = useState(persistedIsPrivateRepo ?? false);
  const [patToken, setPatToken] = useState(persistedPatToken ?? "");
  const [jobId, setJobId] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return readPersistedValue(WIZARD_JOB_ID_KEY) || "";
  });
  const [connecting, setConnecting] = useState(false);
  // Caches the last successful connect (keyed by url+token) so validating and
  // then continuing does not create a duplicate migration job.
  const lastConnectRef = useRef<{ url: string; token: string; result: ConnectRepositoryResult } | null>(null);
  const [repoAccessCheckLoading, setRepoAccessCheckLoading] = useState(false);
  const [accessTokenValidationState, setAccessTokenValidationState] =
    useState<AccessTokenValidationState>("idle");
  const [accessTokenValidationMessage, setAccessTokenValidationMessage] = useState("");
  const [localProjectCapabilities, setLocalProjectCapabilities] = useState<LocalProjectCapabilities | null>(null);
  const [localProjectCapabilitiesLoading, setLocalProjectCapabilitiesLoading] = useState(false);
  const [localProjectUploadFiles, setLocalProjectUploadFiles] = useState<File[]>([]);
  const [localProjectUploadLoading, setLocalProjectUploadLoading] = useState(false);
  const [localProjectUploadCompressing, setLocalProjectUploadCompressing] = useState(false);
  const [localProjectUploadError, setLocalProjectUploadError] = useState("");
  const [localProjectUploadWarning, setLocalProjectUploadWarning] = useState("");

  const urlValidation = repoUrl ? normalizeGithubUrl(repoUrl) : { valid: false, normalizedUrl: "", message: "" };
  const showEnterpriseToken = repoUrl && isEnterpriseGithub(urlValidation.normalizedUrl || repoUrl);
  const activeAccessToken = (showEnterpriseToken ? githubToken : patToken).trim();
  const repositoryNeedsAuthentication = Boolean(showEnterpriseToken || isPrivateRepo);
  const currentToken = useMemo(() => {
    if (showEnterpriseToken) return githubToken.trim();
    if (isPrivateRepo) return patToken.trim() || githubToken.trim();
    if (githubToken.trim()) return githubToken.trim();
    if (patToken.trim()) return patToken.trim();
    return "";
  }, [githubToken, patToken, showEnterpriseToken, isPrivateRepo]);
  const shouldShowPatInput = showEnterpriseToken || isPrivateRepo;

  const resetAccessTokenValidationState = useCallback(() => {
    setAccessTokenValidationState("idle");
    setAccessTokenValidationMessage("");
  }, []);

  const persistConnectResult = (result: ConnectRepositoryResult, connectUrl: string, token: string) => {
    setJobId(result.jobId);
    writeSessionValue(WIZARD_JOB_ID_KEY, result.jobId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(WIZARD_JOB_ID_KEY, result.jobId);
    }
    lastConnectRef.current = { url: connectUrl, token, result };
  };

  const handleAccessTokenValidate = async () => {
    if (!urlValidation.valid) return;

    if (!activeAccessToken) {
      setAccessTokenValidationState("invalid");
      setAccessTokenValidationMessage(
        showEnterpriseToken
          ? "Enter a GitHub Personal Access Token before validating this GitHub Enterprise repository."
          : "Enter a GitHub Personal Access Token with repo scope before validating this private repository."
      );
      return;
    }

    setAccessTokenValidationState("validating");
    setAccessTokenValidationMessage("");

    const connectUrl = buildConnectUrl(urlValidation.normalizedUrl);

    // github.com repositories are validated through the Connect backend, which
    // also creates the migration job (reused on Continue). Other refs keep the
    // existing visibility check.
    if (connectUrl) {
      try {
        const result = await connectRepository(connectUrl, activeAccessToken);
        persistConnectResult(result, connectUrl, activeAccessToken);
        const detectedPrivateRepo = result.repoVisibility === "PRIVATE";
        setIsPrivateRepo(detectedPrivateRepo);
        setError("");
        setAccessTokenValidationState("valid");
        setAccessTokenValidationMessage(
          detectedPrivateRepo
            ? "Token validated. Private repository access looks ready."
            : "Token validated. Repository access looks ready."
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : "We couldn't validate this token yet.";
        setAccessTokenValidationState("invalid");
        setAccessTokenValidationMessage(message);
      }
      return;
    }

    try {
      const visibility = await getRepoVisibility(urlValidation.normalizedUrl, activeAccessToken);
      const detectedPrivateRepo =
        visibility.requires_token ||
        visibility.visibility === "private" ||
        visibility.visibility === "private_or_inaccessible";

      setIsPrivateRepo(detectedPrivateRepo);
      setError("");
      setAccessTokenValidationState("valid");
      setAccessTokenValidationMessage(
        showEnterpriseToken
          ? "Token validated. Repository authentication looks ready."
          : detectedPrivateRepo
            ? "Token validated. Private repository access looks ready."
            : "Token validated. Repository access looks ready."
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "We couldn't validate this token yet.";
      setAccessTokenValidationState("invalid");
      setAccessTokenValidationMessage(
        isPrivateRepoAccessError(message)
          ? "We couldn't verify private repository access. Check that the PAT is correct and includes repo scope."
          : message
      );
    }
  };

  const handleRepositoryContinue = async () => {
    if (!urlValidation.valid) return;

    const normalizedUrl = urlValidation.normalizedUrl;
    const token = currentToken.trim();

    if (showEnterpriseToken && !token) {
      setError("");
      setAccessTokenValidationState("invalid");
      setAccessTokenValidationMessage("Enter a GitHub Personal Access Token to analyze this GitHub Enterprise repository.");
      return;
    }

    if (isPrivateRepo && !token) {
      setError("");
      setAccessTokenValidationState("invalid");
      setAccessTokenValidationMessage("Enter a GitHub Personal Access Token with repo scope to analyze this private repository.");
      return;
    }

    // For github.com repositories, verify access and create the migration job
    // via the Connect backend before advancing. Navigation only happens on
    // success. Reuse a previously validated connect to avoid duplicate jobs.
    const connectUrl = buildConnectUrl(normalizedUrl);
    if (connectUrl) {
      const cached = lastConnectRef.current;
      const alreadyConnected = cached?.url === connectUrl && cached?.token === (token || "");

      if (!alreadyConnected) {
        setConnecting(true);
        setError("");
        try {
          const result = await connectRepository(connectUrl, token || undefined);
          persistConnectResult(result, connectUrl, token || "");
          setIsPrivateRepo(result.repoVisibility === "PRIVATE");
        } catch (err) {
          setConnecting(false);
          const accessStatus =
            err instanceof ConnectRepositoryApiError ? err.accessStatus : "SERVICE_ERROR";
          const message =
            err instanceof Error ? err.message : "We couldn't verify the repository right now.";

          // Private/denied/not-found: reveal the PAT field so the user can retry
          // with a token and surface the clean backend message.
          if (accessStatus === "ACCESS_DENIED" || accessStatus === "NOT_FOUND") {
            setIsPrivateRepo(true);
            resetAccessTokenValidationState();
            setAccessTokenValidationState("invalid");
            setAccessTokenValidationMessage(message);
          } else {
            setError(message);
          }
          return; // do not navigate on failure
        }
        setConnecting(false);
      }
    }

    resetRepositorySelectionState();
    setSelectedRepo({
      name: normalizedUrl.split("/").pop() || "",
      full_name: normalizedUrl
        .replace(/^https?:\/\/(www\.)?github\.com\//, "")
        .replace(/^https?:\/\/(www\.)?gitlab\.com\//, ""),
      url: normalizedUrl,
      default_branch: "main",
      language: "Java",
      description: "",
    });
    setStep(2);
  };

  const shouldCompressLocalProjectUpload = (files: File[]) => {
    if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
      return false;
    }
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    return (
      files.length > AUTO_ZIP_LOCAL_PROJECT_UPLOAD_FILES ||
      totalSize > AUTO_ZIP_LOCAL_PROJECT_UPLOAD_SIZE_BYTES
    );
  };

  const zipLocalProjectFiles = async (files: File[]): Promise<Blob> => {
    const entries: Record<string, Uint8Array> = {};
    for (const file of files) {
      const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      const arrayBuffer = await file.arrayBuffer();
      entries[relativePath || file.name] = new Uint8Array(arrayBuffer);
    }
    const zipSync = await loadZipSync();
    const zipped = zipSync(entries, { level: 3 });
    const zipBytes = new Uint8Array(zipped.byteLength);
    zipBytes.set(zipped);
    return new Blob([zipBytes], { type: "application/zip" });
  };

  const handleLocalProjectFilesChange = (files: FileList | null) => {
    if (!files) {
      setLocalProjectUploadFiles([]);
      setLocalProjectUploadError("");
      setLocalProjectUploadWarning("");
      return;
    }

    const fileArray = Array.from(files);
    const totalSize = fileArray.reduce((sum, file) => sum + file.size, 0);

    if (fileArray.length > MAX_LOCAL_PROJECT_UPLOAD_FILES || totalSize > MAX_LOCAL_PROJECT_UPLOAD_SIZE_BYTES) {
      setLocalProjectUploadFiles(fileArray);
      setLocalProjectUploadError(
        `Selected folder is too large to upload directly (${fileArray.length} files, ${(totalSize / (1024 * 1024)).toFixed(1)} MB). Please upload a ZIP archive instead.`
      );
      setLocalProjectUploadWarning("");
      setError("");
      return;
    }

    const shouldCompress = shouldCompressLocalProjectUpload(fileArray);
    let warningMessage = "";
    if (shouldCompress) {
      warningMessage = `Selected folder contains ${fileArray.length} files and ${(totalSize / (1024 * 1024)).toFixed(1)} MB. It will be compressed to ZIP before uploading to improve reliability.`;
    } else if (fileArray.length > WARN_LOCAL_PROJECT_UPLOAD_FILES || totalSize > WARN_LOCAL_PROJECT_UPLOAD_SIZE_BYTES) {
      warningMessage = `Selected folder contains ${fileArray.length} files and ${(totalSize / (1024 * 1024)).toFixed(1)} MB. Upload may take a long time, but it is allowed.`;
    }

    setLocalProjectUploadFiles(fileArray);
    setLocalProjectUploadError("");
    setLocalProjectUploadWarning(warningMessage);
    setError("");

    if (selectedRepo && isLocalRepoRef(selectedRepo.url)) {
      setSelectedRepo(null);
      setRepoAnalysis(null);
    }
  };

  const handleLocalProjectUpload = async () => {
    if (localProjectUploadFiles.length === 0 || localProjectUploadError) return;

    setLocalProjectUploadLoading(true);
    setLocalProjectUploadCompressing(false);
    setLocalProjectUploadError("");
    setLocalProjectUploadWarning("");
    setError("");

    const localFiles = localProjectUploadFiles;
    const shouldCompress = shouldCompressLocalProjectUpload(localFiles);
    const uploadFiles = async (zip: boolean) => {
      const formData = new FormData();
      if (zip) {
        setLocalProjectUploadCompressing(true);
        const zipBlob = await zipLocalProjectFiles(localFiles);

        if (zipBlob.size > CHUNK_UPLOAD_SIZE_BYTES) {
          const totalChunks = Math.ceil(zipBlob.size / CHUNK_UPLOAD_SIZE_BYTES);
          const uploadId = globalThis.crypto?.randomUUID?.() ?? `upload-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
          let finalResponse: LocalProjectAnalysisResponse | null = null;

          for (let index = 0; index < totalChunks; index++) {
            const start = index * CHUNK_UPLOAD_SIZE_BYTES;
            const end = Math.min(start + CHUNK_UPLOAD_SIZE_BYTES, zipBlob.size);
            const chunkBlob = zipBlob.slice(start, end);
            const result = await uploadLocalProjectChunk(
              uploadId,
              index + 1,
              totalChunks,
              chunkBlob,
              "local-project.zip",
            );

            if (index === totalChunks - 1) {
              finalResponse = result as LocalProjectAnalysisResponse;
            }
          }

          if (!finalResponse) {
            throw new Error("Failed to complete chunked upload");
          }

          return finalResponse;
        }

        formData.append("zip_file", zipBlob, "local-project.zip");
        setLocalProjectUploadCompressing(false);
      } else {
        localFiles.forEach((file) => formData.append("files", file, file.webkitRelativePath || file.name));
      }

      return uploadLocalProject(formData);
    };

    let result: LocalProjectAnalysisResponse | undefined;
    let attemptedZipRetry = false;
    try {
      result = await uploadFiles(shouldCompress);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to upload local project";
      const isNetworkFailure =
        message === "Failed to fetch" ||
        message.includes("ERR_HTTP2_PROTOCOL_ERROR") ||
        message.includes("NetworkError");

      if (!shouldCompress && !attemptedZipRetry && isNetworkFailure && localFiles.length > 1) {
        attemptedZipRetry = true;
        try {
          result = await uploadFiles(true);
        } catch (retryErr) {
          const retryMessage = retryErr instanceof Error ? retryErr.message : "Failed to upload local project";
          setLocalProjectUploadError(
            retryMessage === "Failed to fetch"
              ? "Upload failed due to browser or network limits. Try uploading a ZIP archive directly."
              : retryMessage
          );
        }
      } else {
        setLocalProjectUploadError(
          message === "Failed to fetch"
            ? "Upload failed due to browser or network limits. Try uploading a ZIP archive directly."
            : message
        );
      }
    } finally {
      setLocalProjectUploadCompressing(false);
      setLocalProjectUploadLoading(false);
    }

    if (!result) return;

    const uploadedRepoUrl = result.project_path.startsWith("local://")
      ? result.project_path
      : buildLocalRepoRef(result.project_path);

    resetRepositorySelectionState();
    setSelectedRepo({
      name: result.project_name || getPathBasename(localProjectUploadFiles[0]?.webkitRelativePath || localProjectUploadFiles[0]?.name || "uploaded-project"),
      full_name: uploadedRepoUrl,
      url: uploadedRepoUrl,
      default_branch: "local",
      language: "Java",
      description: "Uploaded local project",
    });
    setRepoAnalysis(result.analysis);
    setRepoFiles([]);
    setStep(2);
  };

  useEffect(() => {
    let cancelled = false;
    setLocalProjectCapabilitiesLoading(true);
    getLocalProjectCapabilities()
      .then((capabilities) => {
        if (!cancelled) {
          setLocalProjectCapabilities(capabilities);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLocalProjectCapabilities(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLocalProjectCapabilitiesLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return {
    repoUrl,
    setRepoUrl,
    selectedRepo,
    setSelectedRepo,
    githubToken,
    setGithubToken,
    githubUserLogin,
    isPrivateRepo,
    setIsPrivateRepo,
    patToken,
    setPatToken,
    jobId,
    connecting,
    repoAccessCheckLoading,
    setRepoAccessCheckLoading,
    accessTokenValidationState,
    setAccessTokenValidationState,
    accessTokenValidationMessage,
    setAccessTokenValidationMessage,
    localProjectCapabilities,
    localProjectCapabilitiesLoading,
    localProjectUploadFiles,
    setLocalProjectUploadFiles,
    localProjectUploadLoading,
    localProjectUploadCompressing,
    localProjectUploadError,
    setLocalProjectUploadError,
    localProjectUploadWarning,
    setLocalProjectUploadWarning,
    urlValidation,
    showEnterpriseToken,
    activeAccessToken,
    repositoryNeedsAuthentication,
    currentToken,
    shouldShowPatInput,
    resetAccessTokenValidationState,
    handleAccessTokenValidate,
    handleRepositoryContinue,
    handleLocalProjectFilesChange,
    handleLocalProjectUpload,
  };
}
