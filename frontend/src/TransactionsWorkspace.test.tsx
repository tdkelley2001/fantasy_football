import {act, render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {App} from "./App";
import {discoveryDraft} from "./ProjectedOpportunities";
import {activeRun, health, snapshot} from "./test/fixtures";
import type {ProjectedOpportunityResult, SnapshotSummary} from "./types/api";

const live: SnapshotSummary = {...snapshot, players: [...snapshot.players,
  {...snapshot.players[0], player_id:201, display_name:"Harbor Receiver"},
  {...snapshot.players[0], player_id:401, display_name:"Available Receiver",acquisition_status:"FREEAGENT"}],
  roster_assignments:[...snapshot.roster_assignments,{player_id:201,team_id:2,lineup_slot_id:2}],
  live_scoring:{current_scoring_period:8,last_fully_completed_period:7,earliest_unresolved_period:null,
    next_fully_unplayed_period:9,supported_simulation_week:null,partial_week_simulation_required:true,
    boundary_method:"unresolved",boundary_rationale:"",weeks:[],unresolved_capabilities:[],
    current_week_execution_available:true,supported_trade_weeks:[8,9,10],
    player_earliest_trade_weeks:[[101,8],[201,9]]},
};
const transfers=[{player_id:101,from_team_id:1,to_team_id:2},{player_id:201,from_team_id:2,to_team_id:1}];
const timeline=[{scoring_week:9,transfers}];
const action={action_index:1,action_type:"trade",team_id:1,counterparty_team_id:2,
  outgoing_player_ids:[101],incoming_player_ids:[201],acquired_player_id:null,dropped_player_id:null,
  source_candidate_id:"engine-candidate",conditional:false};
const candidate:ProjectedOpportunityResult["candidates"][number]={
  candidate_id:"trade-1", actions:[action], timeline, explicit_changes:transfers,
  forced_drops:[], automatic_additions:[], caveats:[], evaluation_index:0, limitation:null,
};
const base={snapshot_id:live.snapshot_id,canonical_sha256:live.canonical_sha256,status:"complete",
  teams:live.teams.map((team,index)=>({team_id:team.team_id,final_regular_rank:index+1,
    postseason_seed:index<2?index+1:null,final_placement:index+1,final_regular_standing:team})),
  weeks:[],postseason:[],transactions:[],unresolved_capabilities:[],champion_team_id:1};
const hypothetical={...base,champion_team_id:2,teams:base.teams.map(team=>team.team_id===1?
  {...team,final_regular_rank:2,final_regular_standing:{...team.final_regular_standing,points_for:812.75}}:team)};
const compare={baseline:base,hypothetical,timeline,explicit_changes:transfers,
  baseline_final_roster:[],hypothetical_final_roster:[],forced_drops:[],automatic_additions:[]};
const refreshed={...live,snapshot_id:"new-snapshot",canonical_sha256:"b".repeat(64)};
const reply=(body:unknown)=>Promise.resolve(Response.json(body));
function mockServer(candidates:ProjectedOpportunityResult["candidates"]=[candidate]) {
  const payload={snapshot_id:live.snapshot_id,canonical_sha256:live.canonical_sha256,
    baseline:{season:base,final_roster:[]},evaluations:[{season:hypothetical,final_roster:[]}],
    candidates,generated_candidates:candidates.length,candidate_coverage_complete:false,
    evaluation_coverage_complete:true,truncation_reason:"Configured candidate limit reached."};
  return vi.spyOn(globalThis,"fetch").mockImplementation((input,init)=>{
    const path=String(input);
    if(path.endsWith("/health"))return reply(health);
    if(path.endsWith("/snapshots"))return reply([live,refreshed]);
    if(path.endsWith("/managers") || path.includes("/refresh/"))return reply(null);
    if(path.endsWith("/"+live.snapshot_id))return reply(live);
    if(path.endsWith("/"+refreshed.snapshot_id))return reply(refreshed);
    if(path.includes("/runs"))return reply([]);
    if(path.endsWith("/analyses/projected-baseline"))return reply({...base,observed_scores:[],assumptions:[]});
    if(path.endsWith("/analyses/projected-opportunities"))return reply(payload);
    if(path.endsWith("/analyses/projected-scenario")){
      const request=JSON.parse(String(init?.body));
      return reply({...compare,scenario_id:request.scenario.scenario_id});
    }
    throw new Error(path);
  });
}

afterEach(()=>{
  vi.restoreAllMocks();
  localStorage.clear();
  window.history.replaceState(null,"","/");
});

test("legacy Discover route hands off the exact timed exchange, preserves the draft on Back and evaluates it",async()=>{
  const fetch=mockServer();
  window.history.replaceState(null,"","/players-moves/opportunities");
  const user=userEvent.setup();
  render(<App/>);
  await screen.findByRole("heading",{name:"Transactions"});
  await user.click(screen.getByRole("button",{name:"Find projected trades"}));
  await user.click(await screen.findByText("Sanitized Player / Harbor Receiver / Week 9"));
  await user.click(screen.getByRole("button",{name:"Open in Evaluate"}));
  expect(window.location.pathname).toBe("/transactions/evaluate");
  const nav=within(screen.getByRole("navigation",{name:"Transactions views"}));
  expect(screen.queryByRole("region",{name:"Discovered exchange"})).not.toBeInTheDocument();
  expect(screen.getByRole("heading",{name:"Build the exchange"})).toHaveFocus();
  expect(screen.getByText("Effective week 9")).toBeVisible();
  expect(screen.queryByRole("region",{name:"Two-team trade builder"})).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Open roster editor"})).toHaveAttribute("aria-expanded","false");
  await user.click(screen.getByRole("button",{name:"Remove step 1"}));
  expect(screen.getByRole("region",{name:"Two-team trade builder"})).toBeVisible();
  await user.click(nav.getByRole("button",{name:"Discover"}));
  await user.click(screen.getByRole("button",{name:"Open in Evaluate"}));
  await user.click(nav.getByRole("button",{name:"Discover"}));
  expect(screen.getByRole("button",{name:"Open in Evaluate"})).toHaveFocus();
  await act(async()=>window.history.back());
  await user.click(await screen.findByRole("button",{name:"Evaluate Trade"}));
  const evaluation=within(screen.getByRole("region",{name:"Projected season comparison"}));
  expect(await evaluation.findByText(/Champion in each projection/)).toHaveTextContent(/North Harbor.*Sunday Union/);
  const participants=within(evaluation.getByRole("region",{name:"Participating team projections"}));
  expect(participants.getByRole("heading",{name:"North Harbor"})).toBeVisible();
  expect(participants.getByRole("heading",{name:"Sunday Union"})).toBeVisible();
  expect(participants.getByText("811.40 → 812.75")).toBeVisible();
  const request=fetch.mock.calls.find(([url])=>String(url).endsWith("/projected-scenario"));
  expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
    canonical_sha256:live.canonical_sha256,
    scenario:{changes:transfers,effective_trades:[{selected_week:9,transfers}]},
  });
  await user.click(nav.getByRole("button",{name:"Discover"}));
  await user.click(screen.getByRole("button",{name:"Open in Evaluate"}));
  expect(screen.getByText(/replaces the current draft/)).toBeVisible();
  await user.click(screen.getByRole("button",{name:"Keep current draft"}));
  expect(evaluation.getByText(/Champion in each projection/)).toBeVisible();
  await user.click(screen.getByRole("button",{name:"Open league context"}));
  await user.click(screen.getByText("Saved snapshots"));
  await user.selectOptions(screen.getByLabelText("Active snapshot"),refreshed.snapshot_id);
  await user.keyboard("{Escape}");
  expect(await screen.findByText("No transaction steps yet")).toBeVisible();
  expect(screen.queryByText(/Champion in each projection/)).not.toBeInTheDocument();
});

