import { useState } from "react";
import type { PersistedWizardFormState } from "@/shared/utils/migrationWizardStorage";

export function useModernizationState(persistedFormState: PersistedWizardFormState | null) {
  const [runTests, setRunTests] = useState(persistedFormState?.runTests ?? true);
  const [useLLMTests, setUseLLMTests] = useState(false);
  const [selectedLLMProvider, setSelectedLLMProvider] = useState("huggingface");
  const [runSonar, setRunSonar] = useState(persistedFormState?.runSonar ?? true);
  const [runFossa, setRunFossa] = useState(persistedFormState?.runFossa ?? false);
  const [fixBusinessLogic, setFixBusinessLogic] = useState(
    persistedFormState?.fixBusinessLogic ?? true
  );

  return {
    runTests,
    setRunTests,
    useLLMTests,
    setUseLLMTests,
    selectedLLMProvider,
    setSelectedLLMProvider,
    runSonar,
    setRunSonar,
    runFossa,
    setRunFossa,
    fixBusinessLogic,
    setFixBusinessLogic,
  };
}
