from asyncio import Future
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from asphalt.influxdb.query import KeyedTuple, SelectQuery, Series
from asphalt.influxdb.client import InfluxDBClient


class TestKeyedTuple:
    @pytest.fixture
    def test_tuple(self):
        return KeyedTuple({'col1': 0, 'col2': 1, 'col 3': 2}, [2.65, 2.19, 6.03])

    def test_timestamp(self):
        keyedtuple = KeyedTuple({'time': 0, 'col1': 1}, ['2016-12-11T13:40:45.150329483Z', 6])
        assert keyedtuple.time == datetime(2016, 12, 11, 13, 40, 45, 150329, timezone.utc)
        assert keyedtuple.col1 == 6

    def test_getattr(self, test_tuple):
        assert test_tuple.col1 == 2.65
        assert test_tuple.col2 == 2.19

    def test_getattr_error(self, test_tuple):
        pytest.raises(AttributeError, getattr, test_tuple, 'foo').match('no such column: foo')

    @pytest.mark.parametrize('indices', [
        ('col1', 'col2', 'col 3'),
        (0, 1, 2)
    ], ids=['names', 'numeric'])
    def test_getitem(self, test_tuple, indices):
        assert test_tuple[indices[0]] == 2.65
        assert test_tuple[indices[1]] == 2.19
        assert test_tuple[indices[2]] == 6.03

    def test_len(self, test_tuple):
        assert len(test_tuple) == 3

    def test_iter(self, test_tuple):
        assert list(test_tuple) == [2.65, 2.19, 6.03]

    def test_eq(self, test_tuple):
        assert test_tuple == KeyedTuple({'col1': 0, 'col2': 1, 'col 3': 2}, [2.65, 2.19, 6.03])
        assert not test_tuple == KeyedTuple({'X': 0, 'col2': 1, 'col 3': 2}, [2.65, 2.19, 6.03])
        assert not test_tuple == KeyedTuple({'col1': 0, 'col2': 1, 'col 3': 2}, [2.66, 2.19, 6.03])

    def test_eq_notimplemented(self, test_tuple):
        assert not test_tuple == 'blah'

    def test_lt(self, test_tuple):
        other = KeyedTuple({'col1': 0, 'col2': 1, 'col 3': 2}, [2.66, 2.19, 6.03])
        assert test_tuple < other

    def test_lt_notimplemented(self, test_tuple):
        with pytest.raises(TypeError):
            test_tuple < 'blah'


class TestSeries:
    @pytest.fixture
    def test_result(self):
        values = [
            [2.65, 2.19, 6.03],
            [8.38, 5.21, 1.076]
        ]
        return Series('dummyseries', ['col1', 'col2', 'col 3'], values)

    def test_iter(self, test_result):
        gen = iter(test_result)
        assert list(next(gen)) == [2.65, 2.19, 6.03]
        assert list(next(gen)) == [8.38, 5.21, 1.076]
        pytest.raises(StopIteration, next, gen)

    def test_len(self, test_result):
        assert len(test_result) == 2


class TestQuery:
    @pytest.fixture
    def fake_client(self):
        future = Future()
        future.set_result(None)
        client = Mock(InfluxDBClient)
        client.raw_query.configure_mock(return_value=future)
        return client

    @pytest.fixture
    def query(self, fake_client):
        return SelectQuery(fake_client, 'key1,key2', '"m1","m2"')

    def test_select(self, query):
        query = query.select('key3')
        assert str(query) == 'SELECT key1,key2,key3 FROM "m1","m2"'
        assert str(query.select().select('key5')) == 'SELECT key5 FROM "m1","m2"'

    def test_into(self, query):
        query = query.into('m3')
        assert str(query) == 'SELECT key1,key2 INTO "m3" FROM "m1","m2"'

    def test_where(self, query):
        query = query.where('key1 > 5', key2='blah').where('key3=5i').where(key4=4.25)
        assert str(query) == ('SELECT key1,key2 FROM "m1","m2" WHERE key1 > 5 AND "key2" = "blah" '
                              'AND key3=5i AND "key4" = 4.25')
        assert str(query.where()) == 'SELECT key1,key2 FROM "m1","m2"'

    def test_group_by(self, query):
        query = query.group_by('tag1', 'tag2').group_by('tag3')
        assert str(query) == 'SELECT key1,key2 FROM "m1","m2" GROUP BY "tag1","tag2","tag3"'
        assert str(query.group_by('*')) == 'SELECT key1,key2 FROM "m1","m2" GROUP BY *'
        assert str(query.group_by()) == 'SELECT key1,key2 FROM "m1","m2"'

    def test_descending(self, query):
        query = query.descending(True)
        assert str(query) == 'SELECT key1,key2 FROM "m1","m2" ORDER BY time DESC'
        assert str(query.descending(False)) == 'SELECT key1,key2 FROM "m1","m2"'

    def test_limit_offset(self, query):
        query = query.limit(3).offset(2)
        assert str(query) == 'SELECT key1,key2 FROM "m1","m2" LIMIT 3 OFFSET 2'
        assert str(query.limit().offset()) == 'SELECT key1,key2 FROM "m1","m2"'

    def test_slimit_soffset(self, query):
        query = query.slimit(3).soffset(2)
        assert str(query) == 'SELECT key1,key2 FROM "m1","m2" SLIMIT 3 SOFFSET 2'
        assert str(query.slimit().soffset()) == 'SELECT key1,key2 FROM "m1","m2"'

    @pytest.mark.asyncio
    async def test_execute(self, query, fake_client):
        query = query.params(rp='dontkeep', epoch='m')
        assert await query.execute() is None
        fake_client.raw_query.assert_called_once_with('SELECT key1,key2 FROM "m1","m2"',
                                                      http_verb='GET', rp='dontkeep', epoch='m')

    @pytest.mark.asyncio
    async def test_execute_into(self, query, fake_client):
        query = query.into('m3').params(rp='dontkeep', epoch='m')
        assert await query.execute() is None
        fake_client.raw_query.assert_called_once_with('SELECT key1,key2 INTO "m3" FROM "m1","m2"',
                                                      http_verb='POST', rp='dontkeep', epoch='m')
