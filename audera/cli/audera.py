"""Command-line utility"""

import argparse
import sys

from audera.cli import commands


def main():
    """
    usage: audera [-h] {streamer,player} ...

    CLI application for running `audera` services.

    options:
    -h, --help  show this help message and exit

    subjects:
    {streamer,player}
        streamer  Manage the audera streamer.
        player    Manage the audera player.

    Execute `audera {subject} --help` for more help.
    """

    _ARG_PARSER = argparse.ArgumentParser(
        prog='audera',
        description='CLI application for running `audera` services.',
        epilog='Execute `audera {subject} --help` for more help.',
    )

    _SUBJECT_SUBPARSER = _ARG_PARSER.add_subparsers(
        title='subjects',
        prog='audera',
        description='The `audera` subject options.',
        dest='subject',
    )
    _SUBJECT_SUBPARSER.required = True

    # streamer subject
    _STREAMER_PARSER = _SUBJECT_SUBPARSER.add_parser(
        name='streamer',
        help='Manage the audera streamer.',
        epilog='Execute `audera streamer --help` for help.',
    )
    _STREAMER_VERB_SUBPARSER = _STREAMER_PARSER.add_subparsers(
        title='verbs',
        prog='audera streamer',
        description='The `audera streamer` verb options.',
        dest='verb',
    )
    _STREAMER_VERB_SUBPARSER.required = True

    _STREAMER_START_PARSER = _STREAMER_VERB_SUBPARSER.add_parser(
        name='start',
        help='Start the audera streamer service.',
        epilog='Execute `audera streamer start --help` for help.',
    )
    _STREAMER_START_PARSER.set_defaults(func=commands.streamer_start)

    _STREAMER_CONF_PARSER = _STREAMER_VERB_SUBPARSER.add_parser(
        name='conf',
        help='Print a bundled streamer config file to stdout.',
        epilog='Execute `audera streamer conf --help` for help.',
    )
    _STREAMER_CONF_PARSER.add_argument('filename', help='The config file name.', type=str)
    _STREAMER_CONF_PARSER.add_argument(
        '--playback-format',
        choices=['S16LE', 'S32LE'],
        default='S32LE',
        help='CamillaDSP playback device format (camilladsp.yml only).',
    )
    _STREAMER_CONF_PARSER.set_defaults(func=commands.streamer_conf)

    _STREAMER_UNITS_PARSER = _STREAMER_VERB_SUBPARSER.add_parser(
        name='units',
        help="Print the audio sources' systemd units to stdout, one per line.",
        epilog='Execute `audera streamer units --help` for help.',
    )
    # One destination, so the two flags cannot disagree and neither can be omitted. Required
    # because provisioning enables one list and disables the other, and a bare `units` silently
    # meaning one of them would make the wrong call look right.
    _STREAMER_UNITS_SELECTION = _STREAMER_UNITS_PARSER.add_mutually_exclusive_group(required=True)
    _STREAMER_UNITS_SELECTION.add_argument(
        '--enabled',
        dest='disabled',
        action='store_false',
        help="The enabled audio sources' units.",
    )
    _STREAMER_UNITS_SELECTION.add_argument(
        '--disabled',
        dest='disabled',
        action='store_true',
        help="Every other catalogued audio source's units.",
    )
    _STREAMER_UNITS_PARSER.set_defaults(func=commands.streamer_units)

    # player subject
    _PLAYER_PARSER = _SUBJECT_SUBPARSER.add_parser(
        name='player',
        help='Manage the audera player.',
        epilog='Execute `audera player --help` for help.',
    )
    _PLAYER_VERB_SUBPARSER = _PLAYER_PARSER.add_subparsers(
        title='verbs',
        prog='audera player',
        description='The `audera player` verb options.',
        dest='verb',
    )
    _PLAYER_VERB_SUBPARSER.required = True

    _PLAYER_START_PARSER = _PLAYER_VERB_SUBPARSER.add_parser(
        name='start',
        help='Start the audera player service.',
        epilog='Execute `audera player start --help` for help.',
    )
    _PLAYER_START_PARSER.set_defaults(func=commands.player_start)

    _PLAYER_CONF_PARSER = _PLAYER_VERB_SUBPARSER.add_parser(
        name='conf',
        help='Print a bundled player config file to stdout.',
        epilog='Execute `audera player conf --help` for help.',
    )
    _PLAYER_CONF_PARSER.add_argument('filename', help='The config file name.', type=str)
    _PLAYER_CONF_PARSER.add_argument(
        '--playback-format',
        choices=['S16LE', 'S32LE'],
        default='S32LE',
        help='CamillaDSP playback device format (camilladsp.yml only).',
    )
    _PLAYER_CONF_PARSER.set_defaults(func=commands.player_conf)

    _ARGS = _ARG_PARSER.parse_args()
    _KWARGS = {key: value for key, value in vars(_ARGS).items() if key not in ('func', 'subject', 'verb')}

    _ARGS.func(**_KWARGS)


if __name__ == '__main__':
    sys.exit(main())
