import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { LeagueOverview, PlayoffRace, type ForecastRequest } from "./LeagueOverview";
import type {ProjectedSeasonState} from "./useProjectedSeason";
import { api } from "./lib/api";
import { snapshot } from "./test/fixtures";
import type { BackgroundBaselineResultSummary, BackgroundRunRecord, ProbabilityValue } from "./types/api";

beforeEach(()=>{vi.spyOn(api,"recentLeagueResults").mockResolvedValue(null)});

const estimate=(probability:number|null):ProbabilityValue=>({successes:probability===null?0:Math.round(probability*1000),trials:1000,probability,precision_reached:probability!==null,interval:probability===null?null:{method:"wilson_bonferroni",interval_confidence_level:.95,simultaneous_family_confidence_level:.95,lower_probability:Math.max(0,probability-.03),upper_probability:Math.min(1,probability+.03),half_width_probability:.03}});
const run=(id:string,finished:string):BackgroundRunRecord=>({api_schema_version:"1.0",run_id:id,run_type:"baseline",status:"completed",request_sha256:"b".repeat(64),snapshot_id:snapshot.snapshot_id,build:{package_version:"0.9.0",build_revision:"test",revision_status:"explicit"},created_at_utc:finished,started_at_utc:finished,finished_at_utc:finished,expires_at_utc:"2027-01-01T00:00:00Z",stop_reason:"precision_reached",error_code:null,error_message:null,result_available:true});
const result=(record:BackgroundRunRecord,incomplete=false):BackgroundBaselineResultSummary=>({api_schema_version:"1.0",run:record,result:{api_schema_version:"1.0",provenance:{snapshot_id:snapshot.snapshot_id,canonical_sha256:snapshot.canonical_sha256,simulation_config_sha256:"c".repeat(64),engine_run_identity_sha256:"d".repeat(64),model_id:"provisional_empirical_residual",model_parameters:[],master_seed:8128,first_path_index:0,requested_path_count:1000,effective_request_sha256:"e".repeat(64),application_run:{identity_schema_version:"application-run-identity-v1",analytical_equivalence_sha256:"1".repeat(64),application_execution_sha256:"2".repeat(64),presentation_query_sha256:"3".repeat(64),execution_nonce:"test-execution",build:record.build}},precision_config_sha256:"f".repeat(64),stopping_reason:incomplete?"maximum_paths_reached":"precision_reached",league_wide_precision_reached:!incomplete,requested_paths:1000,completed_paths:incomplete?900:1000,incomplete_paths:incomplete?100:0,candidate_coverage_complete:null,teams:snapshot.teams.map((team,index)=>({team_id:team.team_id,championship:estimate(index===2?null:[.42,.29,.18,.11][index]),playoff_qualification:estimate([.9,.76,.47,.22][index]),final_placements:snapshot.teams.map((_,place)=>({placement:place+1,estimate:estimate(place===index?.4:.2)}))})),incomplete_capabilities:incomplete?[["postseason",17]]:[],limitations:["Historical projection provenance remains provisional."]}});

