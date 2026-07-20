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
