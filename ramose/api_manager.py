# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import csv
from collections import OrderedDict
from importlib import import_module
from pathlib import Path
from re import findall, match, sub
from sys import maxsize, path
from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlsplit

from ramose._constants import PARAM_NAME
from ramose.cache import ResultCache
from ramose.hash_format import HashFormatHandler, parse_custom_params, parse_disable_params
from ramose.operation import Operation, OperationConfig

if TYPE_CHECKING:
    import types


class APIConfig(TypedDict):
    conf: OrderedDict[str, dict[str, str]]
    conf_json: list[dict[str, str]]
    base_url: str
    tp: str
    website: str
    engine: str
    sources_map: dict[str, str]
    disable_params: set[str]
    addon: types.ModuleType | None
    sparql_http_method: str


class APIManager:
    # Fixing max size for CSV
    @staticmethod
    def __max_size_csv() -> None:
        max_int = maxsize
        while True:
            try:
                csv.field_size_limit(max_int)
                break
            except OverflowError:  # pragma: no cover
                max_int = int(max_int / 10)

    @staticmethod
    def _load_addon(addon_name: str, conf_file: str) -> types.ModuleType:
        if "." in addon_name:
            return import_module(addon_name)
        addon_path = (Path(conf_file).parent / addon_name).resolve()
        path.append(str(addon_path.parent))
        return import_module(addon_path.name)

    @staticmethod
    def _process_api_metadata(
        item: dict[str, str],
        conf_file: str,
        endpoint_override: str | None,
    ) -> tuple[str, str, str, types.ModuleType | None, str, dict[str, str], str, set[str]]:
        base_url = item["url"]
        website = item["base"]
        tp = endpoint_override or item["endpoint"]
        engine = item["engine"].strip().lower() if "engine" in item else "sparql"
        sources_map: dict[str, str] = {}
        if "sources" in item:
            for raw_pair in item["sources"].split(";"):
                pair = raw_pair.strip()
                if not pair:
                    continue
                name, url = pair.split("=", 1)
                sources_map[name.strip()] = url.strip()
        disable_params_api = parse_disable_params(item["disable_params"]) if "disable_params" in item else set()
        addon = APIManager._load_addon(item["addon"], conf_file) if "addon" in item else None
        sparql_http_method = item["method"].strip().lower() if "method" in item else "get"
        return base_url, tp, website, addon, sparql_http_method, sources_map, engine, disable_params_api

    def __init__(
        self,
        conf_files: list[str],
        endpoint_override: str | None = None,
        cache_dir: str | None = None,
        cache_ttl: int = 86400,
    ) -> None:
        """This is the constructor of the APIManager class. It takes in input a list of API configuration files, each
        defined according to the Hash Format and following a particular structure, and stores all the operations
        defined within a dictionary. Optionally, an endpoint_override parameter can be provided to override the
        SPARQL endpoint defined in the configuration files (useful for staging/production environments).
        The structure of each item in the dictionary of the operations is defined as follows:

        {
            "/api/v1/references/(.+)": {
                "sparql": "PREFIX ...",
                "method": "get",
                ...
            },
            ...
        }

        In particular, each key in the dictionary identifies the full URL of a particular API operation, and it is
        used so as to understand with operation should be called once an API call is done. The object associated
        as value of this key is the transformation of the related operation defined in the input Hash Format file
        into a dictionary.

        In addition, it also defines additional structure, such as the functions to be used for interpreting the
        values returned by a SPARQL query, some operations that can be used for filtering the results, and the
        HTTP methods to call for making the request to the SPARQL endpoint specified in the configuration file."""
        APIManager.__max_size_csv()

        self._cache = ResultCache(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl

        self.all_conf: OrderedDict[str, APIConfig] = OrderedDict()
        self.base_url: list[str] = []
        for conf_file in conf_files:
            conf: OrderedDict[str, dict[str, str]] = OrderedDict()
            conf_json = HashFormatHandler().read(conf_file)
            if not conf_json:
                continue
            base_url, tp, website, addon, sparql_http_method, sources_map, engine, disable_params_api = (
                APIManager._process_api_metadata(conf_json[0], conf_file, endpoint_override)
            )
            self.base_url.append(base_url)
            for item in conf_json[1:]:
                conf[APIManager.nor_api_url(item, base_url)] = item

            self.all_conf[base_url] = {
                "conf": conf,
                "tp": tp or "",
                "conf_json": conf_json,
                "base_url": base_url,
                "website": website,
                "addon": addon,
                "sparql_http_method": sparql_http_method,
                "sources_map": sources_map,
                "engine": engine,
                "disable_params": disable_params_api,
            }

        self._operation_prefixes = APIManager._build_operation_prefixes(self.all_conf)

    @staticmethod
    def _build_operation_prefixes(
        all_conf: OrderedDict[str, APIConfig],
    ) -> list[tuple[str, str, dict[str, str]]]:
        prefixes: list[tuple[str, str, dict[str, str]]] = []
        for base, api_data in all_conf.items():
            for item in api_data["conf"].values():
                template = item["url"]
                brace_pos = template.find("{")
                if brace_pos != -1:
                    prefixes.append((base + template[:brace_pos], base, item))
        prefixes.sort(key=lambda entry: len(entry[0]), reverse=True)
        return prefixes

    @staticmethod
    def nor_api_url(i: dict[str, str], b: str = "") -> str:
        """This method takes an API operation object and an optional base URL (e.g. "/api/v1") as input
        and returns the URL composed by the base URL plus the API URL normalised according to specific rules. In
        particular, these normalisation rules takes the operation URL (e.g. "#url /citations/{oci}") and the
        specification of the shape of all the parameters between brackets in the URL (e.g. "#oci str([0-9]+-[0-9]+)"),
        and returns a new operation URL where the parameters have been substituted with the regular expressions
        defining them (e.g. "/citations/([0-9]+-[0-9]+)"). This URL will be used by RAMOSE for matching the
        particular API calls with the specific operation to execute."""
        result = i["url"]

        for term in findall(PARAM_NAME, result):
            try:
                t = i[term]
            except KeyError:
                t = "str(.+)"
            result = result.replace(f"{{{term}}}", "{}".format(sub(r"^[^\(]+(\(.+\))$", r"\1", t)))

        return f"{b}{result}"

    def best_match(self, u: str) -> tuple[APIConfig | None, str | None]:
        """This method takes an URL of an API call in input and find the API operation URL and the related
        configuration that best match with the API call, if any."""
        cur_u = sub(r"\?.*$", "", u)
        for base_url in self.all_conf:
            if u.startswith(base_url):
                conf = self.all_conf[base_url]
                for pat in conf["conf"]:
                    if match(f"^{pat}$", cur_u):
                        return conf, pat
        return None, None

    @staticmethod
    def _parse_format_map(op_conf: dict[str, str]) -> dict[str, str]:
        op_format_map: dict[str, str] = {}
        if "format" not in op_conf:
            return op_format_map
        fm_val = op_conf["format"]
        fm_list = fm_val if isinstance(fm_val, list) else [fm_val]
        for fm in fm_list:
            for raw_part in fm.split(";"):
                part = raw_part.strip()
                if not part:
                    continue
                fields = part.split(",")
                op_format_map[fields[0].strip()] = fields[1].strip()
        return op_format_map

    def get_op(self, op_complete_url: str) -> Operation | tuple[int, str, str]:
        """This method returns a new object of type Operation which represent the operation specified by
        the input URL (parameter 'op_complete_url)'. In case no operation can be found according by checking
        the configuration files available in the APIManager, a tuple with an HTTP error code and a message
        is returned instead."""
        url_parsed = urlsplit(op_complete_url)
        op_url = url_parsed.path

        conf, op = self.best_match(op_url)
        if conf is not None and op is not None:
            op_conf = conf["conf"][op]
            op_engine = conf.get("engine", "sparql")
            if "engine" in op_conf:
                op_engine = op_conf["engine"].strip().lower()

            custom_params_map = parse_custom_params(op_conf["custom_params"]) if "custom_params" in op_conf else {}

            api_disabled = conf["disable_params"]
            op_disabled = parse_disable_params(op_conf["disable_params"]) if "disable_params" in op_conf else set()
            effective_disabled = api_disabled | op_disabled

            config = OperationConfig(
                sparql_endpoint=conf["tp"],
                sparql_http_method=conf["sparql_http_method"],
                addon=conf["addon"],
                format_map=APIManager._parse_format_map(op_conf),
                sources_map=conf.get("sources_map", {}),
                engine=op_engine,
                custom_params=custom_params_map,
                disabled_params=effective_disabled,
                cache=self._cache,
                default_cache_ttl=self._cache_ttl,
            )
            return Operation(op_complete_url, op, op_conf, config)

        for prefix, base_url, item in self._operation_prefixes:
            if op_url.startswith(prefix):
                template = item["url"]
                full_template = base_url + template
                param_value = op_url[len(prefix) :]
                param_names = findall(PARAM_NAME, template)
                if not param_value:
                    msg = (
                        f"HTTP status code 400: the operation '{full_template}' "
                        f"requires a value for parameter '{param_names[0]}'"
                    )
                else:
                    msg = (
                        f"HTTP status code 400: the value '{param_value}' is not valid for parameter "
                        f"'{param_names[0]}' in operation '{full_template}'"
                    )
                if "call" in item:
                    msg += f". Example: {base_url}{item['call']}"
                return 400, msg, "text/plain"

        return 404, "HTTP status code 404: the operation requested does not exist", "text/plain"
