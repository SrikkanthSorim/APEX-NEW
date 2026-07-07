import { useState } from "react";
import type { PersistedWizardFormState } from "../../../utils/migrationWizardStorage";

export type MigrationApproachValue = "fork" | "branch" | "local";

export interface JavaVersionOption {
  value: string;
  label: string;
}

export function useStrategyState(
  persistedFormState: PersistedWizardFormState | null,
  generateRepoTimestamp: () => string
) {
  const [targetRepoNamesByApproach, setTargetRepoNamesByApproach] = useState<{
    fork: string;
    branch: string;
    local: string;
  }>(() => {
    if (persistedFormState?.targetRepoNamesByApproach) {
      return {
        fork: persistedFormState.targetRepoNamesByApproach.fork ?? "",
        branch: persistedFormState.targetRepoNamesByApproach.branch ?? "",
        local: persistedFormState.targetRepoNamesByApproach.local ?? "",
      };
    }

    const fallbackTargetName = persistedFormState?.targetRepoName ?? "";
    return {
      fork: persistedFormState?.migrationApproach === "fork" ? fallbackTargetName : "",
      branch: persistedFormState?.migrationApproach === "branch" ? fallbackTargetName : "",
      local: persistedFormState?.migrationApproach === "local" ? fallbackTargetName : "",
    };
  });
  const [targetRepoNameEditedByApproach, setTargetRepoNameEditedByApproach] = useState<{
    fork: boolean;
    branch: boolean;
    local: boolean;
  }>(() => ({
    fork: persistedFormState?.targetRepoNameEditedByApproach?.fork ?? false,
    branch: persistedFormState?.targetRepoNameEditedByApproach?.branch ?? false,
    local: persistedFormState?.targetRepoNameEditedByApproach?.local ?? false,
  }));
  const [targetRepoTimestamp, setTargetRepoTimestamp] = useState(
    () => persistedFormState?.targetRepoTimestamp ?? generateRepoTimestamp()
  );
  const [targetVersions, setTargetVersions] = useState<JavaVersionOption[]>([]);
  const [selectedSourceVersion, setSelectedSourceVersion] = useState(
    persistedFormState?.selectedSourceVersion ?? "8"
  );
  const [selectedTargetVersion, setSelectedTargetVersion] = useState(
    persistedFormState?.selectedTargetVersion ?? ""
  );
  const [selectedConversions, setSelectedConversions] = useState<string[]>(
    persistedFormState?.selectedConversions ?? ["java_version"]
  );
  const [targetVersionRequiredError, setTargetVersionRequiredError] = useState(false);
  const [targetRepoNameError, setTargetRepoNameError] = useState("");
  const [migrationApproach, setMigrationApproach] = useState<MigrationApproachValue>(
    (persistedFormState?.migrationApproach as MigrationApproachValue | undefined) ?? "fork"
  );
  const [userSelectedVersion, setUserSelectedVersion] = useState<string | null>(
    persistedFormState?.userSelectedVersion ?? null
  );
  const [sourceVersionStatus, setSourceVersionStatus] = useState<"detected" | "not_selected" | "unknown">(
    persistedFormState?.sourceVersionStatus ?? "unknown"
  );
  const [updateSourceVersion] = useState(
    persistedFormState?.updateSourceVersion ?? false
  );

  function applyDetectedSourceVersion(version: string, status: "detected" | "unknown") {
    setSelectedSourceVersion(version);
    setSourceVersionStatus(status);
  }

  function resetTargetRepoNaming() {
    setTargetRepoNamesByApproach({ fork: "", branch: "", local: "" });
    setTargetRepoNameEditedByApproach({ fork: false, branch: false, local: false });
    setTargetRepoNameError("");
  }

  return {
    targetRepoNamesByApproach,
    setTargetRepoNamesByApproach,
    targetRepoNameEditedByApproach,
    setTargetRepoNameEditedByApproach,
    targetRepoTimestamp,
    setTargetRepoTimestamp,
    targetVersions,
    setTargetVersions,
    selectedSourceVersion,
    setSelectedSourceVersion,
    selectedTargetVersion,
    setSelectedTargetVersion,
    selectedConversions,
    setSelectedConversions,
    targetVersionRequiredError,
    setTargetVersionRequiredError,
    targetRepoNameError,
    setTargetRepoNameError,
    migrationApproach,
    setMigrationApproach,
    userSelectedVersion,
    setUserSelectedVersion,
    sourceVersionStatus,
    setSourceVersionStatus,
    updateSourceVersion,
    applyDetectedSourceVersion,
    resetTargetRepoNaming,
  };
}
