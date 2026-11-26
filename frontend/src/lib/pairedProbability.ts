/** The paired API fields retain probability fractions despite their legacy names. */
export function formatPairedProbabilityPoints(fraction: number): string {
  const points = fraction * 100;
  const magnitude = Math.abs(points).toFixed(2);
  if (magnitude === "0.00") return magnitude;
  return `${points < 0 ? "-" : "+"}${magnitude}`;
}
