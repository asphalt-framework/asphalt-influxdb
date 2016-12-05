from datetime import datetime, timezone
from functools import total_ordering
from typing import List, Dict, Union, Any

from asphalt.influxdb.utils import quote_string


@total_ordering
class KeyedTuple:
    """
    Represents a single result row from a SELECT query.

    Columns can be accessed either as attributes or in a dict-like manner.
    This class also implements ``__len__`` plus all equality and comparison operators.
    """

    __slots__ = ('columns', '_row')

    def __init__(self, columns: Dict[str, int], row: List) -> None:
        self.columns = columns
        self._row = row

        # Convert the timestamp (if included) to a datetime
        time_index = columns.get('time')
        if time_index is not None:
            row[time_index] = datetime.strptime(row[time_index], '%Y-%m-%dT%H:%M:%S.%fZ').\
                replace(tzinfo=timezone.utc)

    def __getattr__(self, key: str):
        try:
            return self._row[self.columns[key]]
        except KeyError:
            raise AttributeError('no such column: %s' % key) from None

    def __getitem__(self, key: Union[str, int]):
        if isinstance(key, int):
            return self._row[key]
        else:
            return self.__getattr__(key)

    def __len__(self):
        return len(self._row)

    def __iter__(self):
        return iter(self._row)

    def __eq__(self, other):
        if isinstance(other, KeyedTuple):
            return self.columns == other.columns and self._row == other._row
        else:
            return NotImplemented

    def __lt__(self, other):
        if isinstance(other, KeyedTuple) and self.columns == other.columns:
            return self._row < other._row
        else:
            return NotImplemented


class Series:
    """
    Represents a series in the result set of a SELECT query.

    Iterating over instances of this class will yield :class:`~.KeyedTuple` instances.

    :ivar str name: name of the series
    :ivar tuple columns: column names
    """

    __slots__ = ('name', 'columns', '_values')

    def __init__(self, name: str, columns: List[str], values: List[list]) -> None:
        self.name = name
        self.columns = tuple(columns)
        self._values = values

    def __iter__(self):
        columns = {key: index for index, key in enumerate(self.columns)}
        for item in self._values:
            yield KeyedTuple(columns, item)

    def __len__(self):
        return len(self._values)


class SelectQuery:
    """Programmatic builder for SELECT queries."""

    __slots__ = ('_client', '_keys', '_measurements', '_query_params', '_into', '_where',
                 '_order_by', '_group_by')

    def __init__(self, client, keys: List[str], measurements: List[str], into: str = '',
                 where: str = '', group_by: str = '', order_by: str = '',
                 query_params: Dict[str, Any] = None) -> None:
        self._client = client
        self._keys = keys
        self._measurements = measurements
        self._into = into
        self._query_params = query_params or {}  # type: Dict[str, Any]
        self._where = where
        self._order_by = order_by
        self._group_by = group_by

    def into(self, into: str) -> 'SelectQuery':
        """Set or replace the INTO expression in the query."""
        return SelectQuery(self._client, self._keys, self._measurements, quote_string(into),
                           self._where, self._group_by, self._order_by, self._query_params)

    def where(self, expression: str) -> 'SelectQuery':
        """Set or replace the WHERE clause in the query."""
        return SelectQuery(self._client, self._keys, self._measurements, self._into, expression,
                           self._group_by, self._order_by, self._query_params)

    def group_by(self, *expressions: str) -> 'SelectQuery':
        """Set or replace the GROUP BY expression in the query."""
        expression = ','.join(expressions)
        return SelectQuery(self._client, self._keys, self._measurements, self._into, self._where,
                           expression, self._order_by, self._query_params)

    def order_by(self, *expressions: str) -> 'SelectQuery':
        """Set or replace the ORDER BY expression in the query."""
        expression = ','.join(expressions)
        return SelectQuery(self._client, self._keys, self._measurements, self._into, self._where,
                           self._group_by, expression, self._query_params)

    def params(self, **query_params) -> 'SelectQuery':
        """Set or replace the HTTP query parameters for this query."""
        return SelectQuery(self._client, self._keys, self._measurements, self._into, self._where,
                           self._group_by, self._order_by, query_params)

    async def execute(self) -> Series:
        """Execute the query on the server and return the result."""
        http_verb = 'POST' if self._into else 'GET'
        return await self._client.raw_query(str(self), http_verb=http_verb, **self._query_params)

    def __str__(self):
        text = 'SELECT ' + ','.join(text for text in self._keys)

        if self._into:
            text += ' INTO ' + self._into

        text += ' FROM ' + ','.join(quote_string(text) for text in self._measurements)

        if self._where:
            text += ' WHERE ' + self._where

        if self._group_by:
            text += ' GROUP BY ' + self._group_by

        if self._order_by:
            text += ' ORDER BY ' + self._order_by

        return text
