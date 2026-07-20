import React, { useState } from "react";
import Drawer from "@/shared/components/ui/Drawer";
import SupportForm from "./SupportForm";
import { SUPPORT_FAQ, TROUBLESHOOTING_GUIDE, MIGRATION_ERROR_HELP } from "../content/faq";
import "./SupportPanel.css";

interface SupportPanelProps {
  open: boolean;
  onClose: () => void;
  onNavigateToDocs: () => void;
}

type SupportTab = "contact" | "report" | "faq" | "troubleshooting" | "errors";

const TABS: { id: SupportTab; label: string }[] = [
  { id: "contact", label: "Contact Support" },
  { id: "report", label: "Report an Issue" },
  { id: "faq", label: "FAQs" },
  { id: "troubleshooting", label: "Troubleshooting" },
  { id: "errors", label: "Migration Error Help" },
];

const renderEntries = (entries: { question: string; answer: string }[]) => (
  <>
    {entries.map((entry) => (
      <div key={entry.question} className="support-faq-entry">
        <p className="support-faq-question">{entry.question}</p>
        <p className="support-muted">{entry.answer}</p>
      </div>
    ))}
  </>
);

const SupportPanel: React.FC<SupportPanelProps> = ({ open, onClose, onNavigateToDocs }) => {
  const [tab, setTab] = useState<SupportTab>("contact");

  return (
    <Drawer open={open} title="Support" onClose={onClose} widthPx={560}>
      <div className="support-tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`support-tab ${tab === item.id ? "is-active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "contact" && <SupportForm />}
      {tab === "report" && (
        <SupportForm fixedCategory="bug" fixedCategoryLabel="Bug report" />
      )}
      {tab === "faq" && <div className="support-section">{renderEntries(SUPPORT_FAQ)}</div>}
      {tab === "troubleshooting" && (
        <div className="support-section">{renderEntries(TROUBLESHOOTING_GUIDE)}</div>
      )}
      {tab === "errors" && (
        <div className="support-section">
          {renderEntries(MIGRATION_ERROR_HELP)}
          <SupportForm fixedCategory="migration_error" fixedCategoryLabel="Migration error" />
        </div>
      )}

      <div className="support-section">
        <button type="button" className="support-link-button" onClick={onNavigateToDocs}>
          View Documentation →
        </button>
      </div>
    </Drawer>
  );
};

export default SupportPanel;
