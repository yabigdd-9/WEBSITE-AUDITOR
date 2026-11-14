"""JSON input boundaries use disposable workspaces and no network."""
import json

import mm_local_inputs as inputs
import pytest


def test_owned_json_is_read_without_mutation(tmp_path):
    p = tmp_path / 'review.json'
    p.write_text('{"synthetic": true}')
    assert inputs.read_json(p, workspace=tmp_path) == {'synthetic': True}
    assert p.read_text() == '{"synthetic": true}'


@pytest.mark.parametrize('kind', ['outside', 'parent', 'symlink', 'extension'])
def test_unowned_input_is_rejected_before_read(tmp_path, monkeypatch, kind):
    base = tmp_path / 'workspace'
    base.mkdir()
    outside = tmp_path / 'private.json'
    outside.write_text('{"private": true}')
    p = outside
    if kind == 'parent':
        p = base / '../private.json'
    elif kind == 'symlink':
        p = base / 'alias.json'
        p.symlink_to(outside)
    elif kind == 'extension':
        p = base / 'private.env'
        p.write_text('{}')
    with pytest.raises(ValueError, match='JSON_INPUT_OUTSIDE'):
        inputs.read_json(p, workspace=base)


def test_input_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, 'MAX_JSON_BYTES', 8)
    p = tmp_path / 'large.json'
    p.write_text(json.dumps({'long': 'x' * 10}))
    with pytest.raises(ValueError, match='JSON_INPUT_TOO_LARGE'):
        inputs.read_json(p, workspace=tmp_path)
