export function isPrivateRepoAccessError(message: string): boolean {
  const normalizedMessage = message.toLowerCase();
  return (
    normalizedMessage.includes("private repository") ||
    normalizedMessage.includes("repository not found or is private") ||
    normalizedMessage.includes("provide a personal access token") ||
    normalizedMessage.includes("access denied") ||
    normalizedMessage.includes("repo scope") ||
    normalizedMessage.includes("does not have access")
  );
}
