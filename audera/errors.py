"""Typed exceptions for command failures.

Every write path raises one of these at its translation boundary, so the UI can catch a single
hierarchy and show the right message without inspecting exception types from three libraries.
"""


class CommandError(Exception):
    """A command targeting a service or the local filesystem failed."""


class Unreachable(CommandError):
    """The target service could not be reached."""


class ServiceError(CommandError):
    """The target service rejected the request."""


class StorageError(CommandError):
    """A local file operation failed."""
