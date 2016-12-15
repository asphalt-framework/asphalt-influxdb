from decimal import Decimal
from functools import total_ordering
from typing import List, Dict, Union, Any

from dateutil.parser import parse

from asphalt.influxdb.utils import quote_string, transform_value


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
            row[time_index] = parse(row[time_index])

    def _asdict(self) -> Dict[str, Any]:
        """Return the tuple as a dictionary."""
        return {col: self._row[index] for col, index in self.columns.items()}

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
    """
    Programmatic builder for SELECT queries.

    The query is considered immutable. None of the methods mutate existing queries,
    but rather return new copies of the original with the new parameters.
    """

    __slots__ = ('_client', '_select', '_from', '_query_params', '_into', '_where',
                 '_group_by', '_descending', '_limit', '_offset', '_slimit', '_soffset')

    def __init__(self, client, select: str, from_: str, into: str = '', where: str = '',
                 group_by: str = '', descending: bool = False, limit: int = None,
                 offset: int = None, slimit: int = None, soffset: int = None,
                 query_params: Dict[str, Any] = None) -> None:
        self._client = client
        self._select = select
        self._from = from_
        self._into = into
        self._where = where
        self._group_by = group_by
        self._descending = descending
        self._limit = limit
        self._offset = offset
        self._slimit = slimit
        self._soffset = soffset
        self._query_params = query_params or {}  # type: Dict[str, Any]

    def select(self, *expressions: str) -> 'SelectQuery':
        """
        Augment or reset the SELECT clause in the query.

        With no arguments, the SELECT clause is reset. Otherwise, the expressions will be added to
        the existing SELECT clause.

        :param expressions: raw InfluxQL expressions
        :return: a new query

        """
        expression = ','.join(expressions)
        if expression and self._select:
            expression = self._select + ',' + expression

        return SelectQuery(self._client, expression, self._from, self._into, self._where,
                           self._group_by, self._descending, self._limit, self._offset,
                           self._slimit, self._soffset, self._query_params)

    def into(self, into: str) -> 'SelectQuery':
        """
        Set the INTO expression in the query.

        :param into: name of the measurement to write the query results into.
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, quote_string(into),
                           self._where, self._group_by, self._descending, self._limit,
                           self._offset, self._slimit, self._soffset, self._query_params)

    def where(self, *expressions: str,
              **equals: Union[str, float, int, Decimal, bool]) -> 'SelectQuery':
        """
        Augment or reset the WHERE clause in the query.

        With no arguments, the WHERE clause is reset. Otherwise, the expressions will be joined to
        the existing WHERE clause using the ``AND`` operator.

        :param expressions: raw InfluxQL expressions
        :param equals: key-value pairs which are transformed into expressions,
            quoting/transforming as necessary
        :return: a new query

        """
        equal_exprs = tuple('%s = %s' % (quote_string(key), transform_value(value))
                            for key, value in equals.items())
        expression = ' AND '.join(expressions + equal_exprs)
        if expression and self._where:
            expression = self._where + ' AND ' + expression

        return SelectQuery(self._client, self._select, self._from, self._into, expression,
                           self._group_by, self._descending, self._limit, self._offset,
                           self._slimit, self._soffset, self._query_params)

    def group_by(self, *tags: str) -> 'SelectQuery':
        """
        Augment or reset the GROUP BY clause in the query.

        If a ``*`` is the existing GROUP BY clause or among the given tags, it will be set as the
        sole GROUP BY clause and all other tags will be ignored as they would be redundant.

        With no arguments, the GROUP BY clause is reset. Otherwise, the expressions will be added
        to the existing GROUP BY clause.

        :param tags: tags on which to group
        :return: a new query

        """
        if '*' in (self._group_by,) + tags:
            expression = '*'
        else:
            expression = ','.join(quote_string(tag) for tag in tags)
            if expression and self._group_by:
                expression = self._group_by + ',' + expression

        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           expression, self._descending, self._limit, self._offset, self._slimit,
                           self._soffset, self._query_params)

    def descending(self, value: bool) -> 'SelectQuery':
        """
        Set the sort order of the query.

        :param value: ``True`` to sort in descending order, ``False`` for ascending
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, value, self._limit, self._offset, self._slimit,
                           self._soffset, self._query_params)

    def limit(self, limit: int = None) -> 'SelectQuery':
        """
        Set the LIMIT clause in the query.

        :param limit: the new LIMIT value
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, self._descending, limit, self._offset, self._slimit,
                           self._soffset, self._query_params)

    def offset(self, offset: int = None) -> 'SelectQuery':
        """
        Set the OFFSET clause in the query.

        :param offset: the new OFFSET value
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, self._descending, self._limit, offset, self._slimit,
                           self._soffset, self._query_params)

    def slimit(self, slimit: int = None) -> 'SelectQuery':
        """
        Set the SLIMIT clause in the query.

        :param slimit: the new SLIMIT value
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, self._descending, self._limit, self._offset, slimit,
                           self._soffset, self._query_params)

    def soffset(self, soffset: int = None) -> 'SelectQuery':
        """
        Set the SOFFSET clause in the query.

        :param soffset: the new SOFFSET value
        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, self._descending, self._limit, self._offset,
                           self._slimit, soffset, self._query_params)

    def params(self, **query_params) -> 'SelectQuery':
        """
        Set or replace the HTTP query parameters for this query.

        :return: a new query

        """
        return SelectQuery(self._client, self._select, self._from, self._into, self._where,
                           self._group_by, self._descending, self._limit, self._offset,
                           self._slimit, self._soffset, query_params)

    async def execute(self) -> Union[Series, List[Series]]:
        """
        Execute the query on the server and return the result.

        :return: a series or a list of series, depending on the query

        """
        http_verb = 'POST' if self._into else 'GET'
        return await self._client.raw_query(str(self), http_verb=http_verb, **self._query_params)

    def __str__(self):
        text = 'SELECT ' + self._select

        if self._into:
            text += ' INTO ' + self._into

        text += ' FROM ' + self._from

        if self._where:
            text += ' WHERE ' + self._where

        if self._group_by:
            text += ' GROUP BY ' + self._group_by

        if self._descending:
            text += ' ORDER BY time DESC'

        if self._limit is not None:
            text += ' LIMIT %d' % self._limit

        if self._offset is not None:
            text += ' OFFSET %d' % self._offset

        if self._slimit is not None:
            text += ' SLIMIT %d' % self._slimit

        if self._soffset is not None:
            text += ' SOFFSET %d' % self._soffset

        return text
