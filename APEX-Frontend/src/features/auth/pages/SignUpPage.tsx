import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FaCheck } from "react-icons/fa";
import { Button } from "@/shared/components/ui";
import AuthLayout from "../components/AuthLayout";
import SocialAuthButtons from "../components/SocialAuthButtons";
import PasswordInput from "../components/PasswordInput";
import { useAuthForm, type FormErrors } from "../hooks/useAuthForm";
import "../auth.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MIN_PASSWORD_LENGTH = 8;

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

  if (!values.password) {
    errors.password = "Password is required.";
  } else if (values.password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
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
  const [submitted, setSubmitted] = useState(false);

  const { values, errors, setField, handleSubmit } = useAuthForm<SignUpValues>({
    initialValues: { fullName: "", email: "", password: "", confirmPassword: "" },
    validate: validateSignUp,
    onValid: () => {
      // TODO: replace with a real POST /auth/signup call once the backend endpoint exists.
      setSubmitted(true);
    },
  });

  if (submitted) {
    return (
      <AuthLayout title="Create Your Account" subtitle="Sign up to start your migration journey">
        <div className="auth-success">
          <div className="auth-success-icon">
            <FaCheck />
          </div>
          <h2 className="auth-success-title">Details look good!</h2>
          <p className="auth-success-text">
            Sign-up isn&apos;t connected to a backend yet, so no account was created. Once the API
            is available this form will submit your details and sign you up automatically.
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
        />

        <PasswordInput
          label="Confirm Password"
          name="confirmPassword"
          value={values.confirmPassword}
          onChange={(v) => setField("confirmPassword", v)}
          placeholder="Confirm your password"
          error={errors.confirmPassword}
        />

        <Button type="submit" variant="primary" fullWidth>
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
