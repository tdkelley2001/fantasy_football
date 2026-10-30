import { chromium } from "playwright-core";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const executablePath="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const output=resolve("../docs/images/m7-3");
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath,headless:true});

async function capture(name,viewport,{light=false,expectImpact=true,setup=async()=>{},after=async()=>{}}={}) {
  const context=await browser.newContext({viewport,colorScheme:light?"light":"dark"});
  const page=await context.newPage();
  if(light) await page.addInitScript(()=>localStorage.setItem("war-room-theme","light"));
  await setup(page);
  await page.goto("http://127.0.0.1:5173",{waitUntil:"networkidle"});
  if(viewport.width<760) await page.getByRole("button",{name:"Open navigation"}).click();
  await page.getByRole("button",{name:"Opportunity Explorer"}).click();
  if(expectImpact) await page.getByRole("button",{name:/Trade Then Acquisition, \+4\.25/}).waitFor();
  else await page.getByRole("heading",{name:"No retained opportunity search"}).waitFor();
  await after(page);
  await page.screenshot({path:resolve(output,`${name}.png`),fullPage:true});
  await context.close();
}

await capture("opportunity-default-dark-1440x1100",{width:1440,height:1100});
await capture("opportunity-selected-detail-dark-1440x1100",{width:1440,height:1100});
await capture("opportunity-league-impact-dark-1280x900",{width:1280,height:900});
await capture("opportunity-comparison-dark-1440x1100",{width:1440,height:1100},{after:async page=>{const buttons=page.getByRole("button",{name:"Add to comparison"});await buttons.nth(0).click();await buttons.nth(3).click();}});
await capture("opportunity-light-1440x1100",{width:1440,height:1100},{light:true});
await capture("opportunity-laptop-1280x800",{width:1280,height:800});
await capture("opportunity-mobile-390x844",{width:390,height:844});
await capture("opportunity-empty-1280x800",{width:1280,height:800},{expectImpact:false,setup:async page=>page.route("**/api/v1/runs?*",async route=>{const response=await route.fetch(),payload=await response.json();await route.fulfill({response,json:payload.filter(run=>run.run_type!=="action_search")});})});
await browser.close();
