import React from "react";
import { Link } from "react-router-dom";
import { Card } from "@/shared/components/ui";
import apexLogo from "../../../assets/logo.jpg";

export interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({ title, subtitle, children }) => {
  return (
    <div className="auth-page">
      <div className="auth-shell">
        <div className="auth-card">
          <Link to="/" className="auth-back-link">
            <img src={apexLogo} alt="Java APEX" />
            Java APEX
          </Link>
          <Card variant="elevated">
            <div className="auth-card-header">
              <h1 className="auth-card-title">{title}</h1>
              <p className="auth-card-subtitle">{subtitle}</p>
            </div>
            {children}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default AuthLayout;
