"""Various command-line specific support."""

import configparser
import sys

from pkgcore.util import commandline
from snakeoil.cli import arghparse
from snakeoil.contexts import patch
from snakeoil.klass import jit_attr_none
from snakeoil.mappings import OrderedSet
from snakeoil.log import suppress_logging

from . import base, const


class Tool(commandline.Tool):
    """Suppress log messages globally."""

    def main(self):
        with suppress_logging():
            try:
                return super().main()
            except base.PkgcheckException as e:
                sys.exit(str(e))


class ConfigArgumentParser(arghparse.ArgumentParser):
    """Argument parser that supports loading settings from specified config files."""

    default_configs = (const.SYSTEM_CONF_FILE, const.USER_CONF_FILE)

    def __init__(self, configs=(), **kwargs):
        super().__init__(**kwargs)
        self.configs = OrderedSet(configs)

    @jit_attr_none
    def config(self):
        return self.parse_config()

    def parse_config(self, configs=()):
        """Parse given config files."""
        configs = configs if configs else self.configs
        config = configparser.ConfigParser()
        try:
            for f in configs:
                config.read(f)
        except configparser.ParsingError as e:
            self.error(f'parsing config file failed: {e}')
        return config

    def parse_config_options(self, namespace=None, section='DEFAULT', configs=()):
        """Parse options from config if they exist."""
        if configs:
            self.configs.update(configs)
            # reset jit attr to force reparse
            self._config = None
        namespace = arghparse.Namespace() if namespace is None else namespace
        config_args = [f'--{k}={v}' if v else f'--{k}' for k, v in self.config.items(section)]
        if config_args:
            with patch('snakeoil.cli.arghparse.ArgumentParser.error', self._config_error):
                namespace, args = self.parse_known_optionals(config_args, namespace)
                if args:
                    self.error(f"unknown arguments: {'  '.join(args)}")
        return namespace

    def _config_error(self, message, status=2):
        """Stub to replace error method that notes config failure."""
        self.exit(status, f'{self.prog}: failed loading config: {message}\n')
