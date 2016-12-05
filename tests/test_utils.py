from datetime import datetime, timezone

import pytest

from asphalt.influxdb.utils import (
    convert_to_timestamp, quote_string, merge_write_params, merge_query_params)


@pytest.mark.parametrize('value, expected', [
    ('abc def', '"abc def"'),
    ('"abc def"', '"\"abc def\""')
], ids=['noescape', 'escape'])
def test_quote_string(value, expected):
    assert quote_string(value) == expected


@pytest.mark.parametrize('precision, expected', [
    ('h', 411329),
    ('m', 24679758),
    ('s', 1480785505),
    ('ms', 1480785505123),
    ('u', 1480785505123456),
    ('n', 1480785505123456000)
], ids=['h', 'm', 's', 'ms', 'u', 'n'])
def test_convert_to_timestamp(precision, expected):
    dt = datetime(2016, 12, 3, 17, 18, 25, 123456, tzinfo=timezone.utc)
    assert convert_to_timestamp(dt, precision) == expected


def test_merge_write_params():
    defaults = {
        'db': 'testdb',
        'u': 'testuser',
        'p': 'testpass',
        'consistency': 'all',
        'rp': 'policy1',
        'precision': 'ms'
    }
    result = merge_write_params(defaults, db='anotherdb', username='user2', consistency='quorum',
                                retention_policy='policy2', precision='m')
    assert result == {
        'db': 'anotherdb',
        'u': 'user2',
        'p': 'testpass',
        'consistency': 'quorum',
        'rp': 'policy2',
        'precision': 'm'
    }


@pytest.mark.parametrize('kwargs, error', [
    ({'consistency': 'blah'}, 'consistency must be one of "any", "one", "quorum", "all" or None'),
    ({'precision': 'blah'}, 'precision must be one of "n", "u", "ms", "s", "m", "h" or None')
], ids=['consistency', 'precision'])
def test_merge_write_params_bad_values(kwargs, error):
    pytest.raises(ValueError, merge_write_params, {}, **kwargs).match(error)


def test_merge_query_params():
    defaults = {
        'db': 'testdb',
        'u': 'testuser',
        'p': 'testpass',
        'chunked': True,
        'rp': 'policy1',
        'epoch': 'ms'
    }
    result = merge_query_params(defaults, db='anotherdb', username='user2', chunked=5000,
                                retention_policy='policy2', epoch='m')
    assert result == {
        'db': 'anotherdb',
        'u': 'user2',
        'p': 'testpass',
        'chunked': 5000,
        'rp': 'policy2',
        'epoch': 'm'
    }


def test_merge_query_params_bad_values():
    pytest.raises(ValueError, merge_query_params, {}, epoch='blah').\
        match('epoch must be one of "ns", "u", "ms", "s", "m", "h" or None')
