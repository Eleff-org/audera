"""UX optionality feature-flag catalog"""

from __future__ import annotations

from dataclasses import dataclass

from audera.models.settings import Settings


@dataclass(frozen=True)
class Option:
    """A `class` that represents a single selectable option for a `Feature`.

    Attributes
    ----------
    value: `str`
        The persisted identifier, stored as `Settings.features[feature.key]`.
    label: `str`
        The button label shown in the Settings tab.
    """

    value: str
    label: str


@dataclass(frozen=True)
class Feature:
    """A `class` that represents a feature with two or more alternate UX options.

    Attributes
    ----------
    key: `str`
        The stable identifier, used as the `Settings.features` dict key.
    label: `str`
        The feature name shown in the Settings tab, e.g. `'Player Selection'`.
    options: `tuple[Option, ...]`
        The available options for the feature. The first option is the default.
    """

    key: str
    label: str
    options: tuple[Option, ...]

    @property
    def default(self) -> Option:
        """Returns the default `Option`, which is always the first registered option."""
        return self.options[0]

    def option(self, value: str) -> Option:
        """Returns the `Option` matching `value`, falling back to the default when unmatched.

        Parameters
        ----------
        value: `str`
            The persisted option value to resolve.
        """
        for opt in self.options:
            if opt.value == value:
                return opt
        return self.default


PLAYER_SELECTION_KEY = 'player_selection'
VOLUME_KEY = 'volume'

FF_DISABLED_VS_MUTE = 'disabled'
FF_VOLUME_PERC_OR_DB = 'db'

FEATURES: list[Feature] = [
    Feature(
        PLAYER_SELECTION_KEY,
        'Player Selection',
        (Option('mute', 'Mute checkbox'), Option('disabled', 'Disabled toggle')),
    ),
    Feature(
        VOLUME_KEY,
        'Volume',
        (Option('percent', 'Percent'), Option('db', 'Decibels')),
    ),
]


def get_feature(key: str) -> Feature:
    """Returns the registered `Feature` for `key`.

    Parameters
    ----------
    key: `str`
        The feature key to look up.

    Raises
    ------
    `KeyError`
        When `key` is not registered in `FEATURES`.
    """
    for feature in FEATURES:
        if feature.key == key:
            return feature
    raise KeyError(key)


def default_selections() -> dict[str, str]:
    """Returns the default option value for every registered feature, keyed by feature key."""
    return {feature.key: feature.default.value for feature in FEATURES}


def selected(settings: Settings, key: str) -> str:
    """Returns the selected option value for `key`, falling back to the feature's default.

    Parameters
    ----------
    settings: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    key: `str`
        The feature key to resolve.
    """
    return settings.features.get(key, get_feature(key).default.value)


def flag_enabled(settings: Settings, key: str, option: str) -> bool:
    """Returns `True` when the selected option for `key` equals `option`.

    Parameters
    ----------
    settings: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    key: `str`
        The feature key to resolve.
    option: `str`
        The option value to compare against the selection.
    """
    return selected(settings, key) == option
