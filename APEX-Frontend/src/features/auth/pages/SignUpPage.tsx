import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FaCheck } from "react-icons/fa";
import { Button } from "@/shared/components/ui";
import { ApiError } from "@/services/http/client";
import AuthLayout from "../components/AuthLayout";
import SocialAuthButtons from "../components/SocialAuthButtons";
import PasswordInput from "../components/PasswordInput";
import { signUp } from "../services/authService";
import { useAuthForm, type FormErrors } from "../hooks/useAuthForm";
import { getOAuthErrorMessage } from "../oauthErrorMessages";
import "../auth.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 128;
const HAS_UPPERCASE = /[A-Z]/;
const HAS_LOWERCASE = /[a-z]/;
const HAS_DIGIT = /\d/;
const HAS_SPECIAL_CHARACTER = /[^A-Za-z0-9]/;

interface SignUpValues {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}

function validateSignUp(values: SignUpValues): FormErrors<SignUpValues> {
  const errors: FormErrors<SignUpValues> = {};

  if (!values.fullName.trim()) {
    errors.fullName = "Full name is required.";
  }

  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!EMAIL_PATTERN.test(values.email.trim())) {
    errors.email = "Enter a valid email address.";
  }

  // Mirrors the backend's password policy exactly (app/schemas/auth_schema.py)
  // so a password the form calls "valid" is never rejected by the server.
  if (!values.password) {
    errors.password = "Password is required.";
  } else if (values.password.length < MIN_PASSWORD_LENGTH || values.password.length > MAX_PASSWORD_LENGTH) {
    errors.password = `Password must be between ${MIN_PASSWORD_LENGTH} and ${MAX_PASSWORD_LENGTH} characters.`;
  } else if (!HAS_UPPERCASE.test(values.password)) {
    errors.password = "Password must contain at least one uppercase letter.";
  } else if (!HAS_LOWERCASE.test(values.password)) {
    errors.password = "Password must contain at least one lowercase letter.";
  } else if (!HAS_DIGIT.test(values.password)) {
    errors.password = "Password must contain at least one number.";
  } else if (!HAS_SPECIAL_CHARACTER.test(values.password)) {
    errors.password = "Password must contain at least one special character.";
  }

  if (!values.confirmPassword) {
    errors.confirmPassword = "Please confirm your password.";
  } else if (values.confirmPassword !== values.password) {
    errors.confirmPassword = "Passwords do not match.";
  }

  return errors;
}

const SignUpPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // The backend redirects back here as `/signin?oauth_error=<code>` (see
  // app/api/v1/endpoints/auth_controller.py); a user can also land on Sign Up
  // with the same param if they started the OAuth flow from this page.
  useEffect(() => {
    const oauthErrorCode = searchParams.get("oauth_error");
    if (oauthErrorCode) {
      setApiError(getOAuthErrorMessage(oauthErrorCode));
      navigate("/signup", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const { values, errors, setField, handleSubmit } = useAuthForm<SignUpValues>({
    initialValues: { fullName: "", email: "", password: "", confirmPassword: "" },
    validate: validateSignUp,
    onValid: async (formValues) => {
      // Extra guard beyond the button's disabled state: React may not have
      // re-rendered yet between two rapid clicks, so this makes the second
      // call a no-op instead of firing a duplicate request.
      if (isSubmitting) return;

      setApiError(null);
      setIsSubmitting(true);
      try {
        await signUp({
          fullName: formValues.fullName.trim(),
          email: formValues.email.trim(),
          password: formValues.password,
          confirmPassword: formValues.confirmPassword,
        });
        setSubmitted(true);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            setApiError("An account with this email already exists. Try signing in instead.");
          } else {
            // Covers 422 (validation the server caught that we didn't) and
            // 500 (ApiError's message is the server's own safe error text).
            setApiError(err.message || "Sign up failed. Please try again.");
          }
        } else {
          // fetch() itself rejected: backend unreachable, DNS failure, or a
          // CORS-blocked request — the browser hides the exact reason from
          // JS in all three cases, so this is the most specific message we
          // can honestly show.
          setApiError("Unable to reach the server. Check your connection and try again.");
        }
      } finally {
        setIsSubmitting(false);
      }
    },
  });

  if (submitted) {
    return (
      <AuthLayout title="Create Your Account" subtitle="Sign up to start your migration journey">
        <div className="auth-success">
          <div className="auth-success-icon">
            <FaCheck />
          </div>
          <h2 className="auth-success-title">Account created!</h2>
          <p className="auth-success-text">
            Your account has been created successfully. Sign in to start your migration journey.
          </p>
          <Button variant="primary" fullWidth onClick={() => navigate("/signin")}>
            Go to Sign In
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create Your Account" subtitle="Sign up to start your migration journey">
      {apiError && <div className="auth-notice auth-notice--error">{apiError}</div>}

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        <div className="auth-field">
          <label className="auth-label" htmlFor="fullName">
            Full Name
          </label>
          <input
            id="fullName"
            name="fullName"
            type="text"
            className={`auth-input ${errors.fullName ? "auth-input--error" : ""}`}
            placeholder="Enter your full name"
            value={values.fullName}
            onChange={(e) => setField("fullName", e.target.value)}
            autoComplete="name"
            disabled={isSubmitting}
          />
          {errors.fullName && <span className="auth-error-text">{errors.fullName}</span>}
        </div>

        <div className="auth-field">
          <label className="auth-label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            className={`auth-input ${errors.email ? "auth-input--error" : ""}`}
            placeholder="Enter your email"
            value={values.email}
            onChange={(e) => setField("email", e.target.value)}
            autoComplete="email"
            disabled={isSubmitting}
          />
          {errors.email && <span className="auth-error-text">{errors.email}</span>}
        </div>

        <PasswordInput
          label="Password"
          name="password"
          value={values.password}
          onChange={(v) => setField("password", v)}
          placeholder="Create a strong password"
          error={errors.password}
          disabled={isSubmitting}
        />

        <PasswordInput
          label="Confirm Password"
          name="confirmPassword"
          value={values.confirmPassword}
          onChange={(v) => setField("confirmPassword", v)}
          placeholder="Confirm your password"
          error={errors.confirmPassword}
          disabled={isSubmitting}
        />

        <Button type="submit" variant="primary" fullWidth loading={isSubmitting}>
          Sign Up
        </Button>
      </form>

      <div className="auth-divider">or continue with</div>
      <SocialAuthButtons mode="signup" />

      <p className="auth-footer-note">
        Already have an account? <Link to="/signin">Sign in</Link>
      </p>
    </AuthLayout>
  );
};

export default SignUpPage;
