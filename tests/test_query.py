from asyncio import Future
from unittest.mock import Mock

import pytest

from asphalt.influxdb import KeyedTuple, SelectQuery, Series, InfluxDBClient


class TestKeyedTuple:
    @pytest.fixture
    def test_tuple(self):
        return KeyedTuple({'col1': 0, 'col2': 1, 'col 3': 2}, [2.65, 2.19, 6.03])

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
    def test_query(self, fake_client):
        return SelectQuery(fake_client, ['key1', 'key2'], ['m1', 'm2'])

    def test_str(self, test_query):
        test_query = test_query.into('m3').where('m1 > 6.54').order_by('m2 DESC', 'm1 ASC').\
            group_by('m1', 'm2')
        assert str(test_query) == ('SELECT key1,key2 INTO "m3" FROM "m1","m2" WHERE m1 > 6.54 '
                                   'GROUP BY m1,m2 ORDER BY m2 DESC,m1 ASC')

    @pytest.mark.asyncio
    async def test_execute(self, test_query, fake_client):
        test_query = test_query.params(rp='dontkeep', epoch='m')
        assert await test_query.execute() is None
        fake_client.raw_query.assert_called_once_with('SELECT key1,key2 FROM "m1","m2"',
                                                      http_verb='GET', rp='dontkeep', epoch='m')

    @pytest.mark.asyncio
    async def test_execute_into(self, test_query, fake_client):
        test_query = test_query.into('m3').params(rp='dontkeep', epoch='m')
        assert await test_query.execute() is None
        fake_client.raw_query.assert_called_once_with('SELECT key1,key2 INTO "m3" FROM "m1","m2"',
                                                      http_verb='POST', rp='dontkeep', epoch='m')
