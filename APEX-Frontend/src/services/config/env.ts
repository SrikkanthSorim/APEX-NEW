const configuredApiUrl = import.meta.env?.VITE_API_URL?.trim();
const isLocalFrontend =
  typeof window !== "undefined" &&
  ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
  window.location.port !== "8000";
const runtimeOrigin =
  isLocalFrontend
    ? "http://localhost:8000"
    : typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
    : "http://localhost:8000";

export const APP_BASE_URL = (configuredApiUrl || runtimeOrigin).replace(/\/+$/, "");
export const API_BASE_URL = `${APP_BASE_URL}/api`;
export const GITHUB_AUTH_LOGIN_URL = `${API_BASE_URL}/auth/github/login`;
