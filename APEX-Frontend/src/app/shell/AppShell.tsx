import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import apexLogo from "../../assets/logo.jpg";
import { DocsPanel } from "@/features/docs";
import { SupportPanel } from "@/features/support";
import { Button } from "@/shared/components/ui";
import { useAuth } from "@/shared/context/AuthContext";
import "./AppShell.css";

const shellStyles: { [key: string]: React.CSSProperties } = {
  root: {
    minHeight: "100vh",
    width: "100%",
    margin: 0,
    padding: 0,
    background: "linear-gradient(180deg, #f8fbff 0%, #f8fafc 220px, #f8fafc 100%)",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    background: "rgba(255, 255, 255, 0.92)",
    borderBottom: "1px solid #e2e8f0",
    padding: "14px 28px",
    width: "100%",
    boxSizing: "border-box",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    rowGap: 10,
    position: "sticky",
    top: 0,
    zIndex: 20,
    backdropFilter: "blur(12px)",
    boxShadow: "0 10px 30px rgba(15, 23, 42, 0.04)",
  },
  main: {
    flex: 1,
    width: "100%",
    padding: 0,
    margin: 0,
  },
  content: {
    width: "100%",
    margin: 0,
    padding: 0,
  },
  footer: {
    background: "linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.96) 100%)",
    borderTop: "1px solid #e2e8f0",
    padding: "18px 28px",
    fontSize: 13,
    width: "100%",
    boxSizing: "border-box",
  },
  footerContent: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    color: "#64748b",
    gap: 16,
    flexWrap: "wrap",
  },
};

const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [activePanel, setActivePanel] = useState<"docs" | "support" | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { isAuthenticated, user, logout } = useAuth();

  const isLandingPage = location.pathname === "/";

  return (
    <div style={shellStyles.root}>
      <header style={shellStyles.header}>
        <div className="app-shell-brand">
          <img
            src={apexLogo}
            alt="Apex Logo"
            className="app-shell-logo"
            style={{ cursor: "pointer" }}
            onClick={() => navigate("/")}
          />
        </div>
        <nav className="app-shell-nav">
          {/* {isLandingPage && (
            <>
              <a href="#features" className="ui-nav-link">
                Features
              </a>
              <a href="#how-it-works" className="ui-nav-link">
                How It Works
              </a>
            </>
          )} */}
          <button
            type="button"
            className="ui-nav-button"
            onClick={() => setActivePanel("docs")}
            aria-haspopup="dialog"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            Docs
          </button>
          <button
            type="button"
            className="ui-nav-button"
            onClick={() => setActivePanel("support")}
            aria-haspopup="dialog"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ opacity: 0.6 }}>
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
            Support
          </button>
          <div className="app-shell-nav-divider" />

          {isAuthenticated ? (
            <div style={{ position: "relative" }}>
              <button
                onClick={() => setShowProfileMenu(!showProfileMenu)}
                className={`ui-profile-trigger ${showProfileMenu ? "is-open" : ""}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  border: "1px solid #e2e8f0",
                  fontWeight: 700,
                  color: "#2563eb",
                  background: "#eff6ff",
                }}
                title={user?.name ?? "Profile"}
                aria-expanded={showProfileMenu}
              >
                {(user?.name?.trim()?.charAt(0) || "?").toUpperCase()}
              </button>

              {showProfileMenu && (
                <>
                  <div
                    style={{ position: "fixed", inset: 0, zIndex: 999 }}
                    onClick={() => setShowProfileMenu(false)}
                  />
                  <div
                    style={{
                      position: "absolute",
                      top: 44,
                      right: 0,
                      width: 240,
                      background: "#fff",
                      borderRadius: 12,
                      boxShadow: "0 10px 40px rgba(0,0,0,0.15)",
                      border: "1px solid #e2e8f0",
                      zIndex: 1000,
                      overflow: "hidden",
                    }}
                  >
                    <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
                      <div style={{ fontSize: 15, fontWeight: 600, color: "#1e293b" }}>{user?.name}</div>
                      <div style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>{user?.email}</div>
                    </div>
                    <div style={{ padding: 12 }}>
                      <button
                        type="button"
                        className="ui-menu-button"
                        style={{
                          width: "100%",
                          display: "flex",
                          alignItems: "center",
                          gap: 12,
                          padding: "12px 16px",
                          borderRadius: 8,
                          border: "1px solid #e2e8f0",
                          background: "#fff",
                          color: "#1e293b",
                          fontSize: 14,
                          fontWeight: 500,
                        }}
                        onClick={() => {
                          setShowProfileMenu(false);
                          logout();
                          navigate("/");
                        }}
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                          <polyline points="16 17 21 12 16 7"></polyline>
                          <line x1="21" y1="12" x2="9" y2="12"></line>
                        </svg>
                        Logout
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : (
            <>
              {location.pathname !== "/signin" && (
                <Button variant="ghost" size="sm" onClick={() => navigate("/signin")}>
                  Sign In
                </Button>
              )}
              {location.pathname !== "/signup" && (
                <Button variant="primary" size="sm" onClick={() => navigate("/signup")}>
                  Sign Up
                </Button>
              )}
            </>
          )}
        </nav>
      </header>

      <main style={shellStyles.main}>
        <div style={shellStyles.content}>
          {children}
        </div>
      </main>

      <footer style={shellStyles.footer}>
        <div style={shellStyles.footerContent} className="app-shell-footer-content">
          <span className="app-shell-footer-meta" data-year={new Date().getFullYear()}>
            © {new Date().getFullYear()} Powered by <a href="https://sorim.ai/" target="_blank" rel="noreferrer">Sorim.ai</a>
          </span>
          <span>© {new Date().getFullYear()} <a href="https://sorim.ai/">Sorim.ai</a></span>
        </div>
      </footer>

      <DocsPanel
        open={activePanel === "docs"}
        onClose={() => setActivePanel(null)}
        onNavigateToSupport={() => setActivePanel("support")}
      />
      <SupportPanel
        open={activePanel === "support"}
        onClose={() => setActivePanel(null)}
        onNavigateToDocs={() => setActivePanel("docs")}
      />
    </div>
  );
};

export default AppShell;
