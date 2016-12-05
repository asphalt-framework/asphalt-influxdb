import logging
from functools import partial
from typing import Dict, Any

from asphalt.core import Component, Context, merge_config
from typeguard import check_argument_types

from asphalt.influxdb.client import InfluxDBClient

logger = logging.getLogger(__name__)


class InfluxDBComponent(Component):
    """
    Publishes one or more :class:`~asphalt.influxdb.client.InfluxDBClient` resources.

    If ``clients`` is given, a InfluxDB client resource will be published for each key in the
    dictionary, using the key as the resource name. Any extra keyword arguments to the component
    constructor will be used as defaults for omitted configuration values. The context attribute
    will by default be the same as the resource name, unless explicitly set with the
    ``context_attr`` option.

    If ``clients`` is omitted, a single InfluxDB client resource (``default`` / ``ctx.influxdb``)
    is published using any extra keyword arguments passed to the component.

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
            self.clients.append((resource_name, context_attr, client_args))

    @staticmethod
    async def shutdown_client(event, client: InfluxDBClient, resource_name: str):
        await client.close()
        logger.info('InfluxDB client (%s) shut down', resource_name)

    async def start(self, ctx: Context):
        for resource_name, context_attr, client_args in self.clients:
            client = InfluxDBClient(**client_args)
            ctx.finished.connect(
                partial(self.shutdown_client, client=client, resource_name=resource_name))
            ctx.publish_resource(client, resource_name, context_attr)
            logger.info('Configured InfluxDB client (%s / ctx.%s; base_urls=%r)', resource_name,
                        context_attr, client.base_urls)
