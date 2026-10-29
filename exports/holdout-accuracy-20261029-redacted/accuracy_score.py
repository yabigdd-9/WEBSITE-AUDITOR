"""Offline, evidence-bound accuracy scoring; never runs an auditor or provider.

Input contains reviewed observation units, not precomputed accuracy numbers.
Independent review and representativeness remain human attestations, not facts
that this program can authenticate. Output never grants release authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meaningful(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def timestamp(value: object) -> bool:
    if not meaningful(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.tzinfo is not None
    except ValueError:
        return False


def bound_file(root: Path, item: dict) -> Path:
    path = (root / item['path']).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Evidence must be an existing file inside the bundle')
    if digest(path) != item['sha256']:
        raise ValueError('Evidence hash mismatch: ' + item['path'])
    return path


def unit(item: dict) -> tuple[str, str, str]:
    values = tuple(item[name] for name in ('rule', 'url', 'location'))
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError('Observation identity requires rule, url and location')
    return values


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    scale = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / scale
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total**2)) / scale
    return [max(0.0, centre - half), min(1.0, centre + half)]


def score(manifest_path: Path) -> dict:
    raw = manifest_path.read_bytes()
    data = json.loads(raw)
    if data['schema_version'] != 'audit-accuracy/v1':
        raise ValueError('Unsupported schema')
    if not re.fullmatch(r'[0-9a-f]{40}', data['source_sha']):
        raise ValueError('Exact source revision required')
    if not meaningful(data['prediction_author']) or not data['required_strata']:
        raise ValueError('Prediction author and required strata are required')
    if not all(meaningful(value) for value in data['required_strata']):
        raise ValueError('Required strata must have meaningful names')
    root = manifest_path.parent
    blockers = []
    counts = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'uncertain': 0, 'unreviewed_predictions': 0}
    seen_cases, seen_fixtures, strata = set(), set(), set()
    development = set(data['development_fixture_sha256'])
    if not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in development):
        raise ValueError('Development SHA256 values must be lowercase hexadecimal')
    rows = []
    if not data['cases']:
        blockers.append('No cases supplied')
    for case in data['cases']:
        if case['case_id'] in seen_cases:
            raise ValueError('Duplicate case ID')
        seen_cases.add(case['case_id'])
        fixture = bound_file(root, case['fixture'])
        fixture_hash = digest(fixture)
        if fixture_hash in seen_fixtures:
            blockers.append(case['case_id'] + ': duplicate fixture bytes')
        if fixture_hash in development:
            blockers.append(case['case_id'] + ': development fixture reused')
        seen_fixtures.add(fixture_hash)
        strata.add(case['stratum'])
        prediction_path = bound_file(root, case['predictions'])
        predictions = json.loads(prediction_path.read_bytes())
        if predictions['source_sha'] != data['source_sha']:
            blockers.append(case['case_id'] + ': prediction source revision mismatch')
        if predictions['fixture_sha256'] != fixture_hash:
            blockers.append(case['case_id'] + ': prediction fixture binding mismatch')
        predicted = [unit(item) for item in predictions['observations']]
        if len(predicted) != len(set(predicted)):
            raise ValueError('Duplicate prediction unit')
        predicted = set(predicted)
        review_path = bound_file(root, case['review'])
        review = json.loads(review_path.read_bytes())
        if review['fixture_sha256'] != fixture_hash:
            blockers.append(case['case_id'] + ': review fixture binding mismatch')
        if not (meaningful(review.get('reviewer')) and timestamp(review.get('reviewed_at'))
                and review.get('independence_attested') is True
                and review['reviewer'].strip().casefold() != data['prediction_author'].strip().casefold()
                and review.get('exhaustive_within_scope') is True
                and meaningful(review.get('scope'))):
            blockers.append(case['case_id'] + ': independent complete review missing')
        if review.get('scope') != case['scope'] or predictions.get('scope') != case['scope']:
            blockers.append(case['case_id'] + ': review/prediction scope mismatch')
        labels = {}
        for label in review['observations']:
            key = unit(label)
            if key in labels:
                raise ValueError('Duplicate label unit')
            if label['verdict'] not in ('present', 'absent', 'uncertain'):
                raise ValueError('Unknown label verdict')
            if not meaningful(label.get('rationale')):
                raise ValueError('Label rationale missing')
            labels[key] = label['verdict']
        if not labels:
            blockers.append(case['case_id'] + ': no reviewed observation units')
        row = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0, 'uncertain': 0,
               'unreviewed_predictions': len(predicted - labels.keys())}
        for key, verdict in labels.items():
            if verdict == 'uncertain':
                row['uncertain'] += 1
            else:
                metric = ('tp' if key in predicted else 'fn') if verdict == 'present' else ('fp' if key in predicted else 'tn')
                row[metric] += 1
        if row['uncertain'] or row['unreviewed_predictions']:
            blockers.append(case['case_id'] + ': uncertain or unreviewed observations')
        for name, value in row.items():
            counts[name] += value
        rows.append({'case_id': case['case_id'], **row})
    missing = sorted(set(data['required_strata']) - strata)
    if missing:
        blockers.append('Missing required strata: ' + ', '.join(missing))
    policy = data['thresholds']
    for name in ('minimum_precision', 'minimum_recall'):
        if isinstance(policy[name], bool) or not isinstance(policy[name], (int, float)) or not 0 <= policy[name] <= 1:
            raise ValueError('Invalid accuracy threshold')
    minimum_cases = policy['minimum_cases']
    if isinstance(minimum_cases, bool) or not isinstance(minimum_cases, int) or minimum_cases < 1:
        raise ValueError('Invalid minimum case count')
    if not (meaningful(policy.get('approved_by')) and timestamp(policy.get('approved_at'))):
        blockers.append('Thresholds not approved')
    if len(rows) < minimum_cases:
        blockers.append('Insufficient case count')
    positive_predictions = counts['tp'] + counts['fp']
    positives = counts['tp'] + counts['fn']
    precision = counts['tp'] / positive_predictions if positive_predictions else None
    recall = counts['tp'] / positives if positives else None
    if precision is None or recall is None:
        blockers.append('Precision or recall denominator is empty')
    elif precision < policy['minimum_precision'] or recall < policy['minimum_recall']:
        blockers.append('Observed accuracy below proposed thresholds')
    return {
        'schema_version': 'audit-accuracy-result/v1',
        'input_sha256': hashlib.sha256(raw).hexdigest(),
        'source_sha': data['source_sha'], 'cases': rows, 'counts': counts,
        'precision_reviewed_units': precision, 'recall_reviewed_units': recall,
        'precision_wilson_95': wilson(counts['tp'], positive_predictions),
        'recall_wilson_95': wilson(counts['tp'], positives),
        'blockers': blockers, 'scoped_gate_passed': not blockers,
        'release_authorized': False,
        'limits': 'Point estimates and Wilson intervals describe reviewed units only. Units within a page are correlated. Identity, independence, completeness and representativeness are human attestations; hashes do not authenticate them. No runtime/resource claim is made.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    try:
        result = score(args.manifest)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'scoped_gate_passed': False,
                          'release_authorized': False}))
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['scoped_gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
