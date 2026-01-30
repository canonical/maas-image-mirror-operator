# simplestreams-maas-mirror

A Juju machine charm that deploys an nginx-based mirror for MAAS simplestreams images.

## Description

This charm automates the setup of a MAAS image mirror by:
- Installing nginx and simplestreams packages
- Configuring nginx to serve mirrored content with directory indexing
- Setting up automated synchronization via cron jobs

## Usage

Deploy the charm:

```bash
juju deploy ./simplestreams-maas-mirror_ubuntu-24.04-amd64.charm
```

### Configuration

The charm provides a `cron-jobs` configuration option to customize the synchronization schedule:

```bash
juju config simplestreams-maas-mirror cron-jobs="0 */2 * * 0 sstream-mirror ..."
```

The default configuration syncs MAAS ephemeral images for amd64 architecture and specific Ubuntu releases (focal, jammy, noble) every 2 hours on Sundays.

## Building

To build the charm:

```bash
charmcraft pack
```

## Contributing

Please ensure all code follows best practices and includes appropriate error handling.

## License

Apache License 2.0
