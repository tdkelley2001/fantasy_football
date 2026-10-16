import unittest

from research.validate_residuals import Empirical, Metrics, Pools, folds


def row(year,week,projection=10,residual=0,pid=1,position="QB"):
    return dict(season=year,week=week,projection_points=projection,residual=residual,
                player_id=pid,position=position)


class EmpiricalValidationTests(unittest.TestCase):
    def test_crps_matches_direct_weighted_pairwise_definition(self):
        values=[-4.,0.,1.,9.]
        weights=[1.,2.,4.,3.]
        dist=Empirical(values,weights)
        normalized=[w/sum(weights) for w in weights]
        for observation in (-20,-4,0,2,9,30):
            for centered in (False,True):
                shifted=[x-(dist.mean if centered else 0) for x in values]
                expected=sum(w*abs(x-observation) for x,w in zip(shifted,normalized))
                expected-=sum(a*b*abs(x-y) for x,a in zip(shifted,normalized)
                              for y,b in zip(shifted,normalized))/2
                self.assertAlmostEqual(dist.crps(observation,centered),expected,places=12)

    def test_point_mass_quantiles_centering_and_boundary_coverage(self):
        d=Empirical([3,3])
        self.assertEqual(d.quantile(.95),3)
        self.assertEqual(d.crps(0,True),0)
        self.assertEqual(d.crps(0,False),3)
        self.assertTrue(d.evaluate(0)["95"]["covered"])
        self.assertEqual(d.evaluate(0)["95"]["width"],0)

    def test_weighted_quantiles_and_effective_sample_size(self):
        d=Empirical([1,10],[9,1])
        self.assertEqual(d.quantile(.5),1)
        self.assertEqual(d.quantile(.95),10)
        self.assertAlmostEqual(d.ess,1/.82)

    def test_invalid_pools_are_not_silently_replaced(self):
        for values,weights in (([],None),([1],[0]),([float("nan")],None),([1],[1,2])):
            with self.assertRaises(ValueError):Empirical(values,weights)

    def test_nearest_neighbors_match_exhaustive_selection(self):
        training=[row(2019,1,p,residual=p,pid=i) for i,p in enumerate([1,2,2,3,9,14,20])]
        pool=Pools(training)
        for query in (-5,2,4,15,30):
            expected=sorted(training,key=lambda r:(abs(r["projection_points"]-query),
                r["projection_points"],(r["season"],r["week"]),r["player_id"]))[:3]
            self.assertEqual(pool.local("QB",query,3),expected)
        with self.assertRaises(ValueError):pool.local("QB",5,500)
        tied=Pools([row(2019,1,10,pid=i) for i in range(600)])
        self.assertEqual([r["player_id"] for r in tied.local("QB",11,500)],list(range(500)))

    def test_training_cannot_include_forecast_week(self):
        p=Pools([row(2025,3)])
        for week in (2,3):
            with self.assertRaises(ValueError):p.forecast("A",row(2025,week))
        self.assertEqual(p.forecast("A",row(2025,4)).mean,0)

    def test_annual_and_weekly_splits_exclude_same_week(self):
        rows=[row(year,w) for year in range(2018,2026) for w in range(1,19)]
        for protocol in ("season_holdout","weekly_2025"):
            for _,train,test in folds(rows,protocol):
                self.assertLess(max((r["season"],r["week"]) for r in train),
                                min((r["season"],r["week"]) for r in test))
                if protocol=="season_holdout":
                    self.assertLess(max(r["season"] for r in train),test[0]["season"])

    def test_recency_changes_weights_without_changing_membership(self):
        rows=[row(2020 if i<250 else 2024,1,10,-2 if i<250 else 2,pid=i) for i in range(500)]
        p=Pools(rows);query=row(2025,1)
        d,e=p.forecast("D",query),p.forecast("E",query)
        self.assertEqual(d.x,e.x)
        self.assertAlmostEqual(d.mean,0)
        self.assertGreater(e.mean,0)
        self.assertLess(e.ess,d.ess)

    def test_coverage_and_width_aggregation(self):
        d=Empirical([-1,1]);metrics=Metrics()
        for actual in (-1,1,5):metrics.add(d.evaluate(actual,False))
        r=metrics.result()
        self.assertEqual(r["n"],3)
        self.assertAlmostEqual(r["95_covered"],2/3)
        self.assertAlmostEqual(r["95_above"],1/3)
        self.assertEqual(r["95_width"],2)


if __name__=="__main__":
    unittest.main()
