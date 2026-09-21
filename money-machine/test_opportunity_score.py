import unittest

from mm_core import CLAIM_TYPES, opportunity_score_6_component


class OpportunityScoreTests(unittest.TestCase):
    def test_score_uses_the_six_specified_component_weights(self):
        result = opportunity_score_6_component(1, 1, 1, 1, 1, 1)
        self.assertEqual(result['score'], 100)
        self.assertTrue(result['is_shortlist'])
        self.assertEqual(result['components']['supported_problem'], 25)

    def test_score_rejects_out_of_range_component_values(self):
        with self.assertRaises(ValueError):
            opportunity_score_6_component(1.1, 0, 0, 0, 0, 0)

    def test_claim_types_match_the_canonical_evidence_taxonomy(self):
        self.assertEqual(CLAIM_TYPES, (
            'observed_fact', 'explicit_request', 'interpretation', 'hypothesis',
            'contradiction',
        ))


if __name__ == '__main__':
    unittest.main()
