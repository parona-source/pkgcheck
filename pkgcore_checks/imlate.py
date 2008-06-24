# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.restrictions import packages, values
from pkgcore_checks import base, addons


class LaggingStableInfo(base.Result):

    """Arch that is behind another from a stabling standpoint"""

    __slots__ = ("category", "package", "version", "keywords",
        "stable")
    threshold = base.versioned_feed

    def __init__(self, pkg, keywords):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.keywords = keywords
        self.stable = tuple(str(x) for x in pkg.keywords
            if not x[0] in ("~", "-"))

    @property
    def short_desc(self):
        return "stabled arches [ %s ], potentials [ %s ]" % \
            (', '.join(self.stable), ', '.join(self.keywords))


class ImlateReport(base.Template):

    """
    scan for ebuilds that can be stabled based upon stabling status for
    other arches
    """

    feed_type = base.package_feed
    required_addons = (addons.ArchesAddon,)
    known_results = (LaggingStableInfo,)

    @staticmethod
    def mangle_option_parser(parser):
        parser.add_option(
            "--source-arches", action='callback', dest='reference_arches',
            default=addons.ArchesAddon.default_arches,
            type='string', callback=addons.ArchesAddon._record_arches,
            help="comma seperated list of what arches to compare against for "
            "imlate, defaults to %s" % (
                ",".join(addons.ArchesAddon.default_arches),))

    def __init__(self, options, arches):
        base.Template.__init__(self, options)
        arches = frozenset(x.strip().lstrip("~") for x in options.arches)
        self.target_arches = frozenset("~%s" % x.strip().lstrip("~")
            for x in arches)
        self.source_arches = frozenset(x.lstrip("~")
            for x in options.reference_arches)
        self.source_filter = packages.PackageRestriction("keywords",
            values.ContainmentMatch(*self.source_arches))

    def feed(self, pkgset, reporter):
        fmatch = self.source_filter.match
        remaining = set(self.target_arches)
        for pkg in reversed(pkgset):
            if not fmatch(pkg):
                continue
            unstable_keys = remaining.intersection(pkg.keywords)
            if unstable_keys:
                reporter.add_report(LaggingStableInfo(pkg,
                    sorted(unstable_keys)))
                remaining.difference_update(unstable_keys)
                if not remaining:
                    break
