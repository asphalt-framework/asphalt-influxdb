Version history
===============

This library adheres to `Semantic Versioning <http://semver.org/>`_.

**2.0.1**

- Added compatibility with Asphalt 4.0
- Fixed ``DeprecationWarning: ClientSession.close() is not coroutine`` warnings

**2.0.0** (2017-04-11)

- **BACKWARD INCOMPATIBLE** Migrated to Asphalt 3.0
- **BACKWARD INCOMPATIBLE** Migrated to aiohttp 2.0

**1.1.1** (2017-02-09)

- Fixed handling of long responses (on InfluxDB 1.2+)

**1.1.0** (2016-12-15)

- Added the ``KeyedTuple._asdict()`` method
- Fixed wrong quoting of string values (should use single quotes, not double quotes)

**1.0.0** (2016-12-12)

- Initial release
