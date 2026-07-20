import React, { useMemo, useState } from "react";
import { AuthContext, type AuthContextValue, type AuthUser } from "./AuthContext";

/**
 * Frontend-only placeholder for auth state. No real authentication is wired
 * up yet — `login`/`logout` exist so the header can render a logged-in state
 * once real API integration replaces this.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: user !== null,
      user,
      login: (nextUser: AuthUser) => setUser(nextUser),
      logout: () => setUser(null),
    }),
    [user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
