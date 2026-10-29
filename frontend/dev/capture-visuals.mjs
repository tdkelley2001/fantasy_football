import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const executablePath="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const output=resolve("../docs/images/m7-1");
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath,headless:true});
async function capture(name,viewport,setup=async()=>{},after=async()=>{}) { const context=await browser.newContext({viewport,colorScheme:"dark"}); const page=await context.newPage(); await setup(page); await page.goto("http://127.0.0.1:5173",{waitUntil:"networkidle"}); await after(page); await page.screenshot({path:resolve(output,`${name}.png`),fullPage:true}); await context.close(); }
await capture("desktop-dark-1440x1000",{width:1440,height:1000});
await capture("laptop-dark-1280x800",{width:1280,height:800});
await capture("mobile-dark-390x844",{width:390,height:844});
await capture("desktop-light-1440x1000",{width:1440,height:1000},async(page)=>page.addInitScript(()=>localStorage.setItem("war-room-theme","light")));
await capture("empty-1280x800",{width:1280,height:800},async(page)=>page.route("**/api/v1/snapshots",route=>route.fulfill({json:[]})));
await capture("disconnected-1280x800",{width:1280,height:800},async(page)=>page.route("**/api/**",route=>route.abort()));
for (const concept of ["tactical","landscape","table"]) {
  await capture(`review-${concept}-desktop-default-1440x1000`,{width:1440,height:1000},async()=>{},async(page)=>page.goto(`http://127.0.0.1:5173/?concept=${concept}`,{waitUntil:"networkidle"}));
  await capture(`review-${concept}-desktop-selected-1440x1000`,{width:1440,height:1000},async()=>{},async(page)=>{await page.goto(`http://127.0.0.1:5173/?concept=${concept}`,{waitUntil:"networkidle"}); const buttons=page.locator(".map-track button,.landscape-team,.field-matchup button"); if(await buttons.count()>1)await buttons.nth(1).click();});
  await capture(`review-${concept}-mobile-390x844`,{width:390,height:844},async()=>{},async(page)=>page.goto(`http://127.0.0.1:5173/?concept=${concept}`,{waitUntil:"networkidle"}));
}
await browser.close();
