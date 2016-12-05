import asyncio
import re
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone

import pytest
from aiohttp import ClientSession
from asphalt.core import Context

from asphalt.influxdb.client import InfluxDBClient, DataPoint


async def run_query(query, method='POST', *, loop):
    async with ClientSession(loop=loop) as session:
        url = 'http://localhost:8086/query'
        params = {'q': query, 'db': 'asphalt_test'}
        async with session.request(method, url, params=params) as response:
            json = await response.json()
            if response.status == 200:
                return json['results']
            else:
                raise Exception(json['error'])


class TestDataPoint:
    def test_no_fields_error(self):
        pytest.raises(ValueError, DataPoint, 'm1', {}, {}).match('at least one field is required')

    @pytest.mark.parametrize('timestamp, expected', [
        (datetime(2016, 12, 3, 19, 26, 51, 53212, tzinfo=timezone.utc),
         'm1,tag1=abc,tag2=6 field1=5.5,field2=7i,field3="x" 1480793211053212'),
        (1480793211053212,
         'm1,tag1=abc,tag2=6 field1=5.5,field2=7i,field3="x" 1480793211053212'),
        (None, 'm1,tag1=abc,tag2=6 field1=5.5,field2=7i,field3="x"')
    ], ids=['datetime', 'integer', 'none'])
    def test_as_line(self, timestamp, expected):
        tags = OrderedDict([('tag1', 'abc'), ('tag2', 6)])
        fields = OrderedDict([('field1', 5.5), ('field2', 7), ('field3', 'x')])
        datapoint = DataPoint('m1', tags, fields, timestamp)
        assert datapoint.as_line('u') == expected


class TestClient:
    @pytest.fixture(scope='class', autouse=True)
    def testdb(self):
        with closing(asyncio.new_event_loop()) as loop:
            loop.run_until_complete(run_query('CREATE DATABASE "asphalt_test"', loop=loop))
            yield
            loop.run_until_complete(run_query('DROP DATABASE "asphalt_test"', loop=loop))

    @pytest.fixture
    def cleanup_measurements(self, event_loop):
        """Delete all data from the "m1" measurements."""
        yield
        event_loop.run_until_complete(run_query('DELETE FROM "m1"', loop=event_loop))

    @pytest.fixture
    def client(self, event_loop):
        client_ = InfluxDBClient(db='asphalt_test', precision='u')
        yield client_
        event_loop.run_until_complete(client_.close())

    @pytest.fixture
    def bad_cluster_client(self, event_loop):
        base_urls = ['http://localhost:9999', 'http://localhost:8086']
        client_ = InfluxDBClient(base_urls, db='asphalt_test', precision='u')
        yield client_
        event_loop.run_until_complete(client_.close())

    @pytest.mark.asyncio
    async def test_preexisting_session(self):
        """Test that the client does not close a pre-existing ClientSession on its way out."""
        session = ClientSession()
        client = InfluxDBClient(session=session)
        await client.close()
        assert not session.closed

    @pytest.mark.asyncio
    async def test_session_resource(self):
        """Test that the client can acquire a ClientSession resource when started."""
        session = ClientSession()
        client = InfluxDBClient(session='default')
        ctx = Context()
        ctx.publish_resource(session)
        await client.start(ctx)

    @pytest.mark.asyncio
    async def test_ping(self, client):
        version = await client.ping()
        assert re.match(r'^\d+\.\d+\.\d+$', version)

    @pytest.mark.asyncio
    async def test_cluster_ping(self, bad_cluster_client):
        """
        Test that the client tries the next base url on the node list when one fails to connect.

        """
        version = await bad_cluster_client.ping()
        assert re.match(r'^\d+\.\d+\.\d+$', version)
        assert bad_cluster_client.base_urls[0] == 'http://localhost:8086'

    @pytest.mark.asyncio
    async def test_raw_query(self, client, event_loop, cleanup_measurements):
        timestamp1 = datetime(2016, 12, 3, 19, 26, 51, 53212, tzinfo=timezone.utc)
        timestamp2 = datetime(2016, 12, 3, 19, 26, 52, 640291, tzinfo=timezone.utc)
        await client.write('m1', dict(tag1=5, tag6='a'), dict(f1=4.32, f2=6.9312), timestamp1)
        await client.write('m1', dict(tag1='x', tag6='xy'), dict(f1=5.22, f2=8.79), timestamp2)

        results = await client.raw_query('SELECT * FROM m1')
        assert results.name == 'm1'
        row1, row2 = results
        assert row1.time == timestamp1
        assert row1.tag1 == '5'
        assert row1.tag6 == 'a'
        assert row1.f1 == 4.32
        assert row1.f2 == 6.9312
        assert row2.time == timestamp2
        assert row2.tag1 == 'x'
        assert row2.tag6 == 'xy'
        assert row2.f1 == 5.22
        assert row2.f2 == 8.79

    @pytest.mark.asyncio
    async def test_write(self, client, event_loop, cleanup_measurements):
        timestamp = datetime(2016, 12, 3, 19, 26, 51, 53212, tzinfo=timezone.utc)
        await client.write('m1', dict(tag1=5, tag6='a'), dict(f1=4.32, f2=6.9312), timestamp)
        results = await run_query('SELECT * FROM m1', 'GET', loop=event_loop)
        assert results == [{
            'series': [{
                'columns': ['time', 'f1', 'f2', 'tag1', 'tag6'],
                'name': 'm1',
                'values': [['2016-12-03T19:26:51.053212Z', 4.32, 6.9312, '5', 'a']]
            }]
        }]

    @pytest.mark.asyncio
    async def test_write_many(self, client, event_loop, cleanup_measurements):
        datapoints = [
            DataPoint('m1', dict(tag1=5, tag6='a'), dict(f1=4.32, f2=6.9312),
                      datetime(2016, 12, 3, 19, 26, 51, 53212, tzinfo=timezone.utc)),
            DataPoint('m1', dict(tag1='abc', tag6='xx'), dict(f1=654.0, f2=3042.1),
                      1480796369123456)
        ]
        await client.write_many(datapoints)
        results = await run_query('SELECT * FROM m1', 'GET', loop=event_loop)
        assert results == [{
            'series': [{
                'columns': ['time', 'f1', 'f2', 'tag1', 'tag6'],
                'name': 'm1',
                'values': [['2016-12-03T19:26:51.053212Z', 4.32, 6.9312, '5', 'a'],
                           ['2016-12-03T20:19:29.123456Z', 654.0, 3042.1, 'abc', 'xx']]
            }]
        }]
