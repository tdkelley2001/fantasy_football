import unittest
from unittest.mock import patch

from fantasy_projection.progress import Progress


class ProgressTests(unittest.TestCase):
    @patch('fantasy_projection.progress.TerminalProgress')
    def test_iteration_counts_only_completed_items(self, terminal):
        events = []
        work = Progress([1, 2], desc='Projections', unit='weeks', callback=lambda *e: events.append(e))
        for item in work:
            self.assertEqual(events[-1][1], item - 1)
        self.assertEqual(events, [('Projections', 0, 2, 'weeks'),
                                  ('Projections', 1, 2, 'weeks'),
                                  ('Projections', 2, 2, 'weeks')])
        terminal.return_value.close.assert_called_once()

    @patch('fantasy_projection.progress.TerminalProgress')
    def test_failure_does_not_claim_completed_work(self, terminal):
        events = []
        work = Progress([1, 2], callback=lambda *e: events.append(e))
        iterator = iter(work)
        next(iterator)
        iterator.close()
        self.assertEqual(events[-1][1], 0)
        terminal.return_value.close.assert_called_once()
