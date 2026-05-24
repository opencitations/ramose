# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ramose.api_manager import APIManager


class DocumentationHandler:
    def __init__(self, api_manager: APIManager) -> None:
        """This class provides the main structure for returning a human-readable documentation of all
        the operations described in the configuration files handled by the APIManager specified as input."""
        self.conf_doc = api_manager.all_conf

    @abstractmethod
    def get_documentation(self, *args: str | None, **dargs: str | None) -> tuple[int, str]:
        """An abstract method that returns a string defining the human-readable documentation of the operations
        available in the input APIManager."""
        # pragma: no cover

    @abstractmethod
    def store_documentation(self, file_path: str, *args: str | None, **dargs: str | None) -> None:
        """An abstract method that store in the input file path (parameter 'file_path') the human-readable
        documentation of the operations available in the input APIManager."""
        # pragma: no cover

    @abstractmethod
    def get_index(self, *args: str | None, **dargs: str | None) -> str:
        """An abstract method that returns a string defining the index of all the various configuration files
        handled by the input APIManager."""
        # pragma: no cover
