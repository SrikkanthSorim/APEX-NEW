import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { exchangeGithubAuthCode } from "@/features/auth/services/authService";

const AuthCallback: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get("code");
    if (code) {
      exchangeGithubAuthCode(code)
        .then((data) => {
          if (data.access_token) {
            localStorage.setItem("github_token", data.access_token);
            localStorage.setItem("github_user", JSON.stringify(data.user));
            navigate("/connect");
          } else {
            alert("GitHub login failed: " + (data.error || "Unknown error"));
            navigate("/connect");
          }
        })
        .catch(() => {
          alert("GitHub login failed: Network error");
          navigate("/connect");
        });
    } else {
      alert("No code found in URL");
      navigate("/connect");
    }
  }, [navigate]);

  return <div>Logging in with GitHub...</div>;
};

export default AuthCallback;
