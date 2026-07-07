import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "@/app/shell/AppShell";
import AuthCallback from "@/features/auth/pages/AuthCallback";
import "./App.css";

const MigrationWizardPage = lazy(() => import("@/features/wizard/pages/MigrationWizardPage"));

export default function App() {
  return (
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
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/*" element={<MigrationWizardPage />} />
          </Routes>
        </Suspense>
      </AppShell>
    </BrowserRouter>
  );
}
