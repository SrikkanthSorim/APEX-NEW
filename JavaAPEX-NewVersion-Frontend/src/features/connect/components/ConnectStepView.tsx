import {
  FaCheckCircle,
  FaExclamationTriangle,
  FaFileAlt,
  FaFolderOpen,
  FaInfoCircle,
  FaLink,
  FaLock,
  FaUpload,
} from "react-icons/fa";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import {
  renderWizardIconBadge,
  renderForwardButtonLabel,
  buildWizardAccentVars,
  WizardInfoTooltip,
} from "@/shared/components/wizard";
import type { useRepositoryConnect } from "../hooks/useRepositoryConnect";

interface ConnectStepViewProps {
  connect: ReturnType<typeof useRepositoryConnect>;
  onError: (message: string) => void;
  onClearRepoAnalysis: () => void;
}

export function ConnectStepView({ connect, onError, onClearRepoAnalysis }: ConnectStepViewProps) {
  const {
    repoUrl,
    setRepoUrl,
    setSelectedRepo,
    githubToken,
    setGithubToken,
    setIsPrivateRepo,
    patToken,
    setPatToken,
    connecting,
    repoAccessCheckLoading,
    accessTokenValidationState,
    accessTokenValidationMessage,
    localProjectCapabilities,
    localProjectCapabilitiesLoading,
    localProjectUploadFiles,
    localProjectUploadLoading,
    localProjectUploadCompressing,
    localProjectUploadError,
    localProjectUploadWarning,
    urlValidation,
    showEnterpriseToken,
    activeAccessToken,
    repositoryNeedsAuthentication,
    shouldShowPatInput,
    resetAccessTokenValidationState,
    handleAccessTokenValidate,
    handleRepositoryContinue,
    handleLocalProjectFilesChange,
    handleLocalProjectUpload,
  } = connect;

  const browserWindow = window as Window & typeof globalThis & {
    folderInputRef?: HTMLInputElement | null;
    zipInputRef?: HTMLInputElement | null;
  };

  const localProjectMessage = localProjectCapabilitiesLoading
    ? "Checking local project support..."
    : localProjectCapabilities?.message ||
      "Upload projects using the folder picker or ZIP archive uploader below. The backend will extract and analyze your uploaded files.";
  const authenticationBannerText = showEnterpriseToken
    ? "GitHub Enterprise repository detected - authentication required"
    : "Private repository detected - authentication required";
  const tokenCardTitle = showEnterpriseToken
    ? "Enterprise Repository - Enter Personal Access Token"
    : "Private Repository - Enter Personal Access Token";
  const tokenDescription = showEnterpriseToken
    ? "This repository requires authentication. Provide a GitHub Personal Access Token before analysis."
    : "This repository requires authentication. Provide a GitHub Personal Access Token with repo scope.";
  const tokenStatusColor =
    accessTokenValidationState === "valid"
      ? "#166534"
      : accessTokenValidationState === "invalid"
        ? "#b45309"
        : "#9a3412";
  const tokenStatusIcon =
    accessTokenValidationState === "valid"
      ? <FaCheckCircle />
      : accessTokenValidationState === "invalid"
        ? <FaExclamationTriangle />
        : <FaInfoCircle />;
  return (
    <div style={styles.card}>
      <div style={styles.stepHeader}>
        {renderWizardIconBadge(<FaLink />, "#2563eb", "xl")}
        <div>
          <h2 style={styles.title}>Connect Repository</h2>
          <p style={styles.subtitle}>Enter a GitHub repository URL or analyze a local Java project to start migration analysis.</p>
        </div>
      </div>

      <div style={styles.field}>
        <label style={{ ...styles.label, display: "flex", alignItems: "center", gap: 8 }}>
          Repository URL
          <WizardInfoTooltip label="Repository URL formats" placement="left" width={220}>
            <div style={{ fontWeight: 600, marginBottom: 6, color: "#94a3b8" }}>Supported formats:</div>
            <div>- https://github.com/owner/repo</div>
            <div>- github.com/owner/repo</div>
            <div>- owner/repo</div>
          </WizardInfoTooltip>
        </label>
        <input
          type="text"
          style={{ ...styles.input, borderColor: urlValidation.valid ? '#22c55e' : repoUrl ? '#ef4444' : '#e2e8f0' }}
          value={repoUrl}
          onChange={(e) => {
            setRepoUrl(e.target.value);
            setSelectedRepo(null);
            onClearRepoAnalysis();
            setIsPrivateRepo(false);
            setPatToken("");
            resetAccessTokenValidationState();
            onError("");
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && urlValidation.valid) {
              void handleRepositoryContinue();
            }
          }}
          placeholder="https://github.com/owner/repository"
        />
        {!shouldShowPatInput && (
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 12, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <span>Public GitHub repositories can be analyzed without a token.</span>
            <button
              type="button"
              onClick={() => {
                setIsPrivateRepo(true);
                resetAccessTokenValidationState();
                onError("");
              }}
              style={{
                background: "none",
                border: "none",
                color: "#2563eb",
                cursor: "pointer",
                fontSize: 12,
                fontWeight: 600,
                padding: 0,
                textDecoration: "underline",
              }}
            >
              Have a Private Access Token (PAT)?
            </button>
          </div>
        )}
        {repoAccessCheckLoading && !shouldShowPatInput && (
          <div style={{ fontSize: 12, color: '#2563eb', marginTop: 8 }}>
            Checking repository access...
          </div>
        )}
        {shouldShowPatInput && (
          <div style={{ marginTop: 16 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 14,
                color: "#f59e0b",
                fontSize: 14,
                fontWeight: 600,
              }}
            >
              <FaLock />
              <span>{authenticationBannerText}</span>
            </div>
            <div
              style={{
                border: "1px solid #fbbf24",
                borderRadius: 18,
                padding: 20,
                background: "linear-gradient(180deg, #fff8db 0%, #fff4c2 100%)",
                boxShadow: "0 8px 18px rgba(245, 158, 11, 0.12)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 10,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#fff",
                    color: "#d97706",
                    boxShadow: "0 2px 8px rgba(217, 119, 6, 0.12)",
                  }}
                >
                  <FaLock />
                </div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "#9a3412" }}>{tokenCardTitle}</div>
                  <div style={{ fontSize: 13, color: "#b45309", marginTop: 4 }}>{tokenDescription}</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  type="password"
                  style={{
                    ...styles.input,
                    flex: "1 1 420px",
                    marginBottom: 0,
                    background: "#fff",
                    borderColor:
                      accessTokenValidationState === "valid"
                        ? "#22c55e"
                        : accessTokenValidationState === "invalid"
                          ? "#f59e0b"
                          : activeAccessToken
                            ? "#22c55e"
                            : "#e2e8f0",
                  }}
                  value={showEnterpriseToken ? githubToken : patToken}
                  onChange={(e) => {
                    resetAccessTokenValidationState();
                    if (showEnterpriseToken) {
                      setGithubToken(e.target.value);
                    } else {
                      setPatToken(e.target.value);
                    }
                  }}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  autoComplete="off"
                />
                <button
                  type="button"
                  style={{
                    ...styles.primaryBtn,
                    minWidth: 132,
                    opacity: accessTokenValidationState === "validating" ? 0.8 : 1,
                  }}
                  disabled={accessTokenValidationState === "validating"}
                  onClick={() => void handleAccessTokenValidate()}
                >
                  {accessTokenValidationState === "validating" ? "Validating..." : "Validate"}
                </button>
              </div>
              <div style={{ fontSize: 12, color: tokenStatusColor, marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
                {tokenStatusIcon}
                <span>
                  {accessTokenValidationMessage || (
                    <a href="https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token" target="_blank" rel="noopener noreferrer">
                      How to create a Personal Access Token?
                    </a>
                  )}
                </span>
              </div>
              {accessTokenValidationState === "valid" && (
                <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="button"
                    style={{
                      ...styles.primaryBtn,
                      background: "linear-gradient(135deg, #16a34a, #15803d)",
                      border: "none",
                      minWidth: 260,
                      fontWeight: 700,
                      fontSize: 15,
                      boxShadow: "0 4px 14px rgba(22,163,74,0.25)",
                    }}
                    onClick={() => void handleRepositoryContinue()}
                  >
                    {renderForwardButtonLabel("Continue with Authenticated Repository")}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
        {repositoryNeedsAuthentication && !activeAccessToken && accessTokenValidationState === "idle" && (
          <div style={{ fontSize: 12, color: "#b45309", marginTop: 8 }}>
            Add a PAT above before continuing with repository analysis.
          </div>
        )}
        {repoUrl && !urlValidation.valid && (
          <div style={{ fontSize: 12, color: '#ef4444', marginTop: 6 }}>
            Warning: {urlValidation.message}
          </div>
        )}
        {urlValidation.valid && (
          <div style={{ fontSize: 12, color: '#22c55e', marginTop: 6 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <FaCheckCircle />
              Valid repository URL
            </span>
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
        <div style={{ fontSize: 14, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em" }}>OR</div>
        <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
      </div>

      <div className="wizard-local-project-panel">
        <div className="wizard-local-project-header">
          {renderWizardIconBadge(<FaFolderOpen />, "#f59e0b", "lg")}
          <div>
            <div className="wizard-local-project-title">
              Upload Local Project
            </div>
            <div className="wizard-local-project-subtitle">
              Select a folder from your computer or upload a ZIP file for analysis.
            </div>
          </div>
        </div>

        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 12 }}>
          {localProjectMessage}
        </div>

        <div style={{ fontSize: 13, color: "#475569", marginBottom: 12 }}>
          Select a folder from your computer OR upload a ZIP archive. This sends the project contents to the backend for analysis.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="wizard-picker-grid">
              <div style={{ flex: 1, minWidth: 200 }}>
                <input
                  ref={(el) => {
                    if (el) {
                      browserWindow.folderInputRef = el;
                      el.setAttribute('webkitdirectory', '');
                      el.setAttribute('directory', '');
                    }
                  }}
                  type="file"
                  multiple
                  style={{ display: "none" }}
                  onChange={(e) => handleLocalProjectFilesChange(e.target.files)}
                />
                <div
                  onClick={() => {
                    browserWindow.folderInputRef?.click();
                  }}
                  className="wizard-picker-option"
                  style={buildWizardAccentVars("#f59e0b")}
                >
                  <span className="wizard-picker-option-label">
                    {renderWizardIconBadge(<FaFolderOpen />, "#f59e0b", "sm")}
                    <span>Select Folder</span>
                  </span>
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 200 }}>
                <input
                  ref={(el) => {
                    if (el) browserWindow.zipInputRef = el;
                  }}
                  type="file"
                  accept=".zip"
                  style={{ display: "none" }}
                  onChange={(e) => handleLocalProjectFilesChange(e.target.files)}
                />
                <div
                  onClick={() => {
                    browserWindow.zipInputRef?.click();
                  }}
                  className="wizard-picker-option"
                  style={buildWizardAccentVars("#8b5cf6")}
                >
                  <span className="wizard-picker-option-label">
                    {renderWizardIconBadge(<FaFileAlt />, "#8b5cf6", "sm")}
                    <span>Select ZIP File</span>
                  </span>
                </div>
              </div>
            </div>
            {localProjectUploadFiles.length > 0 && (
              <div style={{ fontSize: 13, color: "#334155" }}>
                Selected {localProjectUploadFiles.length} file{localProjectUploadFiles.length === 1 ? "" : "s"}.
              </div>
            )}
            {localProjectUploadWarning && (
              <div style={{ fontSize: 13, color: "#b45309" }}>{localProjectUploadWarning}</div>
            )}
            {localProjectUploadCompressing && (
              <div style={{ fontSize: 13, color: "#0f766e" }}>Compressing selected folder to ZIP before upload...</div>
            )}
            {localProjectUploadError && (
              <div style={{ fontSize: 13, color: "#b91c1c" }}>{localProjectUploadError}</div>
            )}
            <button
              style={{ ...styles.primaryBtn, minWidth: 140, opacity: localProjectUploadFiles.length === 0 || localProjectUploadLoading || localProjectCapabilities?.enabled === false ? 0.5 : 1, display: "flex", alignItems: "center", gap: 8, justifyContent: "center" }}
              disabled={localProjectUploadFiles.length === 0 || localProjectUploadLoading || localProjectCapabilities?.enabled === false}
              onClick={() => void handleLocalProjectUpload()}
            >
              {localProjectUploadLoading ? (
                "Uploading..."
              ) : (
                <span className="wizard-button-content">
                  {renderWizardIconBadge(<FaUpload />, "#2563eb", "sm")}
                  <span>Upload and Analyze</span>
                </span>
              )}
            </button>
          </div>
      </div>

      <div style={styles.btnRow}>
        <button
          style={{
            ...styles.primaryBtn,
            opacity:
              connecting ||
              !urlValidation.valid ||
              (shouldShowPatInput && accessTokenValidationState !== "valid")
                ? 0.5
                : 1,
          }}
          disabled={
            connecting ||
            !urlValidation.valid ||
            (shouldShowPatInput && accessTokenValidationState !== "valid")
          }
          onClick={() => void handleRepositoryContinue()}
        >
          {connecting
            ? "Verifying repository..."
            : renderForwardButtonLabel(
                shouldShowPatInput && accessTokenValidationState === "valid"
                  ? "Continue with Authenticated Repository"
                  : shouldShowPatInput
                    ? "Validate PAT to Continue"
                    : "Continue"
              )}
        </button>
      </div>
    </div>
  );
}
