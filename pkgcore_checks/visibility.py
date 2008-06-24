# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from snakeoil.compatibility import any
from pkgcore_checks import base, addons
from snakeoil.iterables import caching_iter
from snakeoil.lists import stable_unique, iflatten_instance
from pkgcore.ebuild.atom import atom
from snakeoil.demandload import demandload
demandload(globals(), "snakeoil.xml:escape")


class VisibleVcsPkg(base.Result):
    """pkg is vcs based, but visible"""

    __slots__ = ("category", "package", "version", "profile", "arch")

    threshold = base.versioned_feed

    def __init__(self, pkg, arch, profile):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.arch = arch.lstrip("~")
        self.profile = profile

    @property
    def short_desc(self):
        return "VCS version visible for arch %s, profile %s" % (
            self.arch, self.profile)


class NonExistantDeps(base.Result):
    """No matches exist for a depset element"""

    __slots__ = ("category", "package", "version", "attr", "atoms")

    threshold = base.versioned_feed

    def __init__(self, pkg, attr, nonexistant_atoms):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.attr = attr
        self.atoms = tuple(str(x) for x in nonexistant_atoms)

    @property
    def short_desc(self):
        return "depset %s: nonexistant atoms [ %s ]" % (
            self.attr, ', '.join(self.atoms))


class NonsolvableDeps(base.Result):
    """No potential solution for a depset attribute"""

    __slots__ = ("category", "package", "version", "attr", "profile",
        "keyword", "potentials")

    threshold = base.versioned_feed

    def __init__(self, pkg, attr, keyword, profile, horked):
        base.Result.__init__(self)
        self._store_cpv(pkg)
        self.attr = attr
        self.profile = profile
        self.keyword = keyword
        self.potentials = tuple(str(x) for x in stable_unique(horked))

    @property
    def short_desc(self):
        return "nonsolvable depset(%s) keyword(%s) profile (%s): " \
            "solutions: [ %s ]" % (self.attr, self.keyword, self.profile,
            ', '.join(self.potentials))


class VisibilityReport(base.Template):

    """Visibility dependency scans.
    Check that at least one solution is possible for a pkg, checking all
    profiles (defined by arch.list) visibility modifiers per stable/unstable
    keyword
    """

    feed_type = base.versioned_feed
    required_addons = (
        addons.ArchesAddon, addons.QueryCacheAddon, addons.ProfileAddon,
        addons.EvaluateDepSetAddon)
    known_results = (VisibleVcsPkg, NonExistantDeps, NonsolvableDeps)

    vcs_eclasses = frozenset(["subversion", "git", "cvs", "darcs"])

    def __init__(self, options, arches, query_cache, profiles, depset_cache):
        base.Template.__init__(self, options)
        self.query_cache = query_cache.query_cache
        self.depset_cache = depset_cache
        self.profiles = profiles
        self.arches = frozenset(x.lstrip("~") for x in options.arches)

    def feed(self, pkg, reporter):
        # query_cache gets caching_iter partial repo searches shoved into it-
        # reason is simple, it's likely that versions of this pkg probably
        # use similar deps- so we're forcing those packages that were
        # accessed for atom matching to remain in memory.
        # end result is less going to disk

        fvcs = self.vcs_eclasses
        for eclass in pkg.data["_eclasses_"]:
            if eclass in fvcs:
                # vcs ebuild that better not be visible
                self.check_visibility_vcs(pkg, reporter)
                break

        for attr, depset in (("depends", pkg.depends),
            ("rdepends", pkg.rdepends), ("post_rdepends", pkg.post_rdepends)):
            nonexistant = set()
            for node in iflatten_instance(depset, atom):

                h = str(node)
                if h not in self.query_cache:
                    if h in self.profiles.global_insoluable:
                        nonexistant.add(node)
                        # insert an empty tuple, so that tight loops further
                        # on don't have to use the slower get method
                        self.query_cache[h] = ()

                    else:
                        matches = caching_iter(
                            self.options.search_repo.itermatch(node))
                        if matches:
                            self.query_cache[h] = matches
                        elif not node.blocks and not node.category == "virtual":
                            nonexistant.add(node)
                            self.query_cache[h] = ()
                            self.profiles.global_insoluable.add(h)
                elif not self.query_cache[h]:
                    nonexistant.add(node)

            if nonexistant:
                reporter.add_report(NonExistantDeps(pkg, attr, nonexistant))

        del nonexistant

        for attr, depset in (("depends", pkg.depends),
            ("rdepends", pkg.rdepends), ("post_rdepends", pkg.post_rdepends)):

            for edepset, profiles in self.depset_cache.collapse_evaluate_depset(
                pkg, attr, depset):

                self.process_depset(pkg, attr, edepset, profiles, reporter)

    def check_visibility_vcs(self, pkg, reporter):
        for key, profiles in self.profiles.profile_filters.iteritems():
            if key.startswith("~") or key.startswith("-"):
                continue
            for profile in profiles:
                if profile.visible(pkg):
                    reporter.add_report(VisibleVcsPkg(pkg,
                        profile.key, profile.name))

    def process_depset(self, pkg, attr, depset, profiles, reporter):
        csolutions = depset.cnf_solutions()

        for profile in profiles:
            failures = set()
            # is it visible?  ie, is it masked?
            # if so, skip it.
            # long term, probably should do testing in the same respect we do
            # for other visibility tiers
            cache = profile.cache
            provided = profile.provides_repo.match
            is_virtual = profile.virtuals.match
            insoluable = profile.insoluable
            visible = profile.visible
            for required in csolutions:
                if any(True for a in required if a.blocks):
                    continue
                for a in required:
                    h = str(a)
                    if h in insoluable:
                        pass
                    elif h in cache:
                        break
                    elif provided(a):
                        break
                    elif is_virtual(a):
                        cache.add(h)
                        break
                    elif a.category == "virtual" and h not in self.query_cache:
                        insoluable.add(h)
                    else:
                        if any(True for pkg in self.query_cache[h] if
                            visible(pkg)):
                            cache.add(h)
                            break
                        else:
                            insoluable.add(h)
                else:
                    # no matches.  not great, should collect them all
                    failures.update(required)
            if failures:
                reporter.add_report(NonsolvableDeps(pkg, attr, profile.key,
                    profile.name, list(failures)))
