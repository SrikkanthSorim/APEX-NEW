const configuredApiUrl = import.meta.env?.VITE_API_URL?.trim();
// Default to the page's OWN origin so API calls stay same-origin and go through
// the Vite dev proxy (`/api` -> backend, see vite.config.ts). This keeps the
// HttpOnly auth cookie first-party regardless of which host the app is opened on
// (localhost / 127.0.0.1 / LAN IP via `server.host: true`); hardcoding
// http://localhost:8000 here made requests cross-site and silently dropped the
// SameSite=lax cookie, causing 401s after login. An explicit VITE_API_URL still
// wins for deployments where the API lives on a different origin.
const runtimeOrigin =
  typeof window !== "undefined" && window.location?.origin
    ? window.location.origin
    : "http://localhost:8000";

export const APP_BASE_URL = (configuredApiUrl || runtimeOrigin).replace(/\/+$/, "");
export const API_BASE_URL = `${APP_BASE_URL}/api`;
export const GITHUB_AUTH_LOGIN_URL = `${API_BASE_URL}/auth/github/login`;
export const GOOGLE_AUTH_LOGIN_URL = `${API_BASE_URL}/auth/google/login`;
