import React, { useState } from "react";
import { Link } from "react-router-dom";
import { FaInfoCircle } from "react-icons/fa";
import { Button } from "@/shared/components/ui";
import AuthLayout from "../components/AuthLayout";
import SocialAuthButtons from "../components/SocialAuthButtons";
import PasswordInput from "../components/PasswordInput";
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
  const [showNotice, setShowNotice] = useState(false);

  const { values, errors, setField, handleSubmit } = useAuthForm<SignInValues>({
    initialValues: { email: "", password: "" },
    validate: validateSignIn,
    onValid: () => {
      // TODO: replace with a real POST /auth/signin call once the backend endpoint
      // exists, then call AuthContext.login(user) on success.
      setShowNotice(true);
    },
  });

  return (
    <AuthLayout title="Welcome Back!" subtitle="Sign in to continue your migration">
      {showNotice && (
        <div className="auth-notice">
          <FaInfoCircle style={{ marginTop: 2, flexShrink: 0 }} />
          <span>Your details look good. Sign-in isn&apos;t connected to a backend yet — this form is ready for future API integration.</span>
        </div>
      )}

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

        <Button type="submit" variant="primary" fullWidth>
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
