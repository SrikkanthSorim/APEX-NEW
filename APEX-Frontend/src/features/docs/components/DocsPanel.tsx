import React, { useEffect, useState } from "react";
import Drawer from "@/shared/components/ui/Drawer";
import { ApiError } from "@/services/http/client";
import { readPersistedValue, WIZARD_JOB_ID_KEY } from "@/shared/utils/migrationWizardStorage";
import { downloadHtmlAsPdf, downloadHtmlDocument } from "@/features/result/utils/migrationWizardPdf";
import { getProjectDocs, getProjectDocsHtml, type ProjectDocsResponse } from "../services/docsService";
import { DOCS_FAQ, DOCS_USER_GUIDE } from "../content/faq";
import "./DocsPanel.css";

interface DocsPanelProps {
  open: boolean;
  onClose: () => void;
  onNavigateToSupport: () => void;
}

type LoadState = "idle" | "loading" | "empty" | "ready" | "error";

const EMPTY_STATE_MESSAGE =
  "No repository analyzed yet. Please connect a repository to view the documentation.";

const hasValidRepositoryDocs = (docs: ProjectDocsResponse): boolean => {
  if (!docs.has_repository_analysis) return false;
  return Boolean(
    docs.detected_java_version ||
      docs.build_tool ||
      docs.project_type ||
      docs.frameworks.length > 0 ||
      docs.dependencies.length > 0 ||
      docs.modules.length > 0
  );
};

const renderList = (items: unknown[]): React.ReactNode => {
  if (!items || items.length === 0) {
    return <p className="docs-muted">No data available for this section.</p>;
  }
  return (
    <ul className="docs-list">
      {items.map((item, index) => (
        <li key={index}>
          {typeof item === "object" && item !== null
            ? Object.entries(item as Record<string, unknown>)
                .map(([key, value]) => `${key}: ${String(value)}`)
                .join(", ")
            : String(item)}
        </li>
      ))}
    </ul>
  );
};

