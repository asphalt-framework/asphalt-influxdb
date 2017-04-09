from pathlib import Path

from setuptools import setup

setup(
    name='asphalt-influxdb',
    use_scm_version={
        'version_scheme': 'post-release',
        'local_scheme': 'dirty-tag'
    },
    description='InfluxDB client component for the Asphalt framework',
    long_description=Path(__file__).with_name('README.rst').read_text('utf-8'),
    author='Alex Grönholm',
    author_email='alex.gronholm@nextday.fi',
    url='https://github.com/asphalt-framework/asphalt-influxdb',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Topic :: Database',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6'
    ],
    license='Apache License 2.0',
    zip_safe=False,
    packages=[
        'asphalt.influxdb'
    ],
    setup_requires=[
        'setuptools_scm >= 1.7.0'
    ],
    install_requires=[
        'asphalt ~= 3.0',
        'aiohttp ~= 2.0',
        'python-dateutil ~= 2.6'
    ],
    extras_require={
        'testing': [
            'pytest',
            'pytest-cov',
            'pytest-catchlog',
            'pytest-asyncio >= 0.5.0'
        ]
    },
    entry_points={
        'asphalt.components': [
            'influxdb = asphalt.influxdb.component:InfluxDBComponent'
        ]
    }
)
