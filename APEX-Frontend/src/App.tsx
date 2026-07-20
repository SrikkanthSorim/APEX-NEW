import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "@/app/shell/AppShell";
import AuthCallback from "@/features/auth/pages/AuthCallback";
import { AuthProvider } from "@/shared/context/AuthProvider";
import "./App.css";

const MigrationWizardPage = lazy(() => import("@/features/wizard/pages/MigrationWizardPage"));
const LandingPage = lazy(() => import("@/features/auth/pages/LandingPage"));
const SignUpPage = lazy(() => import("@/features/auth/pages/SignUpPage"));
const SignInPage = lazy(() => import("@/features/auth/pages/SignInPage"));

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppShell>
          <Suspense
            fallback={
              <div
                style={{
                  minHeight: "60vh",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#475569",
                  fontSize: 16,
                  fontWeight: 600,
                }}
              >
                Loading migration workspace...
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/signup" element={<SignUpPage />} />
              <Route path="/signin" element={<SignInPage />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/*" element={<MigrationWizardPage />} />
            </Routes>
          </Suspense>
        </AppShell>
      </BrowserRouter>
    </AuthProvider>
  );
}
