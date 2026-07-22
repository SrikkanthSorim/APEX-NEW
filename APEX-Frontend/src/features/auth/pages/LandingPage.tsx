import React from "react";
import { useNavigate } from "react-router-dom";
import { FaLink, FaSearch, FaBullseye, FaRocket, FaCheckCircle, FaCode, FaLayerGroup, FaTools, FaBoxes } from "react-icons/fa";
import { Button, Card, Container } from "@/shared/components/ui";
import SocialAuthButtons from "../components/SocialAuthButtons";
import apexLogo from "../../../assets/logo.jpg";
import "../auth.css";

const WORKFLOW_STEPS = [
  { icon: <FaLink />, label: "Connect", desc: "Connect your repository" },
  { icon: <FaSearch />, label: "Discovery", desc: "Analyze your codebase" },
  { icon: <FaBullseye />, label: "Strategy", desc: "Plan your migration" },
  { icon: <FaRocket />, label: "Migration", desc: "Migrate with automation" },
  { icon: <FaCheckCircle />, label: "Result", desc: "Get results & reports" },
];

const FEATURES = [
  { icon: <FaCode />, title: "Java Version Upgrade", desc: "Move confidently across Java releases with automated compatibility checks." },
  { icon: <FaLayerGroup />, title: "Framework Modernization", desc: "Modernize legacy frameworks to current, well-supported alternatives." },
  { icon: <FaTools />, title: "Build Tool Migration", desc: "Transition between Maven, Gradle, and other build tools seamlessly." },
  { icon: <FaBoxes />, title: "Dependency Updates", desc: "Detect outdated or vulnerable dependencies and update them safely." },
];

const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="auth-page">
      <Container size="xl" centered>
        <section className="landing-hero">
          <div className="landing-hero-grid">
            <div>
              <img src={apexLogo} alt="Java APEX" className="landing-hero-logo" />
              <span className="landing-eyebrow">Modernize. Migrate. Accelerate.</span>
              <h1 className="landing-title">
                Modernize Your <span className="landing-title-accent">Java Applications</span>
              </h1>
              <p className="landing-description">
                Java APEX helps you analyze, assess, and migrate your Java applications to modern
                architectures with confidence &mdash; from version upgrades to framework and build
                tool modernization.
              </p>

              <div className="landing-cta-row">
                <Button variant="primary" size="lg" onClick={() => navigate("/signup")}>
                  Sign Up
                </Button>
                <Button variant="secondary" size="lg" onClick={() => navigate("/signin")}>
                  Sign In
                </Button>
              </div>

              <div className="landing-divider-row">or continue with</div>
              <SocialAuthButtons mode="signup" />
            </div>

            <Card variant="elevated" noPadding className="landing-preview-card">
              <div className="landing-preview-topbar">
                <span className="landing-preview-dot" style={{ background: "#ef4444" }} />
                <span className="landing-preview-dot" style={{ background: "#f59e0b" }} />
                <span className="landing-preview-dot" style={{ background: "#22c55e" }} />
              </div>
              <pre className="landing-preview-code">
{`public class `}<span className="tok-cls">OrderService</span>{` {

  public `}<span className="tok-cls">Order</span>{` `}<span className="tok-fn">createOrder</span>{`(OrderRequest request) {
    if (request == null) {
      throw new IllegalArgumentException(
        "Request is required");
    }

    Order order = new Order();
    order.setId(UUID.randomUUID().toString());
    order.setStatus(OrderStatus.CREATED);

    return order;
  }
}`}
              </pre>
              <div className="landing-preview-footer">
                <h4>Built for Java. Designed for the future.</h4>
                <div className="landing-preview-check-list">
                  {FEATURES.map((feature) => (
                    <span className="landing-preview-check" key={feature.title}>
                      <FaCheckCircle size={13} />
                      {feature.title}
                    </span>
                  ))}
                </div>
              </div>
            </Card>
          </div>
        </section>

        <section className="landing-section" id="how-it-works">
          <h2 className="landing-section-title">How It Works</h2>
          <p className="landing-section-subtitle">A simple, guided workflow from repository to results.</p>
          <div className="landing-workflow-grid">
            {WORKFLOW_STEPS.map((step, index) => (
              <React.Fragment key={step.label}>
                <div className="landing-workflow-step">
                  <span className="landing-workflow-icon">{step.icon}</span>
                  <span className="landing-workflow-label">{step.label}</span>
                  <span className="landing-workflow-desc">{step.desc}</span>
                </div>
                {index < WORKFLOW_STEPS.length - 1 && <div className="landing-workflow-connector" />}
              </React.Fragment>
            ))}
          </div>
        </section>

        <section className="landing-section" id="features">
          <h2 className="landing-section-title">Features</h2>
          <p className="landing-section-subtitle">Everything you need to modernize your Java applications.</p>
          <div className="landing-feature-grid">
            {FEATURES.map((feature) => (
              <Card variant="outlined" key={feature.title}>
                <div className="landing-feature-card">
                  <span className="landing-feature-icon">{feature.icon}</span>
                  <div>
                    <h3 className="landing-feature-title">{feature.title}</h3>
                    <p className="landing-feature-desc">{feature.desc}</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      </Container>
    </div>
  );
};

export default LandingPage;
