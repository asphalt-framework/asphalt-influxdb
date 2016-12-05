import logging
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Union, Iterable, Sequence, Optional, List

from aiohttp import ClientSession, ClientConnectionError, ClientResponse
from asphalt.core import Context
from typeguard import check_argument_types

from asphalt.influxdb.query import SelectQuery, Series
from asphalt.influxdb.utils import (
    merge_write_params, merge_query_params, convert_to_timestamp, quote_string)

logger = logging.getLogger(__name__)


class InfluxDBError(Exception):
    """Base exception class for InfluxDB related errors."""


class DataPoint:
    """
    Represents a data point to be written to the database.

    :ivar str measurement: name of the measurement
    :ivar tags: a dictionary of tag names to values
    :type tags: Dict[str, Any]
    :ivar fields: a dictionary of field names to values
    :type fields: Dict[str, Any]
    :ivar timestamp: time stamp for the measurement
    :type timestamp: Union[datetime, int, None]
    """

    __slots__ = ('measurement', 'tags', 'fields', 'timestamp')

    def __init__(self, measurement: str, tags: Dict[str, Any],
                 fields: Dict[str, Union[int, float, Decimal, bool, str]],
                 timestamp: Union[datetime, int] = None) -> None:
        assert check_argument_types()
        self.measurement = measurement
        self.tags = tags
        self.fields = fields
        self.timestamp = timestamp
        if not self.fields:
            raise ValueError('at least one field is required')

    def as_line(self, precision: Optional[str]) -> str:
        line = self.measurement

        if self.tags:
            line += ',' + ','.join('%s=%s' % (key, value) for key, value in self.tags.items())

        line += ' '
        fields = []
        for key, value in self.fields.items():
            if isinstance(value, (float, Decimal, bool)):
                value = str(value)
            elif isinstance(value, int):
                value = str(value) + 'i'
            else:
                value = quote_string(value)

            fields.append('%s=%s' % (key, value))

        line += ','.join(fields)
        if self.timestamp is not None:
            timestamp = self.timestamp
            if isinstance(timestamp, datetime):
                timestamp = convert_to_timestamp(timestamp, precision)

            line += ' %s' % timestamp

        return line


