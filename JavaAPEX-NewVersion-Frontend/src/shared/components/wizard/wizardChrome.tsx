import { FaArrowLeft, FaArrowRight } from "react-icons/fa";
import { buildWizardAccentVars } from "./wizardUi";

export const renderWizardIconBadge = (
  icon: React.ReactNode,
  accent: string,
  size: "sm" | "md" | "lg" | "xl" = "lg"
) => (
  <span
    className={`wizard-icon-badge wizard-icon-badge-${size}`}
    style={buildWizardAccentVars(accent)}
  >
    {icon}
  </span>
);

export const renderBackButtonLabel = () => (
  <span className="wizard-button-content">
    <FaArrowLeft />
    <span>Back</span>
  </span>
);

export const renderForwardButtonLabel = (label: string) => (
  <span className="wizard-button-content">
    <span>{label}</span>
    <FaArrowRight />
  </span>
);

export const renderForwardLinkLabel = (label: string) => (
  <span className="wizard-link-content">
    <span>{label}</span>
    <FaArrowRight />
  </span>
);

export const renderStatusChip = (
  icon: React.ReactNode,
  accent: string,
  label: string,
  value: string,
  tone: "warning" | "success"
) => (
  <div className={`wizard-status-chip is-${tone}`}>
    <span className="wizard-status-chip-label">
      {renderWizardIconBadge(icon, accent, "sm")}
      <span>{label}</span>
    </span>
    <span className="wizard-status-chip-value">{value}</span>
  </div>
);
