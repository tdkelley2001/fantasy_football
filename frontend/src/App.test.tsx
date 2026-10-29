import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { App } from "./App";
import { activeRun, health, snapshot } from "./test/fixtures";

function response(body: unknown, status=200) { return Promise.resolve(new Response(JSON.stringify(body), { status, headers:{"Content-Type":"application/json"} })); }
function mockApi(options: { snapshots?: unknown; detail?: unknown; runs?: unknown } = {}) {
  vi.spyOn(globalThis,"fetch").mockImplementation((input) => {
    const url=String(input);
    if(url.includes("/health")) return response(health);
    if(url.includes(`/snapshots/${snapshot.snapshot_id}`)) return response(options.detail ?? snapshot);
    if(url.endsWith("/snapshots")) return response(options.snapshots ?? [snapshot]);
    if(url.includes("/runs")) return response(options.runs ?? [activeRun]);
    throw new Error(`Unexpected URL ${url}`);
  });
}
afterEach(()=>vi.restoreAllMocks());

test("loads source-backed league data and active run status", async()=>{ mockApi(); render(<App/>); expect(await screen.findByRole("heading",{name:"Sanitized Gridiron League"})).toBeInTheDocument(); expect(screen.getAllByText("North Harbor").length).toBeGreaterThan(0); expect(screen.getByText("1 active")).toBeInTheDocument(); });
test("selects and persists another snapshot detail", async()=>{ const user=userEvent.setup(); const second={...snapshot,snapshot_id:"snapshot-beta",league_name:"Second Sanitized League",teams:[]}; vi.spyOn(globalThis,"fetch").mockImplementation((input)=>{ const url=String(input); if(url.includes("/health"))return response(health); if(url.endsWith("/snapshots"))return response([snapshot,second]); if(url.includes("snapshot-beta"))return response(second); if(url.includes("snapshot-alpha"))return response(snapshot); if(url.includes("/runs"))return response([]); throw new Error(url); }); render(<App/>); await screen.findAllByText("North Harbor"); await user.selectOptions(screen.getByRole("combobox",{name:"Active snapshot"}),"snapshot-beta"); expect(await screen.findByRole("heading",{name:"Second Sanitized League"})).toBeInTheDocument(); expect(localStorage.getItem("war-room-snapshot")).toBe("snapshot-beta"); });
test("navigates by keyboard to an honestly labeled future workspace", async()=>{ mockApi(); const user=userEvent.setup(); render(<App/>); await screen.findAllByText("North Harbor"); const trade=screen.getAllByRole("button",{name:"Trade Lab"})[0]; trade.focus(); await user.keyboard("{Enter}"); expect(screen.getByRole("heading",{name:"Trade Lab",level:1})).toBeInTheDocument(); expect(screen.getByText(/intentionally non-operational/)).toBeInTheDocument(); });
test("persists theme preference",async()=>{ mockApi(); const user=userEvent.setup(); render(<App/>); await screen.findAllByText("North Harbor"); await user.click(screen.getByRole("button",{name:"Use light theme"})); expect(document.documentElement).toHaveAttribute("data-theme","light"); expect(localStorage.getItem("war-room-theme")).toBe("light"); });
test("renders empty snapshot state",async()=>{ mockApi({snapshots:[]}); render(<App/>); expect(await screen.findByRole("heading",{name:"No canonical snapshots yet"})).toBeInTheDocument(); });
test("renders a disconnected state and retries",async()=>{ vi.spyOn(globalThis,"fetch").mockRejectedValue(new TypeError("offline")); render(<App/>); expect(await screen.findByRole("heading",{name:"Reconnect the decision engine"})).toBeInTheDocument(); expect(screen.getByRole("button",{name:/try again/i})).toBeInTheDocument(); });
test("renders typed API errors without fabricated data",async()=>{ vi.spyOn(globalThis,"fetch").mockImplementation((input)=>String(input).includes("health") ? response(health) : response({api_schema_version:"1.0",error:{code:"snapshot_store_error",message:"Snapshot store unavailable.",category:"storage",context:{}}},503)); render(<App/>); expect(await screen.findByText("Snapshot store unavailable.")).toBeInTheDocument(); expect(screen.queryByText("North Harbor")).not.toBeInTheDocument(); });
test("falls back from a deleted persisted snapshot",async()=>{ localStorage.setItem("war-room-snapshot","deleted"); mockApi(); render(<App/>); await screen.findAllByText("North Harbor"); expect(localStorage.getItem("war-room-snapshot")).toBe(snapshot.snapshot_id); });
test("core shell has no detectable accessibility violations",async()=>{ mockApi(); const {container}=render(<App/>); await screen.findAllByText("North Harbor"); const result=await axe.run(container); expect(result.violations).toEqual([]); });
test("mobile navigation remains semantically available",async()=>{ mockApi(); render(<App/>); await screen.findAllByText("North Harbor"); expect(screen.getByRole("navigation",{name:"Mobile primary navigation"})).toBeInTheDocument(); });
test.each([
  ["A · Tactical map","Tactical League Map"],
  ["B · Competitive landscape","Competitive Landscape"],
  ["C · Strategy table","Digital Strategy Table"],
])("opens the %s prototype without losing source-backed data",async(tab,title)=>{ mockApi(); const user=userEvent.setup(); render(<App/>); await screen.findAllByText("North Harbor"); await user.click(screen.getByRole("tab",{name:new RegExp(tab)})); expect(screen.getByRole("heading",{name:title})).toBeInTheDocument(); expect(screen.getAllByText(/North Harbor|NH/).length).toBeGreaterThan(0); });
test("team selection updates contextual prototype intelligence",async()=>{ mockApi(); const user=userEvent.setup(); render(<App/>); await screen.findAllByText("North Harbor"); await user.click(screen.getByRole("tab",{name:/Tactical map/})); await user.click(screen.getByRole("button",{name:/2SU5–2/})); expect(screen.getByRole("heading",{name:"Sunday Union"})).toBeInTheDocument(); });
