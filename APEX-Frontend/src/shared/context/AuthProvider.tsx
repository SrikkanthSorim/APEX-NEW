import React, { useEffect, useMemo, useState } from "react";
import { getCurrentUser, logOut } from "@/features/auth/services/authService";
import { AuthContext, type AuthContextValue, type AuthUser } from "./AuthContext";

/**
 * Auth state backed by the real `/api/auth/*` endpoints. The actual session
 * lives in HttpOnly cookies the browser manages automatically — this only
 * mirrors "am I logged in, and as whom" into React state for the UI.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    // On first load, ask the backend whether the access_token cookie (if
    // any, e.g. from a previous visit) still identifies a valid session —
    // this is what keeps someone logged in across a page refresh.
    getCurrentUser()
      .then((me) => {
        if (!cancelled) setUser({ name: me.fullName, email: me.email });
      })
      .catch(() => {
        // No cookie, or an expired/invalid one — this is the normal state
        // for a first-time or already-logged-out visitor, not an error.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: user !== null,
      user,
      login: (nextUser: AuthUser) => setUser(nextUser),
      logout: () => {
        setUser(null);
        // Fire-and-forget: revokes the refresh token and clears both
        // HttpOnly cookies server-side. Local state is cleared immediately
        // above regardless of whether this call succeeds, so the UI never
        // waits on it and logout always "feels" instant.
        void logOut();
      },
    }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