test("advanced discovery opens the existing form with manager context and returns to a retained search",async()=>{
  const fetch=mockServer(),fallback=fetch.getMockImplementation()!;
  const run={...activeRun,run_type:"action_search",status:"completed",result_available:true};
  const older={...run,run_id:"older-search",finished_at_utc:"2020-01-01T00:00:00Z"};
  let submitted=false;
  let finished=false;
  fetch.mockImplementation((input,init)=>{
    const path=String(input);
    if(path.endsWith("/managers"))return reply({snapshot_id:live.snapshot_id,default_team_id:2,
      choices:[{manager_id:"manager",display_name:"Manager",team_id:2,is_primary:true}]});
    if(path.endsWith("/runs/action-search")) {
      submitted=true;
      return reply(run);
    }
    if(path.endsWith("/result"))return reply({api_schema_version:"1.0",run:path.includes(older.run_id)?older:run,result:{
      api_schema_version:"1.0",provenance:{snapshot_id:live.snapshot_id,canonical_sha256:live.canonical_sha256},
      stop_reason:"candidate_limit",coverage:{retained_candidates:0,unique_completed_states:0,
        candidate_coverage_complete:false,evaluation_coverage_complete:false,statistical_precision_complete:false,ranking_resolved:false},
    }});
    if(path.includes("/candidates?"))return reply({run_id:run.run_id,candidates:[],total:0});
    if(path.endsWith("/progress"))return reply({run_id:run.run_id,stage:"evaluating"});
    if(path.includes("/runs"))return reply(submitted?[finished?run:{...run,status:"running",result_available:false},older]:[]);
    return fallback(input,init);
  });
  window.history.replaceState(null,"","/transactions");
  const user=userEvent.setup();
  render(<App/>);
  await user.click(await screen.findByText("Find more types of moves",{selector:"summary"}));
  expect(window.location.pathname).toBe("/transactions");
  expect(screen.queryByRole("heading",{name:"Simulation Center"})).not.toBeInTheDocument();
  expect(within(document.getElementById("configure")!).getByLabelText("Requesting team")).toHaveValue("2");
  expect(submitted).toBe(false);
  await user.click(screen.getByRole("button",{name:"Submit action search"}));
  const request=fetch.mock.calls.find(([url])=>String(url).endsWith("/runs/action-search"));
  expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
    snapshot:{snapshot_id:live.snapshot_id},candidate_search:{requesting_team_id:2},
  });
  expect(await screen.findByText(/Search running/i)).toBeVisible();
  finished=true;
  const selector=await screen.findByRole("combobox",{name:"Completed action search"},{timeout:4000});
  expect(await screen.findByText("Ranking unresolved",{exact:true},{timeout:4000})).toBeVisible();
  expect(selector).toHaveValue(run.run_id);
  await user.selectOptions(selector,older.run_id);
  expect(await screen.findByText("Ranking unresolved",{exact:true})).toBeVisible();
  expect(selector).toHaveValue(older.run_id);
  await user.click(screen.getByRole("button",{name:"Prior analyses"}));
  await user.click(await screen.findAllByRole("button",{name:"Open opportunity search"}).then(buttons=>buttons[0]));
  expect(await screen.findByText("Ranking unresolved",{exact:true})).toBeVisible();
});