const DocsPanel: React.FC<DocsPanelProps> = ({ open, onClose, onNavigateToSupport }) => {
  const [state, setState] = useState<LoadState>("idle");
  const [docs, setDocs] = useState<ProjectDocsResponse | null>(null);
  const [isExporting, setIsExporting] = useState<"html" | "pdf" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;

    const jobId = readPersistedValue(WIZARD_JOB_ID_KEY);
    if (!jobId) {
      setState("empty");
      setDocs(null);
      return;
    }

    setState("loading");
    setExportError(null);
    getProjectDocs(jobId)
      .then((response) => {
        if (!hasValidRepositoryDocs(response)) {
          setDocs(null);
          setState("empty");
          return;
        }
        setDocs(response);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) {
          setState("empty");
          setDocs(null);
          return;
        }
        setState("error");
      });
  }, [open]);

  const handleExport = async (format: "html" | "pdf") => {
    const jobId = readPersistedValue(WIZARD_JOB_ID_KEY);
    if (!jobId || !docs || !hasValidRepositoryDocs(docs)) return;

    setIsExporting(format);
    setExportError(null);
    try {
      const { filename, html } = await getProjectDocsHtml(jobId);
      if (format === "html") {
        await downloadHtmlDocument(html, filename);
      } else {
        await downloadHtmlAsPdf(html, filename.replace(/\.html$/i, ".pdf"));
      }
    } catch {
      setExportError("Could not prepare the document for download. Please try again.");
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <Drawer open={open} title="Documentation" onClose={onClose} widthPx={560}>
      {(state === "loading") && <p className="docs-muted">Loading project documentation...</p>}

      {state === "error" && (
        <p className="docs-error">Something went wrong loading documentation. Please try again.</p>
      )}

      {state === "empty" && (
        <div className="docs-empty-state">
          <h3>Documentation unavailable</h3>
          <p>{EMPTY_STATE_MESSAGE}</p>
        </div>
      )}

      {state === "ready" && docs && (
        <div className="docs-sections">
          <div className="docs-export-row">
            <button
              type="button"
              className="docs-export-button"
              onClick={() => handleExport("html")}
              disabled={isExporting !== null}
            >
              {isExporting === "html" ? "Preparing..." : "Download HTML"}
            </button>
            <button
              type="button"
              className="docs-export-button"
              onClick={() => handleExport("pdf")}
              disabled={isExporting !== null}
            >
              {isExporting === "pdf" ? "Preparing..." : "Download PDF"}
            </button>
          </div>
          {exportError && <p className="docs-error">{exportError}</p>}

          <section className="docs-section">
            <h3>Project Overview</h3>
            <p>
              <strong>{docs.project_name || "Unknown project"}</strong>
              {docs.repo_url && <span className="docs-muted"> — {docs.repo_url}</span>}
            </p>
          </section>

          <section className="docs-section">
            <h3>Detected Java Version</h3>
            <p>{docs.detected_java_version || "Not detected yet — run Discovery."}</p>
          </section>

          <section className="docs-section">
            <h3>Target Java Version</h3>
            <p>{docs.target_java_version || "Not selected yet — complete the Strategy step."}</p>
          </section>

          <section className="docs-section">
            <h3>Build Tool</h3>
            <p>{docs.build_tool || "Not detected yet."}</p>
          </section>

          <section className="docs-section">
            <h3>Frameworks &amp; Dependencies</h3>
            <p className="docs-muted">Frameworks:</p>
            {renderList(docs.frameworks)}
            <p className="docs-muted">Dependencies ({docs.dependencies.length}):</p>
            {renderList(docs.dependencies.slice(0, 25))}
          </section>

          <section className="docs-section">
            <h3>Repository Structure</h3>
            <p className="docs-muted">Modules:</p>
            {renderList(docs.modules)}
          </section>

          <section className="docs-section">
            <h3>Migration Strategy</h3>
            {docs.strategy.has_migration_run ? (
              <ul className="docs-list">
                <li>Target Java Version: {docs.strategy.target_java_version || "-"}</li>
                <li>Conversion Types: {docs.strategy.conversion_types.join(", ") || "-"}</li>
                <li>Build Status: {docs.strategy.build_status || "Unknown"}</li>
                <li>Build Success: {docs.strategy.build_success ? "Yes" : "No"}</li>
              </ul>
            ) : (
              <p className="docs-muted">
                No migration has been run for this project yet. Run Start Migration to populate
                this section.
              </p>
            )}
          </section>

          <section className="docs-section">
            <h3>Dependency Changes</h3>
            {renderList(docs.strategy.dependency_upgrades)}
          </section>

          <section className="docs-section">
            <h3>Source Code Changes</h3>
            <p className="docs-muted">Import Changes:</p>
            {renderList(docs.strategy.import_changes)}
            <p className="docs-muted">Source File Changes:</p>
            {renderList(docs.strategy.source_changes)}
          </section>

          <section className="docs-section">
            <h3>Migration Report</h3>
            <p>{docs.strategy.migration_summary || "No migration summary available yet."}</p>
          </section>
        </div>
      )}

      {state === "ready" && docs && (
        <>
          <section className="docs-section">
            <h3>FAQ</h3>
            {DOCS_FAQ.map((entry) => (
              <div key={entry.question} className="docs-faq-entry">
                <p className="docs-faq-question">{entry.question}</p>
                <p className="docs-muted">{entry.answer}</p>
              </div>
            ))}
          </section>

          <section className="docs-section">
            <h3>User Guide</h3>
            {DOCS_USER_GUIDE.map((entry) => (
              <div key={entry.question} className="docs-faq-entry">
                <p className="docs-faq-question">{entry.question}</p>
                <p className="docs-muted">{entry.answer}</p>
              </div>
            ))}
          </section>
        </>
      )}

      <section className="docs-section">
        <button type="button" className="docs-link-button" onClick={onNavigateToSupport}>
          Need more help? Open Support →
        </button>
      </section>
    </Drawer>
  );
};

export default DocsPanel;
