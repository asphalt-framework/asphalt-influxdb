import logging

from async_generator import yield_
from typing import Dict, Any

from typeguard import check_argument_types

from asphalt.core import Component, Context, merge_config
from asphalt.core.context import context_teardown
from asphalt.influxdb.client import InfluxDBClient

logger = logging.getLogger(__name__)


class InfluxDBComponent(Component):
    """
    Creates one or more :class:`~asphalt.influxdb.client.InfluxDBClient` resources.

    If ``clients`` is given, an InfluxDB client resource will be added for each key in the
    dictionary, using the key as the resource name. Any extra keyword arguments to the component
    constructor will be used as defaults for omitted configuration values. The context attribute
    will by default be the same as the resource name, unless explicitly set with the
    ``context_attr`` option.

    If ``clients`` is omitted, a single InfluxDB client resource (``default`` / ``ctx.influxdb``)
    is added using any extra keyword arguments passed to the component.

    The client(s) will not connect to the target database until they're used for the first time.

    :param clients: a dictionary of resource name ⭢
        :class:`~asphalt.influxdb.client.InfluxDBClient` arguments
    :param default_client_args: default values for omitted
        :class:`~asphalt.influxdb.client.InfluxDBClient` arguments
    """

    def __init__(self, clients: Dict[str, Dict[str, Any]] = None, **default_client_args):
        assert check_argument_types()
        if not clients:
            default_client_args.setdefault('context_attr', 'influxdb')
            clients = {'default': default_client_args}

        self.clients = []
        for resource_name, config in clients.items():
            client_args = merge_config(default_client_args, config)
            context_attr = client_args.pop('context_attr', resource_name)
            client = InfluxDBClient(**client_args)
            self.clients.append((resource_name, context_attr, client))

    @context_teardown
    async def start(self, ctx: Context):
        for resource_name, context_attr, client in self.clients:
            await client.start(ctx)
            ctx.add_resource(client, resource_name, context_attr)
            logger.info('Configured InfluxDB client (%s / ctx.%s; base_urls=%r)', resource_name,
                        context_attr, client.base_urls)

        await yield_()

        for resource_name, context_attr, client in self.clients:
            logger.info('InfluxDB client (%s) shut down', resource_name)
