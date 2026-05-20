"""Command-line utility"""

import argparse
import sys

from audera.cli import commands


# Define audera CLI tool function(s)
def main():
    """
    usage: audera [-h] {run} ...

    CLI application for running `audera` services.

    options:
    -h, --help  show this help message and exit

    commands:
    The `audera` command options.

    {run}
        run       Runs an `audera` service.

    Execute `audera {command} --help` for more help.
    """

    # Setup CLI argument option(s)
    _ARG_PARSER = argparse.ArgumentParser(
        prog='audera',
        description='CLI application for running `audera` services.',
        epilog='Execute `audera {command} --help` for more help.',
    )

    # Setup command argument option(s)
    _ARG_SUBPARSER = _ARG_PARSER.add_subparsers(title='commands', prog='audera', description='The `audera` command options.')

    # Setup `run` command CLI argument option(s)
    _RUN_ARG_PARSER = _ARG_SUBPARSER.add_parser(
        name='run', help='Runs an `audera` service.', epilog='Execute `audera run --help` for help.'
    )
    _RUN_ARG_PARSER.add_argument(
        'type_', help='The type of `audera` service.', type=str, choices=['streamer-server', 'player-server', 'player-setup']
    )
    _RUN_ARG_PARSER.set_defaults(func=commands.run)

    # Setup `conf` command CLI argument option(s)
    _CONF_ARG_PARSER = _ARG_SUBPARSER.add_parser(
        name='conf', help='Prints a bundled config file to stdout.', epilog='Execute `audera conf --help` for help.'
    )
    _CONF_ARG_PARSER.add_argument('role', help='The audera device role.', type=str, choices=['streamer', 'player'])
    _CONF_ARG_PARSER.add_argument('filename', help='The config file name.', type=str)
    _CONF_ARG_PARSER.set_defaults(func=commands.conf)

    # Parse arguments
    _ARGS = _ARG_PARSER.parse_args()
    _KWARGS = {key: vars(_ARGS)[key] for key in vars(_ARGS).keys() if key != 'func'}

    # Execute sub-command
    _ARGS.func(**_KWARGS)


if __name__ == '__main__':
    sys.exit(main())
