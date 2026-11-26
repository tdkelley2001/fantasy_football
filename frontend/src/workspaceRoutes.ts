const paths = {
  home: "/home",
  transactions: "/transactions",
  team: "/my-team/overview",
  opportunities: "/transactions/discover",
  priorAnalyses: "/transactions/prior-analyses",
  trades: "/transactions/evaluate",
  league: "/league/overview",
  playoffs: "/league/playoff-race",
  matchups: "/league/matchups",
  baselineEvidence: "/league/baseline-evidence",
  history: "/history/seasons",
  simulation: "/tools/simulation",
} as const;

export type Destination = keyof typeof paths;
export type WorkspaceRoute =
  | { destination: Exclude<Destination, "history" | "simulation"> }
  | { destination: "simulation"; actionSearch?: true }
  | { destination: "history"; year?: number };

export function readWorkspaceRoute(pathname: string): WorkspaceRoute {
  const path = pathname.replace(/\/$/, "");
  if (path === "/tools/simulation/action-search") return {destination:"simulation",actionSearch:true};
  if (path === "/players-moves/opportunities") return {destination:"opportunities"};
  if (path === "/players-moves/trade-lab") return {destination:"trades"};
  const archive = /^\/history\/seasons\/(\d{4})$/.exec(path);
  if (archive && Number(archive[1]) >= 2000) {
    return { destination: "history", year: Number(archive[1]) };
  }
  const destination = (Object.keys(paths) as Destination[]).find(key => paths[key] === path);
  return { destination: destination ?? "home" };
}

export function workspacePath(route: WorkspaceRoute): string {
  if (route.destination === "simulation" && route.actionSearch) return "/tools/simulation/action-search";
  return route.destination === "history" && route.year !== undefined
    ? `${paths.history}/${route.year}` : paths[route.destination];
}
