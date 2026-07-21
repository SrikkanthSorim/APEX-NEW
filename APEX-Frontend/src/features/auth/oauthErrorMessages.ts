/**
 * Maps the backend's `?oauth_error=<code>` redirect codes (see
 * app/api/v1/endpoints/auth_controller.py) to safe, user-facing text.
 * Never derived from the raw backend error — only these fixed strings.
 */
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: "Sign-in was cancelled.",
  invalid_state: "Your sign-in session expired. Please try again.",
  provider_error: "We couldn't complete sign-in right now. Please try again.",
  provider_not_configured: "This sign-in method isn't available right now.",
  missing_email:
    "We couldn't get a verified email from your account. Please use a different sign-in method.",
  account_conflict:
    "An account with this email already exists. Please sign in with your password instead.",
  account_disabled: "This account has been disabled. Please contact support.",
  server_error: "Something went wrong completing sign-in. Please try again.",
};

export function getOAuthErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return OAUTH_ERROR_MESSAGES[code] ?? OAUTH_ERROR_MESSAGES.server_error;
}