afterEach(()=>vi.restoreAllMocks());
test("selects the newest usable run and presents percentages, intervals, and exact placements",async()=>{const older=run("older","2026-10-20T12:00:00Z"),newer=run("newer","2026-10-21T12:00:00Z");vi.spyOn(globalThis,"fetch").mockImplementation(input=>Promise.resolve(new Response(JSON.stringify(result(String(input).includes("newer")?newer:older)),{headers:{"Content-Type":"application/json"}})));render(<PlayoffRace snapshot={snapshot} runs={[older,newer]}/>);expect(await screen.findByRole("heading",{name:"Championship probability"})).toBeInTheDocument();expect(screen.getByRole("combobox",{name:"Completed run"})).toHaveValue("newer");expect(screen.getAllByText("42%").length).toBeGreaterThan(0);expect(screen.getByText(/39%–45% simultaneous interval/)).toBeInTheDocument();expect(screen.getByText("Accessible exact placement table")).toBeInTheDocument();expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0)});
test("explicit run selection changes retained evidence without mixing runs",async()=>{const user=userEvent.setup(),older=run("older","2026-10-20T12:00:00Z"),newer=run("newer","2026-10-21T12:00:00Z");vi.spyOn(globalThis,"fetch").mockImplementation(input=>Promise.resolve(new Response(JSON.stringify(result(String(input).includes("newer")?newer:older)),{headers:{"Content-Type":"application/json"}})));render(<PlayoffRace snapshot={snapshot} runs={[older,newer]}/>);const select=await screen.findByRole("combobox",{name:"Completed run"});await user.selectOptions(select,"older");await waitFor(()=>expect(select).toHaveValue("older"));expect(screen.getByText("1,000 / 1,000")).toBeInTheDocument()});
test("reports incomplete coverage and rejects mismatched snapshot provenance",async()=>{const record=run("run-incomplete","2026-10-21T12:00:00Z");const bad={...result(record,true),result:{...result(record,true).result,provenance:{...result(record,true).result.provenance,canonical_sha256:"0".repeat(64)}}};vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(bad),{headers:{"Content-Type":"application/json"}}));render(<PlayoffRace snapshot={snapshot} runs={[record]}/>);expect(await screen.findByRole("heading",{name:"Result unavailable"})).toBeInTheDocument();expect(screen.getByText(/canonical identity does not match/)).toBeInTheDocument();expect(screen.queryByRole("heading",{name:"Championship probability"})).not.toBeInTheDocument()});
test("shows incomplete capability semantics when retained paths are partial",async()=>{const record=run("run-partial","2026-10-21T12:00:00Z");vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(result(record,true)),{headers:{"Content-Type":"application/json"}}));render(<PlayoffRace snapshot={snapshot} runs={[record]}/>);expect(await screen.findByText("Precision or coverage qualification")).toBeInTheDocument();expect(screen.getByText(/simulation paths were incomplete/)).toBeInTheDocument();expect(screen.getByText(/analytical capabilities were incomplete/)).toBeInTheDocument()});
test("reads only observed results when no completed baseline exists",async()=>{vi.mocked(api.recentLeagueResults).mockRestore();const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response("null"));render(<LeagueOverview snapshot={snapshot}/>);expect(screen.queryByRole("heading",{name:"Championship probability"})).not.toBeInTheDocument();await screen.findByText("No completed regular-season results are available for this snapshot.");expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0]).toMatch(/recent-results$/)});
test("renders a fourteen-team league from configuration without a size-specific branch",async()=>{const teams=Array.from({length:14},(_,index)=>({...snapshot.teams[index%snapshot.teams.length],team_id:index+1,display_name:`Configured Team ${index+1}`,standing:index+1,playoff_seed:index<6?index+1:null}));const large={...snapshot,snapshot_id:"snapshot-fourteen",canonical_sha256:"9".repeat(64),team_count:14,teams};const record={...run("run-fourteen","2026-10-22T12:00:00Z"),snapshot_id:large.snapshot_id};const payload={...result(record),result:{...result(record).result,provenance:{...result(record).result.provenance,snapshot_id:large.snapshot_id,canonical_sha256:large.canonical_sha256},teams:teams.map((team,index)=>({team_id:team.team_id,championship:estimate((14-index)/105),playoff_qualification:estimate((14-index)/14),final_placements:teams.map((_,place)=>({placement:place+1,estimate:estimate(place===index?.25:.75/13)}))}))}};vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(payload),{headers:{"Content-Type":"application/json"}}));render(<PlayoffRace snapshot={large} runs={[record]}/>);expect(await screen.findByRole("heading",{name:"Championship probability"})).toBeInTheDocument();expect(screen.getAllByText("Configured Team 14").length).toBeGreaterThan(0);expect(screen.getAllByText("14th")).toHaveLength(2)});

