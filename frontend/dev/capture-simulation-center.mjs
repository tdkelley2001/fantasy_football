import {chromium} from "playwright-core";
import {mkdir} from "node:fs/promises";
import {resolve} from "node:path";
const output=resolve("../docs/images/m7-5");await mkdir(output,{recursive:true});const browser=await chromium.launch({executablePath:"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",headless:true});
async function shot(name,viewport,{light=false,action=async()=>{}}={}){const context=await browser.newContext({viewport,colorScheme:light?"light":"dark"});const page=await context.newPage();if(light)await page.addInitScript(()=>localStorage.setItem("war-room-theme","light"));await page.goto("http://127.0.0.1:5173",{waitUntil:"networkidle"});if(viewport.width<760)await page.getByRole("button",{name:"Open navigation"}).click();await page.getByRole("button",{name:"Simulation Center"}).last().click();await page.getByRole("heading",{name:"Simulation Center"}).waitFor();await action(page);await page.evaluate(()=>{window.scrollTo(0,0);(document.activeElement instanceof HTMLElement)&&document.activeElement.blur()});await page.screenshot({path:resolve(output,`${name}.png`),fullPage:true});await context.close()}
await shot("simulation-center-default-dark-1440x1200",{width:1440,height:1200});
await shot("simulation-center-action-config-dark-1440x1500",{width:1440,height:1100},{action:async page=>{await page.getByRole("button",{name:"Action search",exact:true}).click();await page.getByText("Orderings, counterparties, and player restrictions").click()}});
await shot("simulation-center-completed-dark-1440x1300",{width:1440,height:1000},{action:async page=>{await page.getByText("Baseline season simulation").click()}});
await shot("simulation-center-light-1440x1200",{width:1440,height:1200},{light:true});
await shot("simulation-center-mobile-390x844",{width:390,height:844});
await browser.close();
