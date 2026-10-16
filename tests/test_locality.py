import unittest

from research.check_locality import development_folds, neighborhood
from research.validate_residuals import Pools


def row(year, pid=1, projection=10):
    return dict(season=year,week=1,player_id=pid,position="QB",projection_points=projection,residual=0)


class LocalityTests(unittest.TestCase):
    def test_future_seasons_cannot_enter_either_partition(self):
        rows=[row(y) for y in range(2018,2027)]
        for year,training,evaluation in development_folds(rows):
            self.assertLessEqual(year,2024)
            self.assertTrue(all(r["season"]<year for r in training))
            self.assertTrue(all(r["season"]==year for r in evaluation))

    def test_heldout_season_and_same_week_guards(self):
        pool=Pools([row(2019,i) for i in range(1000)])
        for year in (2019,2025,2026):
            with self.assertRaises(ValueError):neighborhood(pool,row(year))

    def test_larger_pool_prefix_matches_independent_k_selection_with_ties(self):
        pool=Pools([row(2019,i,i//12) for i in range(1400)])
        for query in (-1,10,115,150):
            full=neighborhood(pool,row(2020,projection=query))
            for k in (250,500,750,1000):
                self.assertEqual(full[:k],pool.local("QB",query,k))

    def test_insufficient_support_is_not_capped_silently(self):
        pool=Pools([row(2019,i) for i in range(999)])
        with self.assertRaises(ValueError):neighborhood(pool,row(2020))