test("qualifies completed execution when league and metric precision are not reached",async()=>{const record=run("precision-limited","2026-10-23T12:00:00Z"),base=result(record),limited={...base,result:{...base.result,league_wide_precision_reached:false,stopping_reason:"maximum_paths_reached",teams:base.result.teams.map((team,index)=>index===0?{...team,playoff_qualification:{...team.playoff_qualification,precision_reached:false,interval:null}}:team)}};vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(limited),{headers:{"Content-Type":"application/json"}}));render(<PlayoffRace snapshot={snapshot} runs={[record]}/>);expect(await screen.findByText("Precision or coverage qualification")).toBeInTheDocument();expect(screen.getByText(/league-wide precision target was not reached/)).toBeInTheDocument();expect(screen.getAllByText("Interval unavailable").length).toBeGreaterThan(0);expect(screen.getAllByText(/Precision target not reached|Precision pending/).length).toBeGreaterThan(0);expect(screen.getByRole("button",{name:/North Harbor: playoff qualification 90%, interval unavailable, precision target not reached/})).toBeInTheDocument()});

test("snapshot change prevents a late result from appearing under another snapshot",async()=>{const first=run("slow-first","2026-10-23T12:00:00Z"),otherSnapshot={...snapshot,snapshot_id:"snapshot-other",canonical_sha256:"8".repeat(64),league_name:"Other League"},second={...run("fast-second","2026-10-24T12:00:00Z"),snapshot_id:otherSnapshot.snapshot_id};let resolveFirst:(response:Response)=>void=()=>{};const firstResponse=new Promise<Response>(resolve=>{resolveFirst=resolve});vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("slow-first")?firstResponse:Promise.resolve(new Response(JSON.stringify({...result(second),result:{...result(second).result,provenance:{...result(second).result.provenance,snapshot_id:otherSnapshot.snapshot_id,canonical_sha256:otherSnapshot.canonical_sha256}}}),{headers:{"Content-Type":"application/json"}})));const view=render(<PlayoffRace snapshot={snapshot} runs={[first]}/>);view.rerender(<PlayoffRace snapshot={otherSnapshot} runs={[second]}/>);expect(await screen.findByText("Other League / 2026")).toBeInTheDocument();expect(await screen.findByRole("heading",{name:"Championship probability"})).toBeInTheDocument();resolveFirst(new Response(JSON.stringify(result(first)),{headers:{"Content-Type":"application/json"}}));await waitFor(()=>expect(screen.getByText("Other League / 2026")).toBeInTheDocument());expect(screen.queryByText(/canonical identity does not match/)).not.toBeInTheDocument()});

test("rapid run selection ignores late resolution from cancelled requests",async()=>{const user=userEvent.setup(),oldest=run("oldest","2026-10-20T12:00:00Z"),middle=run("middle","2026-10-21T12:00:00Z"),newest=run("newest","2026-10-22T12:00:00Z");let resolveMiddle:(response:Response)=>void=()=>{};const middleResponse=new Promise<Response>(resolve=>{resolveMiddle=resolve});vi.spyOn(globalThis,"fetch").mockImplementation(input=>{const url=String(input);if(url.includes("middle"))return middleResponse;const record=url.includes("oldest")?oldest:newest;return Promise.resolve(new Response(JSON.stringify(result(record)),{headers:{"Content-Type":"application/json"}}))});render(<PlayoffRace snapshot={snapshot} runs={[oldest,middle,newest]}/>);const selector=await screen.findByRole("combobox",{name:"Completed run"});await user.selectOptions(selector,"middle");await user.selectOptions(selector,"oldest");await waitFor(()=>expect(selector).toHaveValue("oldest"));resolveMiddle(new Response(JSON.stringify(result(middle)),{headers:{"Content-Type":"application/json"}}));await waitFor(()=>expect(selector).toHaveValue("oldest"));expect(screen.queryByRole("heading",{name:"Result unavailable"})).not.toBeInTheDocument()});

test("precision and interval states have no detectable accessibility violations",async()=>{const record=run("accessible-limited","2026-10-25T12:00:00Z"),base=result(record),limited={...base,result:{...base.result,league_wide_precision_reached:false,teams:base.result.teams.map((team,index)=>index===0?{...team,playoff_qualification:{...team.playoff_qualification,interval:null,precision_reached:false}}:team)}};vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(limited),{headers:{"Content-Type":"application/json"}}));const {container}=render(<PlayoffRace snapshot={snapshot} runs={[record]}/>);await screen.findByText("Precision or coverage qualification");expect((await axe.run(container)).violations).toEqual([])});

