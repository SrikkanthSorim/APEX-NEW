import React from "react";
import "./ConnectPage.css";

export interface ConnectPageProps {
  /** Step content rendered by the wizard orchestrator */
  children: React.ReactNode;
}

const ConnectPage: React.FC<ConnectPageProps> = ({ children }) => (
  <section className="page-connect" data-step="connect">
    {children}
  </section>
);

export default ConnectPage;
