import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/shared/components/ui";
import { ApiError } from "@/services/http/client";
import { useAuth } from "@/shared/context/AuthContext";
import AuthLayout from "../components/AuthLayout";
import SocialAuthButtons from "../components/SocialAuthButtons";
import PasswordInput from "../components/PasswordInput";
import { signIn } from "../services/authService";
import { useAuthForm, type FormErrors } from "../hooks/useAuthForm";
import "../auth.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface SignInValues {
  email: string;
  password: string;
}

function validateSignIn(values: SignInValues): FormErrors<SignInValues> {
  const errors: FormErrors<SignInValues> = {};

  if (!values.email.trim()) {
    errors.email = "Email is required.";
  } else if (!EMAIL_PATTERN.test(values.email.trim())) {
    errors.email = "Enter a valid email address.";
  }

  if (!values.password) {
    errors.password = "Password is required.";
  }

  return errors;
}

const SignInPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const { values, errors, setField, handleSubmit } = useAuthForm<SignInValues>({
    initialValues: { email: "", password: "" },
    validate: validateSignIn,
    onValid: async (formValues) => {
      if (isSubmitting) return; // guards a double-click landing two requests

      setApiError(null);
      setIsSubmitting(true);
      try {
        const response = await signIn({
          email: formValues.email.trim(),
          password: formValues.password,
        });
        login({ name: response.user.fullName, email: response.user.email });
        navigate("/connect");
      } catch (err) {
        if (err instanceof ApiError) {
          // The backend's own message is already safe to show verbatim for
          // both cases: "Invalid email or password." (401 — same wording
          // whether the email is unknown or the password is wrong, so this
          // never reveals which one happened) and the 403 disabled-account
          // message.
          setApiError(err.message || "Sign in failed. Please try again.");
        } else {
          setApiError("Unable to reach the server. Check your connection and try again.");
        }
      } finally {
        setIsSubmitting(false);
      }
    },
  });

  return (
    <AuthLayout title="Welcome Back!" subtitle="Sign in to continue your migration">
      {apiError && <div className="auth-notice auth-notice--error">{apiError}</div>}

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
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
          placeholder="Enter your password"
          error={errors.password}
          autoComplete="current-password"
          disabled={isSubmitting}
        />

        <div className="auth-row-between">
          <span />
          <button
            type="button"
            className="auth-link auth-link--muted"
            title="Password reset is coming soon"
            disabled
          >
            Forgot password?
          </button>
        </div>

        <Button type="submit" variant="primary" fullWidth loading={isSubmitting}>
          Sign In
        </Button>
      </form>

      <div className="auth-divider">or continue with</div>
      <SocialAuthButtons mode="signin" />

      <p className="auth-footer-note">
        Don&apos;t have an account? <Link to="/signup">Sign up</Link>
      </p>
    </AuthLayout>
  );
};

export default SignInPage;