test("renders the shared projected season and offers optional Monte Carlo", async () => {
  const user = userEvent.setup();
  const openSimulation = vi.fn();
  const fetch = vi.spyOn(globalThis, "fetch");
  render(<LeagueOverview snapshot={snapshot} openSimulation={openSimulation} projection={{
    state: {status: "available", result: {
      snapshot_id: snapshot.snapshot_id, canonical_sha256: snapshot.canonical_sha256,
      status: "complete", champion_team_id: snapshot.teams[0].team_id, teams: [], weeks: [], postseason: [],
      transactions: [], observed_scores: [], assumptions: [], unresolved_capabilities: [], missing_projection_count: 0,
    }}, retry: vi.fn(),
  }}/>);
  expect(screen.getByText(`Champion in this projected season: ${snapshot.teams[0].display_name}`)).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Open Monte Carlo"}));
  expect(openSimulation).toHaveBeenCalledOnce();
  expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/analyses/projected-baseline"))).toBe(false);
});

const projected: ProjectedSeasonState = {state:{status:"available",result:{
  snapshot_id:snapshot.snapshot_id,canonical_sha256:snapshot.canonical_sha256,status:"complete",
  champion_team_id:snapshot.teams[0].team_id,teams:snapshot.teams.map((team,index)=>({
    team_id:team.team_id,final_regular_rank:index+1,postseason_seed:index+1,final_placement:index+1,
    final_regular_standing:{wins:team.wins,losses:team.losses,ties:team.ties,points_for:team.points_for},
  })),weeks:[],postseason:[{
    matchup_id:"title",round_number:1,bracket_type:"championship",home_team_id:snapshot.teams[0].team_id,
    away_team_id:snapshot.teams[1].team_id,home_total:110,away_total:100,winner_team_id:snapshot.teams[0].team_id,
  }],transactions:[],observed_scores:[],assumptions:[],unresolved_capabilities:[],missing_projection_count:0,
}},retry:vi.fn()};

const forecastRequest: ForecastRequest = {
  canonical:snapshot.canonical_sha256,
  request:{
    api_schema_version:"1.0", snapshot:{snapshot_id:snapshot.snapshot_id,league_id:snapshot.league_id,season:snapshot.season},
    simulation:{master_seed:8128,path_count:1000,first_path_index:0,ir_policy:"projection_based",
      waiver_boundary:"modeled_weekly_v1",reject_incomplete_valuations:true,require_complete:true},
    precision:{family_confidence_level:.95,target_half_width_probability:.05,minimum_paths:1000,maximum_paths:1000,evaluation_interval_paths:100},
    outcome_model:{model_type:"provisional_normal",base_stddev_points:4,projection_scale:.2},
  },
};
function commandResult(record: BackgroundRunRecord) {
  const payload=result(record);
  return {...payload,result:{...payload.result,provenance:{...payload.result.provenance,
    model_id:"provisional-independent-normal-v1:missing-projection-zero-v1",
    model_parameters:[["base_stddev",4],["projection_scale",.2],["conditional_independence",true],
      ["missing_projection_outcome","deterministic-zero-v1"]],
  }}};
}

