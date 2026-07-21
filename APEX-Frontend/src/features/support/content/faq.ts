export interface FaqEntry {
  question: string;
  answer: string;
}

export const SUPPORT_FAQ: FaqEntry[] = [
  {
    question: "How long does a migration take?",
    answer:
      "It depends on the repository size and the number of conversions selected. Most single-module Spring Boot projects complete within a few minutes of automated modernization plus a build validation pass.",
  },
  {
    question: "Is my source code or GitHub token stored?",
    answer:
      "The repository is cloned into a per-job workspace to run analysis and migration, and job artifacts (reports, logs) are kept so you can review results. Tokens you provide are used only to authenticate the clone/push for that job.",
  },
  {
    question: "Can I migrate a private repository?",
    answer: "Yes — provide a GitHub personal access token with repo access when connecting a private repository.",
  },
  {
    question: "What if the post-migration build fails?",
    answer:
      "The platform automatically diagnoses common build failures and retries with adjusted transformations, up to a bounded number of attempts. If it still fails, the Result page and this Support form's \"Migration Error Help\" tab both explain what to check.",
  },
];

export const TROUBLESHOOTING_GUIDE: FaqEntry[] = [
  {
    question: "Connect step fails with \"Repository not found\"",
    answer: "Double-check the repository URL and, for private repositories, that a valid token with repo access was provided.",
  },
  {
    question: "Discovery fails with \"Unsupported project\"",
    answer: "Discovery requires a Maven (pom.xml) or Gradle (build.gradle/build.gradle.kts) project at the repository root or in a detected module.",
  },
  {
    question: "Migration seems stuck",
    answer: "Open the Result page to check live progress and logs. Large repositories with many transformations can take longer than expected — the job continues running in the background.",
  },
];

export const MIGRATION_ERROR_HELP: FaqEntry[] = [
  {
    question: "\"BUILD FAILED\" after migration",
    answer:
      "Check the build modernization steps and retry attempts shown in the migration report — the platform records the root cause it diagnosed and which transformations it added on each retry.",
  },
  {
    question: "Dependency resolution errors",
    answer:
      "Review the Dependency Changes section in Docs — a dependency upgrade pinned by the migration may conflict with another BOM/version already declared in the project.",
  },
  {
    question: "Still stuck?",
    answer: "Use the Contact Support or Report an Issue form below with the Job ID (auto-filled if you have an active job) so we can look at the specific run.",
  },
];
