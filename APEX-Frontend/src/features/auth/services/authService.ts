import { requestJson } from "@/services/http/client";

export interface GithubAuthCallbackResponse {
  access_token?: string;
  user?: {
    login?: string;
    [key: string]: unknown;
  };
  error?: string;
}

export async function exchangeGithubAuthCode(code: string): Promise<GithubAuthCallbackResponse> {
  return requestJson<GithubAuthCallbackResponse>(
    "/auth/github/callback",
    "GitHub login failed",
    {
      query: { code },
    }
  );
}

export interface SignUpRequest {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}

/** Mirrors the backend's UserResponse schema exactly (app/schemas/auth_schema.py). */
export interface AuthUser {
  id: number;
  fullName: string;
  email: string;
  role: string;
  isActive: boolean;
  isEmailVerified: boolean;
  createdAt: string;
  lastLoginAt: string | null;
}

export async function signUp(payload: SignUpRequest): Promise<AuthUser> {
  return requestJson<AuthUser>("/auth/signup", "Sign up failed. Please try again.", {
    method: "POST",
    body: payload,
    credentials: "include",
  });
}

export interface SignInRequest {
  email: string;
  password: string;
}

export interface SignInResponse {
  user: AuthUser;
  message: string;
}

export async function signIn(payload: SignInRequest): Promise<SignInResponse> {
  return requestJson<SignInResponse>("/auth/login", "Sign in failed. Please try again.", {
    method: "POST",
    body: payload,
    credentials: "include",
  });
}

/** Resolves the logged-in user from the access_token cookie, or rejects (401) if none. */
export async function getCurrentUser(): Promise<AuthUser> {
  return requestJson<AuthUser>("/auth/me", "Not authenticated", {
    method: "GET",
    credentials: "include",
  });
}

export async function logOut(): Promise<{ message: string }> {
  return requestJson<{ message: string }>("/auth/logout", "Logout failed", {
    method: "POST",
    credentials: "include",
  });
}
