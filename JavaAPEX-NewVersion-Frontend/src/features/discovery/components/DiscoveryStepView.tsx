import React from "react";
import { FaCheckCircle, FaSearch, FaStopwatch } from "react-icons/fa";
import { wizardStyles as styles } from "@/shared/components/wizard/wizardStyles";
import { renderWizardIconBadge, renderStatusChip, renderBackButtonLabel, renderForwardButtonLabel } from "@/shared/components/wizard";
import type { RepoAnalysis, RepoFile, RepoInfo } from "@/shared/types/domain";
import { getFileContent } from "../services/discoveryService";
import { getLocalProjectFileContent } from "@/features/connect/services/connectService";
import { DiscoveryLoader } from "./DiscoveryLoader";
import MicroserviceAssessment from "./MicroserviceAssessment";
import type { useDiscoveryState } from "../hooks/useDiscoveryState";

const DiscoveryFileExplorer = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryFileExplorer };
});
const DiscoveryFrameworkSection = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryFrameworkSection };
});
const DiscoveryHighRiskWarning = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryHighRiskWarning };
});
const DiscoveryNoFrameworkAlert = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryNoFrameworkAlert };
});
const DiscoveryNotJavaAlert = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryNotJavaAlert };
});
const DiscoveryProjectStructureSummary = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryProjectStructureSummary };
});
const DiscoveryTechnicalSpecificationCard = React.lazy(async () => {
  const module = await import("./MigrationDiscoverySections");
  return { default: module.DiscoveryTechnicalSpecificationCard };
});

interface MicroserviceAccordionKeyed {
  isLocalRepoRef: (value: string | null | undefined) => boolean;
  extractLocalRepoPath: (value: string) => string;
}

interface DiscoveryStepViewProps {
  discovery: ReturnType<typeof useDiscoveryState>;
  selectedRepo: RepoInfo | null;
  currentToken: string;
  repoUtils: MicroserviceAccordionKeyed;
  sourceVersionStatus: "detected" | "not_selected" | "unknown";
  applyDetectedSourceVersion: (version: string, status: "detected" | "unknown") => void;
  setUserSelectedVersion: (version: string | null) => void;
  documentGenerationLoading: "brd" | null;
  conversionDecision: "yes" | "no" | null;
  setConversionDecision: (value: "yes" | "no" | null) => void;
  showFolderStructure: boolean;
  setShowFolderStructure: (value: boolean) => void;
  handleCheckMicroserviceEligibility: () => Promise<void>;
  handleGenerateBrdDocument: () => Promise<void>;
  handleOpenFrameworkFile: (framework: { name: string; path: string; type: string }) => Promise<void>;
  isDiscoveryPending: boolean;
  formattedAnalysisElapsed: string;
  formattedAnalysisCompleted: string;
  detectedJavaStructureLabel: string;
  technicalSpecificationButtonLabel: string;
  technicalSpecificationHelperText: string;
  onBack: () => void;
  onChooseDifferentRepository: () => void;
  onContinueToStrategy: () => void;
  onError: (message: string) => void;
}