test.each([
  [{timeline:[]},/effective week cannot be verified/],
  [{limitation:"Evaluation budget exhausted",evaluation_index:null},/completed comparison is needed/],
  [{actions:[action,{...action,action_index:2}]},/ordered intent cannot be reproduced/],
  [{explicit_changes:[{...transfers[0],from_team_id:2},transfers[1]]},/ownership changes disagree/],
] as const)("shows unsupported candidates without offering a handoff",async (change,reason)=>{
  mockServer([{...candidate,...change}]);
  window.history.replaceState(null,"","/transactions");
  const user=userEvent.setup();
  render(<App/>);
  await user.click(await screen.findByRole("button",{name:"Find projected trades"}));
  const row=await screen.findByText(/Sanitized Player \/ Harbor Receiver/);
  await user.click(row);
  expect(screen.getByText(reason)).toBeVisible();
  expect(screen.queryByRole("button",{name:"Open in Evaluate"})).not.toBeInTheDocument();
});

test("opens a canonical structural exchange without manufacturing a scoring week",()=>{
  const canonical={...live,live_scoring:undefined};
  const structural={...candidate,timeline:[]};
  expect(discoveryDraft(canonical,structural,1,2)).toEqual({
    teamId:1,counterpartyId:2,step:{step_id:"discovery-trade-1",transfers},
  });
  expect(discoveryDraft({...canonical,roster_assignments:snapshot.roster_assignments},structural,1,2))
    .toMatch(/ownership differs from the active roster/);
});
