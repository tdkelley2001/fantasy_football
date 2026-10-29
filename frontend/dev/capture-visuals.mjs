import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const executablePath="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const output=resolve("../docs/images/m7-1");
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
await capture("analytics-desktop-dark-1440x1000",{width:1440,height:1000});
await capture("analytics-laptop-dark-1280x800",{width:1280,height:800});
await capture("analytics-mobile-dark-390x844",{width:390,height:844});
await capture("analytics-desktop-light-1440x1000",{width:1440,height:1000},async(page)=>page.addInitScript(()=>localStorage.setItem("war-room-theme","light")));
await capture("analytics-team-selected-1440x1000",{width:1440,height:1000},async()=>{},async(page)=>page.getByRole("button",{name:/Sunday Union, .* observed points for/}).click());
await capture("analytics-empty-1280x800",{width:1280,height:800},async(page)=>page.route("**/api/v1/snapshots",route=>route.fulfill({json:[]})));
await capture("analytics-disconnected-1280x800",{width:1280,height:800},async(page)=>page.route("**/api/**",route=>route.abort()));
await browser.close();
