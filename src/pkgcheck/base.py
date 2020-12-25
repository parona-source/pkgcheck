"""Core classes and interfaces.

This defines a couple of standard feed types and scopes. Currently
feed types are strings and scopes are integers, but you should use the
symbolic names wherever possible (everywhere except for adding a new
feed type) since this might change in the future. Scopes are integers,
but do not rely on that either.

Feed types have to match exactly. Scopes are ordered: they define a
minimally accepted scope.
"""

import re
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial, total_ordering

from pkgcore.restrictions import values
from snakeoil.cli.exceptions import UserException
from snakeoil.mappings import ImmutableDict


@total_ordering
@dataclass(frozen=True)
class Scope:
    """Generic scope for scans, checks, and results."""
    desc: str
    level: int

    def __str__(self):
        return self.desc

    def __lt__(self, other):
        if isinstance(other, Scope):
            return self.level < other.level
        return self.level < other

    def __eq__(self, other):
        if isinstance(other, Scope):
            return self.level == other.level
        return self.level == other

    def __hash__(self):
        return hash(self.desc)

    def __repr__(self):
        address = '@%#8x' % (id(self),)
        return f'<{self.__class__.__name__} desc={self.desc!r} {address}>'


# pkg-related scope levels
repo_scope = Scope('repo', 1)
category_scope = Scope('category', 2)
package_scope = Scope('package', 3)
version_scope = Scope('version', 4)

# Special scope levels, scopes with negative levels are only enabled under
# certain circumstances while location specific scopes have a level of 0.
commit_scope = Scope('commit', -1)
profiles_scope = Scope('profiles', 0)
eclass_scope = Scope('eclass', 0)

# mapping for -S/--scopes option, ordered for sorted output in the case of unknown scopes
scopes = ImmutableDict({
    'git': commit_scope,
    'profiles': profiles_scope,
    'eclass': eclass_scope,
    'repo': repo_scope,
    'cat': category_scope,
    'pkg': package_scope,
    'ver': version_scope,
})


class PkgcheckException(Exception):
    """Generic pkgcheck exception."""


class PkgcheckUserException(PkgcheckException, UserException):
    """Generic pkgcheck exception for user-facing cli output.."""


class Addon:
    """Base class for extra functionality for pkgcheck other than a check.

    The checkers can depend on one or more of these. They will get
    called at various points where they can extend pkgcheck (if any
    active checks depend on the addon).

    These methods are not part of the checker interface because that
    would mean addon functionality shared by checkers would run twice.
    They are not plugins because they do not do anything useful if no
    checker depending on them is active.

    This interface is not finished. Expect it to grow more methods
    (but if not overridden they will be no-ops).

    :cvar required_addons: sequence of addon dependencies
    """

    required_addons = ()

    def __init__(self, options, **kwargs):
        """Initialize.

        An instance of every addon in required_addons is passed as extra arg.

        :param options: the argparse values.
        """
        self.options = options

    @staticmethod
    def mangle_argparser(parser):
        """Add extra options and/or groups to the argparser.

        This hook is always triggered, even if the checker is not
        activated (because it runs before the commandline is parsed).

        :param parser: an C{argparse.ArgumentParser} instance.
        """

    def __hash__(self):
        return hash(self.__class__)

    def __eq__(self, other):
        return self.__class__ == other.__class__


def get_addons(objects):
    """Return tuple of addons for a given sequence of objects."""
    addons = {}

    def _addons(objs):
        """Recursively determine addons that are requested."""
        for addon in objs:
            if addon not in addons:
                if addon.required_addons:
                    _addons(addon.required_addons)
                addons[addon] = None

    _addons(objects)
    return tuple(addons)


def param_name(cls):
    """Restructure class names for injected parameters.

    For example, GitAddon -> git_addon and GitCache -> git_cache.
    """
    return re.sub(r'([a-z])([A-Z])', r'\1_\2', cls.__name__).lower()


def contains(obj_set, obj):
    """Stub method for matching objects against a given set.

    Used to create pickleable scanning restrictions.
    """
    return obj in obj_set


def contains_restriction(objs):
    """Generate a restriction for a given iterable of hashable objects."""
    func = partial(contains, frozenset(objs))
    return values.AnyMatch(values.FunctionRestriction(func))


class ProgressManager(AbstractContextManager):
    """Context manager for handling progressive output.

    Useful for updating the user about the status of a long running process.
    """

    def __init__(self, verbosity=0):
        self.verbosity = verbosity
        self._cached = None

    def _progress_callback(self, s):
        """Callback used for progressive output."""
        # avoid rewriting the same output
        if s != self._cached:
            sys.stderr.write(f'{s}\r')
            self._cached = s

    def __enter__(self):
        if self.verbosity >= 0 and sys.stdout.isatty():
            return self._progress_callback
        return lambda x: None

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if self._cached is not None:
            sys.stderr.write('\n')
