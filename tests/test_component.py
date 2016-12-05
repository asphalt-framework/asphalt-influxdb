import pytest
from asphalt.core import Context

from asphalt.influxdb.client import InfluxDBClient
from asphalt.influxdb.component import InfluxDBComponent


@pytest.mark.asyncio
async def test_default_client(caplog):
    """Test that the default client configuration works as expected."""
    async with Context() as context:
        await InfluxDBComponent().start(context)
        assert isinstance(context.influxdb, InfluxDBClient)

    records = [record for record in caplog.records if record.name == 'asphalt.influxdb.component']
    records.sort(key=lambda r: r.message)
    assert len(records) == 2
    assert records[0].message == ("Configured InfluxDB client (default / ctx.influxdb; "
                                  "base_urls=['http://localhost:8086'])")
    assert records[1].message == 'InfluxDB client (default) shut down'


@pytest.mark.asyncio
async def test_clustered_client(caplog):
    """Test that a clustered client configuration works as expected."""
    async with Context() as context:
        base_urls = ['http://influx1.example.org:8086', 'http://influx2.example.org:8087/prefix']
        await InfluxDBComponent(base_urls=base_urls).start(context)
        assert isinstance(context.influxdb, InfluxDBClient)

    records = [record for record in caplog.records if record.name == 'asphalt.influxdb.component']
    records.sort(key=lambda r: r.message)
    assert len(records) == 2
    assert records[0].message == (
        "Configured InfluxDB client (default / ctx.influxdb; "
        "base_urls=['http://influx1.example.org:8086', 'http://influx2.example.org:8087/prefix'])")
    assert records[1].message == 'InfluxDB client (default) shut down'


@pytest.mark.asyncio
async def test_multiple_clients(caplog):
    """Test that a multiple client configuration works as expected."""
    async with Context() as context:
        await InfluxDBComponent(clients={
            'db1': {'base_urls': 'http://localhost:9999'},
            'db2': {'base_urls': 'https://remotehost.example.org:443/influx'}
        }).start(context)
        assert isinstance(context.db1, InfluxDBClient)
        assert isinstance(context.db2, InfluxDBClient)

    records = [record for record in caplog.records if record.name == 'asphalt.influxdb.component']
    records.sort(key=lambda r: r.message)
    assert len(records) == 4
    assert records[0].message == ("Configured InfluxDB client (db1 / ctx.db1; "
                                  "base_urls=['http://localhost:9999'])")
    assert records[1].message == ("Configured InfluxDB client (db2 / ctx.db2; "
                                  "base_urls=['https://remotehost.example.org:443/influx'])")
    assert records[2].message == 'InfluxDB client (db1) shut down'
    assert records[3].message == 'InfluxDB client (db2) shut down'
