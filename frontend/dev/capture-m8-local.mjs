import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const url = process.env.WAR_ROOM_CAPTURE_URL ?? "http://127.0.0.1:8081";
const output = resolve("../docs/images/m8-1");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: true,
});
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    colorScheme: "dark",
  });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  await page.getByText("Connected", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Simulation Center" }).last().click();
  await page.getByRole("heading", { name: "Simulation Center" }).waitFor();
  await page.screenshot({
    path: resolve(output, "production-local-sanitized-1440x1000.png"),
    fullPage: true,
  });
  await context.close();
} finally {
  await browser.close();
}
