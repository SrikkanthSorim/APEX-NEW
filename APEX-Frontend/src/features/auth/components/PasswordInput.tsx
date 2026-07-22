import React, { useId, useState } from "react";
import { FaEye, FaEyeSlash } from "react-icons/fa";

export interface PasswordInputProps {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  error?: string;
  autoComplete?: string;
  disabled?: boolean;
}

const PasswordInput: React.FC<PasswordInputProps> = ({
  label,
  name,
  value,
  onChange,
  onBlur,
  placeholder,
  error,
  autoComplete = "new-password",
  disabled = false,
}) => {
  const [visible, setVisible] = useState(false);
  const inputId = useId();
  const errorId = `${inputId}-error`;

  return (
    <div className="auth-field">
      <label className="auth-label" htmlFor={inputId}>
        {label}
      </label>
      <div className="auth-input-wrap">
        <input
          id={inputId}
          name={name}
          type={visible ? "text" : "password"}
          className={`auth-input auth-input--with-toggle ${error ? "auth-input--error" : ""}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder}
          autoComplete={autoComplete}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
        />
        <button
          type="button"
          className="auth-toggle-visibility"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          tabIndex={-1}
          disabled={disabled}
        >
          {visible ? <FaEyeSlash size={15} /> : <FaEye size={15} />}
        </button>
      </div>
      {error && (
        <span id={errorId} className="auth-error-text">
          {error}
        </span>
      )}
    </div>
  );
};

export default PasswordInput;
