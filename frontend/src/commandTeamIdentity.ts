// Canonical IDs choose the accent independently of league order and forecast mode.
const accents = [
  "#008a83", "#b76125", "#6276c9", "#a35498", "#617f3e", "#ba5260", "#3b7da7",
  "#907234", "#755eaa", "#238198", "#a46147", "#65788a", "#95751a", "#4c826b",
];

export function commandTeamColor(teamId: number) {
  return accents[((teamId % accents.length) + accents.length) % accents.length];
}
