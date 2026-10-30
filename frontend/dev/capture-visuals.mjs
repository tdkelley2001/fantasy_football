import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const executablePath="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const output=resolve("../docs/images/m7-2");
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath,headless:true});
async function capture(name,viewport,setup=async()=>{},after=async()=>{}) {
  const context=await browser.newContext({viewport,colorScheme:"dark"});
  const page=await context.newPage();
  await setup(page);
  await page.goto("http://127.0.0.1:5173",{waitUntil:"networkidle"});
  await after(page);
  await page.screenshot({path:resolve(output,`${name}.png`),fullPage:true});
  await context.close();
}
await capture("league-analytics-desktop-dark-1440x1100",{width:1440,height:1100});
await capture("league-analytics-laptop-dark-1280x800",{width:1280,height:800});
await capture("league-analytics-mobile-dark-390x844",{width:390,height:844});
await capture("league-analytics-desktop-light-1440x1100",{width:1440,height:1100},async(page)=>page.addInitScript(()=>localStorage.setItem("war-room-theme","light")));
await capture("league-analytics-team-selected-1440x1100",{width:1440,height:1100},async()=>{},async(page)=>page.getByRole("button",{name:/Sunday Union/}).first().click());
await capture("league-analytics-no-result-1280x800",{width:1280,height:800},async(page)=>page.route("**/api/v1/runs?*",route=>route.fulfill({json:[]})));
await capture("league-analytics-precision-limited-dark-1440x1100",{width:1440,height:1100},async(page)=>page.route("**/api/v1/runs/*/result",async route=>{const response=await route.fetch(),payload=await response.json();payload.result.league_wide_precision_reached=false;payload.result.stopping_reason="maximum_paths_reached";payload.result.teams[0].playoff_qualification.precision_reached=false;await route.fulfill({response,json:payload});}));
await capture("league-analytics-interval-unavailable-light-390x844",{width:390,height:844},async(page)=>{await page.addInitScript(()=>localStorage.setItem("war-room-theme","light"));await page.route("**/api/v1/runs/*/result",async route=>{const response=await route.fetch(),payload=await response.json();payload.result.teams[0].playoff_qualification.interval=null;await route.fulfill({response,json:payload});});});
await browser.close();