test("one League canvas promotes a completed baseline and retains focus across mode switches",async()=>{
  const user=userEvent.setup();
  const finished=run("finished","2026-10-24T12:00:00Z");
  const active={...finished,status:"running",result_available:false} as const;
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>Response.json(commandResult(finished)));
  const forecastRequests=new Map([[finished.run_id,forecastRequest]]);
  const view=render(<LeagueOverview snapshot={snapshot} projection={projected} runs={[active]} forecastRequests={forecastRequests}/>);
  const command=within(screen.getByRole("region",{name:"League Command Center"}));
  expect(command.getByRole("button",{name:"Projected season"})).toHaveAttribute("aria-pressed","true");
  expect(command.getByText(/baseline simulation is active/)).toBeInTheDocument();
  const race=within(command.getByRole("region",{name:"Playoff Race"}));
  const journey=within(command.getByRole("region",{name:"Season Journey"}));
  const postseason=within(command.getByRole("region",{name:"Postseason Outlook"}));
  expect(race.getAllByRole("button")).toHaveLength(snapshot.teams.length);
  await user.click(postseason.getByRole("button",{name:/North Harbor/}));
  expect(race.getByRole("button",{name:/North Harbor/})).toHaveAttribute("aria-pressed","true");
  expect(journey.getByText(/North Harbor.*Observed rank/)).toBeInTheDocument();
  expect(command.getByRole("complementary",{name:"Team Focus"})).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();

  view.rerender(<LeagueOverview snapshot={snapshot} projection={projected} runs={[finished]} forecastRequests={forecastRequests}/>);
  await waitFor(()=>expect(command.getByRole("button",{name:"Monte Carlo"})).toHaveAttribute("aria-pressed","true"));
  expect(race.getByRole("button",{name:/North Harbor/})).toHaveAttribute("aria-pressed","true");
  expect(postseason.getByRole("button",{name:/North Harbor: championship/})).toHaveAttribute("aria-pressed","true");
  await user.click(race.getByRole("button",{name:/North Harbor/}));
  expect(command.queryByRole("complementary",{name:"Team Focus"})).not.toBeInTheDocument();
  await user.click(postseason.getByRole("button",{name:/North Harbor: championship/}));
  await user.click(command.getByRole("button",{name:"Projected season"}));
  expect(race.getByRole("button",{name:/North Harbor/})).toHaveAttribute("aria-pressed","true");
  expect(postseason.getByRole("button",{name:/North Harbor.*Winner/})).toBeInTheDocument();
  await user.click(command.getByRole("button",{name:"Dismiss Team Focus"}));
  expect(command.queryByRole("complementary",{name:"Team Focus"})).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledOnce();
});

test("automatic promotion honors an explicit projected choice and rejects a changed request identity",async()=>{
  const user=userEvent.setup();
  const record=run("selected","2026-10-24T12:00:00Z");
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async()=>Response.json(commandResult(record)));
  const forecastRequests=new Map([[record.run_id,forecastRequest]]);
  const view=render(<LeagueOverview snapshot={snapshot} projection={projected} runs={[]} forecastRequests={forecastRequests}/>);
  const mode=screen.getByRole("button",{name:"Projected season"});
  await user.click(mode);
  view.rerender(<LeagueOverview snapshot={snapshot} projection={projected} runs={[record]} forecastRequests={forecastRequests}/>);
  await waitFor(()=>expect(fetch).toHaveBeenCalledOnce());
  expect(mode).toHaveAttribute("aria-pressed","true");
  await user.click(screen.getByRole("button",{name:"Monte Carlo"}));
  expect(await screen.findByRole("heading",{name:"Championship probability"})).toBeInTheDocument();
  view.rerender(<LeagueOverview snapshot={snapshot} projection={projected} runs={[{...record,request_sha256:"0".repeat(64)}]} forecastRequests={forecastRequests}/>);
  expect(screen.queryByRole("heading",{name:"Championship probability"})).not.toBeInTheDocument();
  expect(await screen.findByText(/Monte Carlo forecast unavailable.*identity does not match/)).toBeInTheDocument();
  expect(mode).toHaveAttribute("aria-pressed","false");
  expect(screen.getByRole("button",{name:"Monte Carlo"})).toHaveAttribute("aria-pressed","true");
  expect(screen.getByText("Showing the projected season.")).toBeInTheDocument();
});