export function DiscoveryStepView({
  discovery,
  selectedRepo,
  currentToken,
  repoUtils,
  sourceVersionStatus,
  applyDetectedSourceVersion,
  setUserSelectedVersion,
  documentGenerationLoading,
  conversionDecision,
  setConversionDecision,
  showFolderStructure,
  setShowFolderStructure,
  handleCheckMicroserviceEligibility,
  handleGenerateBrdDocument,
  handleOpenFrameworkFile,
  isDiscoveryPending,
  formattedAnalysisElapsed,
  formattedAnalysisCompleted,
  detectedJavaStructureLabel,
  technicalSpecificationButtonLabel,
  technicalSpecificationHelperText,
  onBack,
  onChooseDifferentRepository,
  onContinueToStrategy,
  onError,
}: DiscoveryStepViewProps) {
  const {
    repoAnalysis,
    repoFiles,
    currentPath,
    setCurrentPath,
    selectedFile,
    setSelectedFile,
    fileContent,
    setFileContent,
    editedContent,
    setEditedContent,
    isEditing,
    setIsEditing,
    fileLoading,
    setFileLoading,
    pathHistory,
    setPathHistory,
    showFileExplorer,
    setShowFileExplorer,
    isJavaProject,
    setIsJavaProject,
    isHighRiskProject,
    setIsHighRiskProject,
    highRiskConfirmed,
    setHighRiskConfirmed,
    suggestedJavaVersion,
    setSuggestedJavaVersion,
    detectedFrameworks,
    viewingFrameworkFile,
    setViewingFrameworkFile,
    frameworkFileLoading,
    microserviceResult,
    microserviceLoading,
    analysisElapsedSeconds,
  } = discovery;

  const { isLocalRepoRef, extractLocalRepoPath } = repoUtils;

  const handleFileClick = async (file: RepoFile) => {
    if (file.type === "dir") {
      setPathHistory((prev) => [...prev, file.path]);
      setCurrentPath(file.path);
      setSelectedFile(null);
      setFileContent("");
      setEditedContent("");
      setIsEditing(false);
    } else {
      setFileLoading(true);
      setSelectedFile(file);
      try {
        const response = isLocalRepoRef(selectedRepo!.url)
          ? await getLocalProjectFileContent(extractLocalRepoPath(selectedRepo!.url), file.path)
          : await getFileContent(selectedRepo!.url, file.path, currentToken);
        setFileContent(response.content);
        setEditedContent(response.content);
      } catch {
        onError("Failed to load file content");
      } finally {
        setFileLoading(false);
      }
    }
  };

  const navigateBack = () => {
    if (pathHistory.length > 1) {
      const newHistory = [...pathHistory];
      newHistory.pop();
      setPathHistory(newHistory);
      setCurrentPath(newHistory[newHistory.length - 1]);
      setSelectedFile(null);
      setFileContent("");
      setEditedContent("");
      setIsEditing(false);
    }
  };

  const navigateToRoot = () => {
    setPathHistory([""]);
    setCurrentPath("");
    setSelectedFile(null);
    setFileContent("");
    setEditedContent("");
    setIsEditing(false);
  };

  const detectedJavaVersion = repoAnalysis?.java_version || repoAnalysis?.java_version_from_build || null;

  return (
    <div style={styles.card}>
      <div style={styles.stepHeader}>
        {renderWizardIconBadge(<FaSearch />, "#0ea5e9", "xl")}
        <div>
          <h2 style={styles.discoveryStepTitle}>Repository Discovery &amp; Dependencies</h2>
          <p style={styles.discoveryStepSubtitle}>Explore the repository structure, dependencies, and frameworks detected.</p>
        </div>
        {isDiscoveryPending &&
          renderStatusChip(
            <FaStopwatch />,
            "#f97316",
            "Analysing...",
            formattedAnalysisElapsed,
            "warning"
          )}
        {!isDiscoveryPending &&
          repoAnalysis &&
          renderStatusChip(
            <FaCheckCircle />,
            "#22c55e",
            "Completed",
            formattedAnalysisCompleted,
            "success"
          )}
      </div>

      {selectedRepo && (
        <React.Suspense
          fallback={
            <DiscoveryLoader
              compact
              title="Loading discovery workspace"
              subtitle="Preparing the repository intelligence panels and analysis surfaces."
              elapsedSeconds={0}
            />
          }
        >
        <>
          {isDiscoveryPending ? (
            <DiscoveryLoader
              title="Analyzing your repository"
              subtitle="Mapping structure, previewing changes, reading dependencies, and estimating microservice readiness."
              elapsedLabel={formattedAnalysisElapsed}
              elapsedSeconds={analysisElapsedSeconds}
            />
          ) : (
            <>
              {isJavaProject === false ? (
                <DiscoveryNotJavaAlert
                  onChooseDifferentRepository={() => {
                    onChooseDifferentRepository();
                    setIsJavaProject(null);
                  }}
                />
              ) : null}

              <DiscoveryNoFrameworkAlert
                isVisible={Boolean(isJavaProject && detectedFrameworks.length === 0)}
              />

              {isJavaProject !== false && (
                <>
                  <DiscoveryHighRiskWarning
                    isVisible={Boolean(isHighRiskProject && !highRiskConfirmed)}
                    missingBuildFiles={Boolean(!repoAnalysis?.structure?.has_pom_xml && !repoAnalysis?.structure?.has_build_gradle)}
                    missingJavaVersion={Boolean(!((repoAnalysis?.java_version || repoAnalysis?.java_version_from_build)) || (repoAnalysis?.java_version || repoAnalysis?.java_version_from_build) === "unknown")}
                    missingSrcMain={Boolean(!repoAnalysis?.structure?.has_src_main)}
                    sourceVersionStatus={sourceVersionStatus}
                    suggestedJavaVersion={suggestedJavaVersion}
                    buildConversionLabel="Proceed with migration"
                    buildConversionNote="No specific build tool conversion detected."
                    onSuggestedJavaVersionChange={(value) => {
                      setSuggestedJavaVersion(value);
                      applyDetectedSourceVersion(value === "auto" ? "8" : value, "detected");
                      setUserSelectedVersion(value);
                    }}
                    onConfirm={() => {
                      setHighRiskConfirmed(true);
                      applyDetectedSourceVersion(suggestedJavaVersion, sourceVersionStatus === "unknown" ? "unknown" : "detected");
                    }}
                    onChooseDifferentRepository={() => {
                      onChooseDifferentRepository();
                      setIsJavaProject(null);
                      setIsHighRiskProject(false);
                    }}
                  />

                  {(!isHighRiskProject || highRiskConfirmed) && (
                    <>
                      <DiscoveryFileExplorer
                        styles={styles}
                        repositoryName={selectedRepo.name}
                        currentPath={currentPath}
                        showFileExplorer={showFileExplorer}
                        selectedFile={selectedFile}
                        repoFiles={repoFiles}
                        fileLoading={fileLoading}
                        fileContent={fileContent}
                        isEditing={isEditing}
                        editedContent={editedContent}
                        onToggleExplorer={() => setShowFileExplorer(!showFileExplorer)}
                        onNavigateRoot={navigateToRoot}
                        onNavigateBack={navigateBack}
                        onFileClick={handleFileClick}
                        onCloseSelectedFile={() => {
                          setSelectedFile(null);
                          setFileContent("");
                          setEditedContent("");
                          setIsEditing(false);
                        }}
                        onEditedContentChange={setEditedContent}
                      />

                      <DiscoveryFrameworkSection
                        styles={styles}
                        detectedFrameworks={detectedFrameworks}
                        dependencies={repoAnalysis?.dependencies}
                        viewingFrameworkFile={viewingFrameworkFile}
                        frameworkFileLoading={frameworkFileLoading}
                        onClosePreview={() => setViewingFrameworkFile(null)}
                        onOpenFramework={handleOpenFrameworkFile}
                      />

                      {repoAnalysis && (
                        <DiscoveryProjectStructureSummary
                          styles={styles}
                          structure={repoAnalysis.structure}
                          detectedJavaVersion={detectedJavaVersion}
                          detectedJavaStructureLabel={detectedJavaStructureLabel}
                        />
                      )}

                      {repoAnalysis && (
                        <MicroserviceAssessment
                          repoAnalysis={repoAnalysis as RepoAnalysis}
                          microserviceResult={microserviceResult}
                          microserviceLoading={microserviceLoading}
                          loading={discovery.analysisLoading}
                          handleCheckMicroserviceEligibility={handleCheckMicroserviceEligibility}
                          conversionDecision={conversionDecision}
                          setConversionDecision={setConversionDecision}
                          showFolderStructure={showFolderStructure}
                          setShowFolderStructure={setShowFolderStructure}
                          styles={styles}
                        />
                      )}

                      {repoAnalysis && (
                        <DiscoveryTechnicalSpecificationCard
                          styles={styles}
                          disabled={documentGenerationLoading !== null || !repoAnalysis}
                          buttonLabel={technicalSpecificationButtonLabel}
                          helperText={technicalSpecificationHelperText}
                          onGenerate={() => {
                            void handleGenerateBrdDocument();
                          }}
                        />
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}
        </>
        </React.Suspense>
      )}

      <div style={styles.btnRow}>
        <button style={styles.secondaryBtn} onClick={onBack}>{renderBackButtonLabel()}</button>
        <button
          style={{ ...styles.primaryBtn, opacity: isJavaProject === false || (isHighRiskProject && !highRiskConfirmed) || isDiscoveryPending || !repoAnalysis ? 0.5 : 1 }}
          onClick={onContinueToStrategy}
          disabled={isJavaProject === false || (isHighRiskProject && !highRiskConfirmed) || isDiscoveryPending || !repoAnalysis}
        >
          {renderForwardButtonLabel("Continue to Strategy")}
        </button>
      </div>
    </div>
  );
}
