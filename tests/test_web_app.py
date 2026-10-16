import unittest
import threading
from unittest.mock import patch
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError
from fantasy_projection import web_app
from stop_app import stop_app
from fantasy_projection.web_app import AppState
from test_trade_analysis import _result


class WebAppTests(unittest.TestCase):
    def test_snapshot_is_explicit_and_excludes_credentials(self):
        state = AppState()
        self.assertIsNone(state.snapshot())
        state.baseline = _result(weekly_points=(10, 20), seeds=(1, 2), places=(1, 2), starters=(101, 202), champion="Alpha")
        state.my_id = 1
        state.config = {"espn_s2": "secret"}
        snapshot = state.snapshot()
        self.assertNotIn("config", snapshot)
        self.assertNotIn("settings_payload", snapshot)
        self.assertEqual(snapshot["my_id"], 1)

    def test_search_requires_snapshot_and_rejects_concurrent_work(self):
        state = AppState()
        with self.assertRaises(ValueError):
            state.start("trades")
        state.busy = True
        with self.assertRaises(ValueError):
            state.start("refresh")

    def test_simulation_controls_reject_invalid_counts_and_seeds(self):
        state=AppState()
        for options in ({"simulations":0},{"simulations":True},{"simulations":20001},
                        {"seed":-1},{"seed":1.5}):
            with self.assertRaises(ValueError):state.start("simulate",options)
        self.assertIsNone(state.simulation)

    def test_simulation_worker_publishes_progress_and_snapshot_result(self):
        from test_monte_carlo import state as fixture, model
        from fantasy_projection.season import project_season
        from types import SimpleNamespace
        app=AppState();app.baseline=project_season(fixture());app.my_id=1
        app.config=SimpleNamespace(espn_s2=None,swid=None);app.residual_model=model(zero=True)[0]
        class InlineThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        with patch.object(web_app.threading,'Thread',InlineThread),patch.object(web_app,'load_simulation_state',side_effect=lambda s,c:s):
            app.start('simulate',{'simulations':2,'seed':1})
        self.assertIsNone(app.error)
        self.assertFalse(app.busy)
        self.assertEqual(app.progress,{'stage':'Simulating seasons','done':2,'total':2,'unit':'seasons'})
        self.assertEqual(app.snapshot()['simulation']['metadata']['simulations'],2)

    def test_identical_trade_search_reuses_cached_results(self):
        from types import SimpleNamespace
        app=AppState();app.baseline=_result(weekly_points=(10,20),seeds=(1,2),places=(1,2),starters=(101,202),champion='Alpha')
        app.my_id=1;app.loaded='snapshot-1'
        result=SimpleNamespace(all_evaluations=[],search_summary=[{'generated':0}])
        class InlineThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        options={'search':{'mode':'quick','monte_carlo_finalists':0,'simulations':500}}
        with patch.object(web_app.threading,'Thread',InlineThread),patch.object(web_app,'evaluate_all_trades',return_value=result) as evaluate:
            app.start('trades',options);app.start('trades',options)
        evaluate.assert_called_once()
        self.assertEqual([],app.snapshot()['trades'])

    def test_search_monte_carlo_is_added_only_to_ranked_finalists(self):
        from types import SimpleNamespace
        from fantasy_projection.search_runtime import runtime_profile
        app=AppState();app.baseline=_result(weekly_points=(10,20),seeds=(1,2),places=(1,2),starters=(101,202),champion='Alpha')
        app.my_id=1;app.config=SimpleNamespace(espn_s2=None,swid=None);app.residual_model=object()
        rows=[{'evaluation_status':'VALID','mutual_sustained_weekly_lineup_gain':2,
               'my_give_player_ids':'101','my_receive_player_ids':'202','partner_team_id':2,
               'current_scoring_week':1},
              {'evaluation_status':'VALID','mutual_sustained_weekly_lineup_gain':1}]
        before={'teams':[{'team_id':1,'expected_wins':6.,'playoff_probability':.4,'championship_probability':.1},
                         {'team_id':2,'expected_wins':7.,'playoff_probability':.5,'championship_probability':.2}]}
        after={'teams':[{'team_id':1,'expected_wins':6.5,'playoff_probability':.5,'championship_probability':.15},
                        {'team_id':2,'expected_wins':6.8,'playoff_probability':.45,'championship_probability':.18}]}
        comparison=SimpleNamespace(after=app.baseline)
        runtime=runtime_profile('custom',candidate_limit=10,monte_carlo_finalists=1,simulations=100)
        with patch.object(web_app,'load_simulation_state',side_effect=lambda state,client:state),\
             patch.object(app,'_cached_search_simulation',side_effect=[before,after]),\
             patch.object(web_app,'evaluate_trade',return_value=comparison):
            metadata=app.simulate_search_finalists('trades',rows,runtime)
        self.assertEqual('COMPLETE',rows[0]['monte_carlo_status'])
        self.assertAlmostEqual(.1,rows[0]['my_mc_playoff_probability_change'])
        self.assertNotIn('monte_carlo_status',rows[1])
        self.assertEqual(1,metadata['finalists_simulated'])

    def test_search_simulation_cache_keys_complete_state_and_controls(self):
        from test_monte_carlo import state
        app=AppState();app.residual_model=object();result={'teams':[]}
        with patch.object(web_app,'simulate_season',return_value=result) as simulate:
            first=app._cached_search_simulation(state(),100,1,None)
            second=app._cached_search_simulation(state(),100,1,None)
        self.assertIs(first,second)
        simulate.assert_called_once()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.server = web_app.ThreadingHTTPServer(("127.0.0.1", 0), web_app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.client = build_opener(ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_stop_script_shuts_down_even_when_analysis_lock_is_held(self):
        with web_app.STATE.lock, patch('builtins.print'):
            self.assertEqual(0, stop_app(self.url))
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def test_comparison_keeps_status_responsive_and_clears_busy_on_failure(self):
        import json
        entered, release = threading.Event(), threading.Event()
        app = AppState()
        app.baseline = object()
        app.my_id = 1
        errors = []

        def evaluate(**kwargs):
            entered.set()
            release.wait(3)
            raise ValueError('Invalid selection')

        def compare():
            request = Request(self.url + '/api/compare', data=b'{"give":[1],"receive":[2],"effective_week":1}',
                              headers={'Content-Type': 'application/json'}, method='POST')
            try:
                self.client.open(request, timeout=4).close()
            except HTTPError as exc:
                errors.append(exc.code)
                exc.close()

        with patch.object(web_app, 'STATE', app), patch.object(web_app, 'evaluate_trade', evaluate):
            worker = threading.Thread(target=compare)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.client.open(self.url + '/api/status', timeout=1) as response:
                    status = json.load(response)
                self.assertEqual(status['busy'], 'compare')
                self.assertIsNone(status['progress']['total'])
                with self.assertRaises(ValueError):
                    app.start('refresh')
            finally:
                release.set()
                worker.join(4)
            self.assertFalse(app.busy)
            self.assertEqual(errors, [400])

    def test_shutdown_rejects_browser_origin_and_missing_control_header(self):
        for headers in ({}, {"Origin":"https://example.com", "X-Studio-Control":"shutdown"}):
            request = Request(self.url + '/api/shutdown', data=b'{}',
                              headers={"Content-Type":"application/json", **headers}, method='POST')
            with self.assertRaises(HTTPError) as error:
                self.client.open(request, timeout=2)
            self.assertEqual(403, error.exception.code)
            error.exception.close()
        self.assertTrue(self.thread.is_alive())

    def test_stop_script_leaves_unrecognized_service_running(self):
        with patch.object(web_app, 'APP_ID', 'another-app'), patch('builtins.print'):
            self.assertEqual(1, stop_app(self.url))
        self.assertTrue(self.thread.is_alive())

    def test_browser_opens_app_url(self):
        with patch.object(web_app.webbrowser, 'open', return_value=True) as browser:
            web_app._open_browser()
        browser.assert_called_once_with(web_app.APP_URL, new=2)

    def test_main_closes_socket_on_interrupt_and_respects_no_browser(self):
        with patch.object(web_app, 'ThreadingHTTPServer') as factory, patch.object(web_app.threading, 'Thread') as thread, patch('builtins.print'):
            factory.return_value.serve_forever.side_effect = KeyboardInterrupt
            web_app.main(open_browser=False)
            thread.assert_not_called()
            factory.return_value.server_close.assert_called_once()
