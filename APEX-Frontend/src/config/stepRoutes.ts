export const STEP_ROUTES: Record<number, string> = {
  1: "/connect",
  2: "/discovery",
  3: "/strategy",
  4: "/migration",
  5: "/migrating",
  6: "/progress",
  7: "/report",
};

export const getStepFromPath = (pathname: string) => {
  const normalizedPath = pathname.replace(/\/+$/, "") || "/";
  const entry = Object.entries(STEP_ROUTES).find(([, route]) => route === normalizedPath);
  return entry ? Number(entry[0]) : 1;
};