test("an active or incompatible baseline cannot displace a compatible completed forecast", async()=>{
  const older=run("older","2026-10-20T12:00:00Z");
  const newer=run("newer","2026-10-21T12:00:00Z");
  const wrongPolicy=run("wrong-policy","2026-10-22T12:00:00Z");
  const wrongModel=run("wrong-model","2026-10-23T12:00:00Z");
  const unknown=run("unknown","2026-10-24T12:00:00Z");
  const forecastRequests=new Map([[older.run_id,forecastRequest],[newer.run_id,forecastRequest],
    [wrongModel.run_id,forecastRequest],[wrongPolicy.run_id,{...forecastRequest,request:{...forecastRequest.request,
      simulation:{...forecastRequest.request.simulation,ir_policy:"strict" as const}}}]]);
  const fetch=vi.spyOn(globalThis,"fetch").mockImplementation(async input=>{
    const url=String(input);
    return Response.json(url.includes("wrong-model")?result(wrongModel):
      commandResult(url.includes("newer")?newer:older));
  });
  const renderRuns=(runs:BackgroundRunRecord[])=> <LeagueOverview snapshot={snapshot}
    projection={projected} runs={runs} forecastRequests={forecastRequests}/>;
  const view=render(renderRuns([older]));
  await screen.findByText(/Run older .* Configuration/);
  view.rerender(renderRuns([older,{...newer,status:"running",result_available:false},wrongPolicy,unknown]));
  expect(screen.getByText(/baseline simulation is active/)).toBeInTheDocument();
  expect(screen.getByText(/Run older .* Configuration/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledOnce();
  view.rerender(renderRuns([older,newer,wrongPolicy,unknown]));
  await screen.findByText(/Run newer .* Configuration/);
  view.rerender(renderRuns([older,newer,wrongPolicy,wrongModel,unknown]));
  await screen.findByText(/retained model or sampling configuration does not match/);
  expect(screen.getByText(/Run newer .* Configuration/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(3);
});

test("projected Playoff Race orders all teams and distinguishes the field reference from actual seed assignments",()=>{
  if(projected.state.status!=="available") throw Error("Projection fixture unavailable");
  const teams=projected.state.result.teams.map((team,index)=>({...team,
    final_regular_rank:[4,1,2,3][index],
    postseason_seed:[2,1,null,null][index],
    championship_qualifier:[true,true,false,null][index],
  }));
  render(<LeagueOverview snapshot={snapshot} projection={{...projected,state:{status:"available",
    result:{...projected.state.result,teams}}}}/>);
  const race=within(screen.getByRole("region",{name:"Playoff Race"}));
  const rows=race.getAllByRole("button");
  expect(rows).toHaveLength(4);
  expect(rows.map(row=>row.textContent)).toEqual([
    expect.stringContaining(snapshot.teams[1].display_name),
    expect.stringContaining("Outside championship field"),
    expect.stringContaining("Qualification unavailable"),
    expect.stringContaining("Seed 2 / Qualified"),
  ]);
  expect(race.getByText("2 of 4 teams qualify for the championship bracket")).toBeInTheDocument();
  expect(within(rows[1].closest("li")!).getByText(/2 championship slots/)).toBeInTheDocument();
  expect(race.queryByText("100%")).not.toBeInTheDocument();
});

test("probability race uses 0?100% fills, keeps unavailable teams, and adds precision on focus",async()=>{
  const user=userEvent.setup(), record=run("qualification","2026-10-23T12:00:00Z");
  const payload=commandResult(record);
  const teams=payload.result.teams.map((team,index)=>({...team,
    playoff_qualification: estimate([0,.123456,null,1][index]),
  }));
  vi.spyOn(globalThis,"fetch").mockImplementation(async()=>Response.json({...payload,result:{...payload.result,teams}}));
  render(<LeagueOverview snapshot={snapshot} projection={projected} runs={[record]}
    forecastRequests={new Map([[record.run_id,forecastRequest]])}/>);
  const race=within(screen.getByRole("region",{name:"Playoff Race"}));
  await race.findByText("Ranked by qualification probability. Field size is a reference.");
  const rows=race.getAllByRole("button");
  expect(rows.map(row=>row.querySelector(".race-value")?.textContent)).toEqual(["100%","12.3456%","0%","Unavailable"]);
  expect(rows.map(row=>row.querySelector<HTMLElement>(".race-fill")?.style.width)).toEqual(["100%","12.3456%","0%",undefined]);
  expect(race.queryByText(/qualifying paths/)).not.toBeInTheDocument();
  await user.click(rows[1]);
  expect(within(rows[1]).getByText(/9.3456% to 15.3456% sampling interval/)).toBeInTheDocument();
  expect(rows[1].querySelector(".race-interval")).toBeInTheDocument();
  expect(race.getAllByRole("button")).toHaveLength(4);
  expect(screen.getByRole("complementary",{name:"Team Focus"})).toHaveTextContent(snapshot.teams[1].display_name);
});