class InfluxDBClient:
    """
    An asyncio based InfluxDB client.

    To set advanced connection options like HTTP authentication, client certificates etc., see the
    documentation of the :class:`~aiohttp.ClientSession` and provide your own ``session`` argument
    to the constructor of this class.

    :param base_urls: an HTTP URL pointing to the InfluxDB server (or several URLs, in case of an
        InfluxEnterprise cluster)
    :param db: default database to use
    :param username: default user name to use for per-request authentication
    :param password: default password to use for per-request authentication
    :param consistency: default write consistency (for InfluxEnterprise) – one of ``any``, ``one``,
        ``quorum``, ``all`` or ``None``
    :param precision: default timestamp precision for writes – one of ``n``, ``u``, ``ms``, ``s``,
        ``m``, ``h`` or ``None``
    :param epoch: default timestamp precision for queries – one of ``n``, ``u``, ``ms``, ``s``,
        ``m``, ``h`` or ``None``
    :param retention_policy: default retention policy name to use for writes
    :param session: an aiohttp session or a resource name of one (if omitted, one is created
        automatically and closed when the client is closed)
    :param timeout: timeout (in seconds) for all HTTP requests
    """

    def __init__(self, base_urls: Union[str, Sequence[str]] = 'http://localhost:8086',
                 db: str = None, username: str = None, password: str = None,
                 consistency: str = None, retention_policy: str = None, precision: str = None,
                 chunked: Union[bool, int] = None, epoch: str = None,
                 session: Union[ClientSession, str] = None, timeout: int = 60) -> None:
        assert check_argument_types()
        base_urls = [base_urls] if isinstance(base_urls, str) else list(base_urls)
        self.base_urls = [url.rstrip('/') for url in base_urls]

        self.default_write_params = merge_write_params(
            {}, db=db, username=username, password=password, consistency=consistency,
            precision=precision, retention_policy=retention_policy)
        self.default_query_params = merge_query_params(
            {}, db=db, username=username, password=password, epoch=epoch, chunked=chunked,
            retention_policy=retention_policy
        )
        self.timeout = timeout

        if session:
            self._session = session
            self._close_session = False
        else:
            self._session = ClientSession()
            self._close_session = True

    async def start(self, ctx: Context) -> None:
        """Resolve Asphalt resource references."""
        if isinstance(self._session, str):
            self._session = await ctx.request_resource(ClientSession, self._session)

    async def close(self) -> None:
        """
        Close the HTTP client session if it was automatically created with the client instance.

        """
        if self._close_session:
            await self._session.close()

        self._session = None

    async def _request(self, method: str, path: str, **kwargs) -> ClientResponse:
        for i, base_url in enumerate(self.base_urls):
            try:
                response = await self._session.request(method, base_url + path,
                                                       timeout=self.timeout, **kwargs)
            except ClientConnectionError as e:
                logger.error('error connecting to %s: %s', base_url, e)
            except Exception as e:
                raise InfluxDBError('unexpected error when connecting to %s' % base_url) from e
            else:
                # Move the known-good base URL to the beginning of the list so it gets tried first
                # on the next request
                if len(self.base_urls) > 1:
                    self.base_urls.insert(0, self.base_urls.pop(i))

                return response
        else:
            raise InfluxDBError('no servers could be reached')

    def query(self, *args, **kwargs) -> SelectQuery:
        """
        Create a query builder.

        :param args: positional arguments to pass to :class:`~..query.SelectQuery`
        :param kwargs: keyword arguments to pass to :class:`~asphalt.influxdb.query.SelectQuery`
        :return: a query builder object

        """
        return SelectQuery(self, *args, **kwargs)

    async def raw_query(self, query: str, *, http_verb: str = None, **query_params) -> \
            Union[Series, List[Series], List[List[Series]]]:
        """
        Send a raw query to the server.

        :param query: the query string
        :param http_verb: the HTTP verb (``GET`` or ``POST``) to use in the HTTP request
            (autodetected for most queries if omitted; ``SELECT ... INTO`` in particular cannot be
            autodetected)
        :param query_params: HTTP query parameters
        :return: depending on the query and the results:

            * ``None`` (if there are no series or errors in the results)
            * a single series
            * a list of series (if selecting from more than one measurement)
            * a list of lists of series (if the query string contained multiple queries)

            Each series can also be replaced by an :class:`.InfluxDBError` if the server returned
            an error for that particular series.
        :raises InfluxDBError: if the server returns an error or an unexpected HTTP status code

        """
        def get_series(result: Dict[str, Any]) -> Union[Series, List[Series], InfluxDBError, None]:
            if 'error' in result:
                return InfluxDBError(result['error'])
            elif 'series' in result:
                series_list = [Series(**item) for item in result['series']]
                return series_list[0] if len(series_list) == 1 else series_list
            else:
                return None

        assert check_argument_types()

        # Autodetecting SELECT ... INTO would require parsing of the query string
        if http_verb is None:
            if query.startswith('SHOW ') or query.startswith('SELECT '):
                http_verb = 'GET'
            else:
                http_verb = 'POST'

        query_params = merge_query_params(self.default_query_params, **query_params)
        query_params['q'] = query
        response = await self._request(http_verb, '/query', params=query_params)
        with closing(response):
            if response.status == 200:
                results = (await response.json())['results']
                series_list = [get_series(result) for result in results]
                if len(series_list) == 1:
                    if isinstance(series_list[0], InfluxDBError):
                        raise series_list[0]
                    else:
                        return series_list[0]
                else:
                    return series_list
            elif (response.status in (400, 404, 500) and
                  response.content_type == 'application/json'):
                body = await response.json()
                raise InfluxDBError(body['error'])
            else:
                raise InfluxDBError('unexpected HTTP status code: %d' % response.status)

    async def write(self, measurement: str, tags: Dict[str, Any],
                    fields: Dict[str, Union[float, Decimal, bool, str]],
                    timestamp: Union[datetime, int] = None, **write_params) -> None:
        """
        Write a single data point to the database.

        This is a shortcut for instantiating a :class:`.DataPoint` and passing it in a tuple to
        :meth:`write_many`.

        :param measurement: name of the measurement
        :param tags: a dictionary of tag names to values
        :param fields: a dictionary of field names to values
        :param timestamp: time stamp for the measurement
        :param write_params: overrides for default write parameters
        :raises InfluxDBError: if the server returns an error or an unexpected HTTP status code

        """
        datapoint = DataPoint(measurement, tags, fields, timestamp)
        return await self.write_many((datapoint,), **write_params)

    async def write_many(self, datapoints: Iterable[DataPoint], **write_params) -> None:
        """
        Write the given data points to the database.

        :param datapoints: data points to write
        :param write_params: overrides for default write parameters
        :raises InfluxDBError: if the server returns an error or an unexpected HTTP status code

        """
        write_params = merge_write_params(self.default_write_params, **write_params)
        precision = write_params.get('precision')
        lines = '\n'.join(datapoint.as_line(precision) for datapoint in datapoints)
        response = await self._request('POST', '/write', data=lines.encode('utf-8'),
                                       params=write_params)
        with closing(response):
            if response.status == 204:
                return
            elif (response.status in (400, 404, 500) and
                  response.content_type == 'application/json'):
                body = await response.json()
                raise InfluxDBError(body['error'])
            else:
                raise InfluxDBError('unexpected HTTP status code: %d' % response.status)

    async def ping(self) -> str:
        """
        Check connectivity to the server.

        :return: value of the ``X-Influxdb-Version`` response header
        :raises InfluxDBError: if the server returns an error or an unexpected HTTP status code

        """
        response = await self._request('GET', '/ping')
        with closing(response) as response:
            if response.status == 204:
                return response.headers['X-Influxdb-Version']
            else:
                raise InfluxDBError('unexpected HTTP status code: %d' % response.status)
