# SPDX-FileCopyrightText: 2018-2021 essepuntato <essepuntato@gmail.com>
# SPDX-FileCopyrightText: 2020-2021 marilena <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 dbrembilla <davide.brembilla98@gmail.com>
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivanhb.ita@gmail.com>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from abc import abstractmethod


class DocumentationHandler(object):
    def __init__(self, api_manager):
        """This class provides the main structure for returning a human-readable documentation of all
        the operations described in the configuration files handled by the APIManager specified as input."""
        self.conf_doc = api_manager.all_conf

    @abstractmethod
    def get_documentation(self, *args, **dargs) -> tuple[int, str]:
        """An abstract method that returns a string defining the human-readable documentation of the operations
        available in the input APIManager."""
        pass  # pragma: no cover

    @abstractmethod
    def store_documentation(self, file_path, *args, **dargs) -> None:
        """An abstract method that store in the input file path (parameter 'file_path') the human-readable
        documentation of the operations available in the input APIManager."""
        pass  # pragma: no cover

    @abstractmethod
    def get_index(self, *args, **dargs) -> str:
        """An abstract method that returns a string defining the index of all the various configuration files
        handled by the input APIManager."""
        pass  # pragma: no cover
