export interface FaqEntry {
  question: string;
  answer: string;
}

export const DOCS_FAQ: FaqEntry[] = [
  {
    question: "What does the Java Migration Accelerator do?",
    answer:
      "It connects to a Java repository, analyzes its build tool, Java version, frameworks, and dependencies, then applies automated modernization transformations to upgrade the codebase to a target Java version — tracking every dependency change and source code change along the way.",
  },
  {
    question: "Where does the data in this Documentation view come from?",
    answer:
      "Every section is generated from the same analysis and migration data produced during Connect, Discovery, and Start Migration for your current job — nothing here is mocked or hardcoded. Sections tied to a completed migration only appear once that stage has run.",
  },
  {
    question: "Why do some sections show a placeholder instead of data?",
    answer:
      "Migration Strategy, Dependency Changes, Source Code Changes, and the Migration Report all depend on Start Migration having completed for this job. Until then, those sections show a short explanation instead of an error.",
  },
  {
    question: "Can I download this documentation?",
    answer:
      "Yes. Use \"Download HTML\" or \"Download PDF\" at the top of the Documentation panel to export the full generated document for the current job, including the repository analysis and migration report sections.",
  },
  {
    question: "How do I start a migration to see the full report?",
    answer:
      "Close this panel and follow the wizard: Connect a repository, run Discovery, choose a migration strategy, then Start Migration. Once it completes, reopen Docs to see the full report.",
  },
];

export const DOCS_USER_GUIDE: FaqEntry[] = [
  {
    question: "1. Connect",
    answer: "Provide a GitHub repository URL (and a personal access token if it's private) to begin.",
  },
  {
    question: "2. Discovery",
    answer:
      "The repository is cloned and analyzed: build tool, current Java version, frameworks, dependencies, and module layout are detected automatically.",
  },
  {
    question: "3. Strategy",
    answer: "Choose a target Java version and the conversions (Spring Boot, dependency upgrades, etc.) to apply.",
  },
  {
    question: "4. Start Migration",
    answer:
      "Automated modernization transformations run against the repository. The build is validated afterward, with automatic diagnose-and-retry if it fails.",
  },
  {
    question: "5. Result & Docs",
    answer:
      "Review the migration report, dependency changes, and code changes on the Result page, or open this Documentation panel any time for the same information in one place.",
  },
];
