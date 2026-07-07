/**
 * Page components barrel export
 *
 * Each page wraps a step (or group of steps) in the Migration Wizard.
 */
export { default as ConnectPage } from "@/features/connect/pages/ConnectPage";
export type { ConnectPageProps } from "@/features/connect/pages/ConnectPage";

export { default as DiscoveryPage } from "@/features/discovery/pages/DiscoveryPage";
export type { DiscoveryPageProps } from "@/features/discovery/pages/DiscoveryPage";

export { default as StrategyPage } from "@/features/strategy/pages/StrategyPage";
export type { StrategyPageProps } from "@/features/strategy/pages/StrategyPage";

export { default as ModernizationPage } from "@/features/modernization/pages/ModernizationPage";
export type { ModernizationPageProps } from "@/features/modernization/pages/ModernizationPage";

export { default as ResultPage } from "@/features/result/pages/ResultPage";
export type { ResultPageProps } from "@/features/result/pages/ResultPage";

export { default as LandingPage } from "./landing/LandingPage";
export { default as AuthCallback } from "@/features/auth/pages/AuthCallback";
