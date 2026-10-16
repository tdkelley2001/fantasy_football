import unittest

from fantasy_projection.search_runtime import prune_ranked, runtime_profile
from fantasy_projection.season import SeasonModelError


class SearchRuntimeTests(unittest.TestCase):
    def test_named_profiles_have_explicit_deterministic_and_mc_budgets(self):
        quick=runtime_profile('quick'); standard=runtime_profile('standard'); deep=runtime_profile('deep')
        self.assertEqual((1000,3,500),(quick.candidate_limit,quick.monte_carlo_finalists,quick.simulations))
        self.assertEqual((5000,5,1000),(standard.candidate_limit,standard.monte_carlo_finalists,standard.simulations))
        self.assertIsNone(deep.candidate_limit)

    def test_custom_profile_is_validated(self):
        custom=runtime_profile('custom',candidate_limit=321,monte_carlo_finalists=2,simulations=700)
        self.assertEqual((321,2,700),(custom.candidate_limit,custom.monte_carlo_finalists,custom.simulations))
        with self.assertRaises(SeasonModelError):runtime_profile('custom',candidate_limit=0)
        with self.assertRaises(SeasonModelError):runtime_profile('standard',monte_carlo_finalists=26)

    def test_pruning_is_stable_and_reports_omitted_candidates(self):
        kept,metadata=prune_ranked([5,1,3,2],2,key=lambda value:value)
        self.assertEqual([1,2],kept)
        self.assertEqual({'generated':4,'evaluated':2,'pruned':2,'approximate_pruning':True},metadata)
        all_rows,deep=prune_ranked([2,1],None,key=lambda value:value)
        self.assertEqual([2,1],all_rows)
        self.assertFalse(deep['approximate_pruning'])


if __name__ == '__main__': unittest.main()
