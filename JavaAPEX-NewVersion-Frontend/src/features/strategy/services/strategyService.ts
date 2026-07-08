import { requestJson } from "@/services/http/client";
import type { DependencyInfo } from "@/shared/types/domain";

export interface JavaVersionInfo {
  source_versions: { value: string; label: string }[];
  target_versions: { value: string; label: string }[];
}

export interface JavaVersionRecommendationRequest {
  source_java_version: string;
  detected_java_version?: string | null;
  build_tool?: string | null;
  dependencies: DependencyInfo[];
  has_tests: boolean;
  api_endpoint_count: number;
  risk_level?: string | null;
  llm_provider?: string | null;
}

export interface JavaVersionRecommendationResponse {
  recommended_target_version: string;
  recommended_versions?: string[];
  confidence: string;
  rationale: string[];
  alternatives: string[];
  provider_used?: string;
  alternative_options?: Array<{
    version: string;
    risk?: string;
    reason?: string;
  }>;
  raw_recommendation?: Record<string, unknown>;
}

// Canonical Java release list used to populate the source/target dropdowns.
// LTS releases are flagged so the UI can label them "(LTS)".
const JAVA_RELEASES: { value: string; lts: boolean }[] = [
  { value: "8", lts: true },
  { value: "9", lts: false },
  { value: "10", lts: false },
  { value: "11", lts: true },
  { value: "12", lts: false },
  { value: "13", lts: false },
  { value: "14", lts: false },
  { value: "15", lts: false },
  { value: "16", lts: false },
  { value: "17", lts: true },
  { value: "18", lts: false },
  { value: "19", lts: false },
  { value: "20", lts: false },
  { value: "21", lts: true },
  { value: "22", lts: false },
  { value: "23", lts: false },
  { value: "24", lts: false },
  { value: "25", lts: true },
];

function buildJavaVersionOptions(): { value: string; label: string }[] {
  return JAVA_RELEASES.map(({ value, lts }) => ({
    value,
    label: `Java ${value}${lts ? " (LTS)" : ""}`,
  }));
}

// Get available Java versions. Served from the canonical list above (no network
// round-trip) so the dropdowns always populate reliably.
export async function getJavaVersions(): Promise<JavaVersionInfo> {
  const options = buildJavaVersionOptions();
  return { source_versions: options, target_versions: options };
}

export async function getJavaVersionRecommendation(
  request: JavaVersionRecommendationRequest
): Promise<JavaVersionRecommendationResponse> {
  return requestJson<JavaVersionRecommendationResponse>(
    "/java-version-recommendation",
    "Failed to get Java version recommendation",
    {
      method: "POST",
      body: request,
    }
  );
}

export interface StrategyQueryRequest {
  repo_url?: string;
  question: string;
  analysis?: unknown;
  strategy_context?: StrategyPageContext | null;
  provider?: string | null;
}

export interface StrategyPageContext {
  page?: string;
  repository?: {
    name?: string | null;
    full_name?: string | null;
    url?: string | null;
    language?: string | null;
  };
  assessment?: {
    risk_level?: string | null;
    risk_reason?: string | null;
    build_tool?: string | null;
    java_version?: string | null;
    has_tests?: boolean | null;
    dependency_count?: number | null;
  };
  strategy?: {
    source_java_version?: string | null;
    target_java_version?: string | null;
    selected_conversions?: string[];
    source_already_at_latest_supported_version?: boolean | null;
  };
  migration_destination?: {
    approach?: string | null;
    label?: string | null;
    description?: string | null;
    target_repo_name?: string | null;
    target_repo_owner?: string | null;
    target_repo_host?: string | null;
    target_repo_name_editable?: boolean | null;
    target_repo_name_source?: string | null;
  };
  migration_approach_options?: Array<{
    value?: string | null;
    label?: string | null;
    desc?: string | null;
    tooltip?: string | null;
  }>;
  recommendation?: {
    recommended_target_version?: string | null;
    recommended_versions?: string[];
    confidence?: string | null;
    rationale?: string[];
    alternatives?: string[];
    alternative_options?: Array<{
      version: string;
      risk?: string;
      reason?: string;
    }>;
  };
  dependency_overview?: Array<{
    group_id?: string | null;
    artifact_id?: string | null;
    current_version?: string | null;
    status?: string | null;
  }>;
  dependency_risk_summary?: {
    critical?: number;
    high?: number;
    medium?: number;
    low?: number;
  };
  attention_dependencies?: Array<{
    display_name?: string | null;
    current_version?: string | null;
    risk?: string | null;
    reason?: string | null;
    status?: string | null;
    category?: string | null;
  }>;
  conversion_options?: Array<{
    key: string;
    title: string;
    status: string;
    description?: string;
  }>;
}

export interface StrategyAnswerResponse {
  answer: string;
  rationale?: string[];
  details?: Record<string, unknown>;
}

export async function queryStrategy(
  request: StrategyQueryRequest
): Promise<StrategyAnswerResponse> {
  return requestJson<StrategyAnswerResponse>(
    "/strategy/query",
    "Failed to query strategy assistant",
    {
      method: "POST",
      body: request,
    }
  );
}
