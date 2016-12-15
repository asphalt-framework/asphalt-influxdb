from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Dict, Any, Union, Optional

from typeguard import check_argument_types

value_types = Union[str, int, float, Decimal, bool, date]
precision_multipliers = {
    'h': 1 / 60 / 60,
    'm': 1 / 60,
    's': 1,
    'ms': 1000,
    'u': 1000000,
    'n': 1000000000,
    None: 1000000000
}


def quote_string(text):
    return '"%s"' % text.replace('"', '\"')


def convert_to_timestamp(dt: datetime, precision: Optional[str]) -> int:
    ts = dt.timestamp()
    return int(ts * precision_multipliers[precision])


def transform_value(value: value_types) -> str:
    assert check_argument_types()
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "\'")
    elif isinstance(value, bool):
        return str(value).upper()
    elif isinstance(value, int):
        return '%di' % value
    elif isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(' ')
    elif isinstance(value, date):
        return value.isoformat()
    else:
        return str(value)


def merge_write_params(old_params: Dict[str, Any], db: str = None, username: str = None,
                       password: str = None, consistency: str = None, retention_policy: str = None,
                       precision: str = None) -> Dict[str, Any]:
    assert check_argument_types()
    if consistency not in ('any', 'one', 'quorum', 'all', None):
        raise ValueError('consistency must be one of "any", "one", "quorum", "all" or None')
    if precision not in ('n', 'u', 'ms', 's', 'm', 'h', None):
        raise ValueError('precision must be one of "n", "u", "ms", "s", "m", "h" or None')

    new_params = {
        'consistency': consistency,
        'db': db,
        'p': password,
        'precision': precision,
        'rp': retention_policy,
        'u': username
    }
    new_params = {key: value for key, value in new_params.items() if value is not None}
    return dict(old_params, **new_params)


def merge_query_params(old_params: Dict[str, Any], db: str = None, username: str = None,
                       password: str = None, chunked: Union[bool, int] = None,
                       retention_policy: str = None, epoch: str = None) -> Dict[str, Any]:
    assert check_argument_types()
    if epoch not in ('n', 'u', 'ms', 's', 'm', 'h', None):
        raise ValueError('epoch must be one of "ns", "u", "ms", "s", "m", "h" or None')

    new_params = {
        'db': db,
        'p': password,
        'chunked': chunked,
        'epoch': epoch,
        'rp': retention_policy,
        'u': username
    }
    new_params = {key: value for key, value in new_params.items() if value is not None}
    return dict(old_params, **new_params)
