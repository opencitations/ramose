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

from ramose._constants import FORMAT_PARTS_WITH_MEDIA_TYPE, PARAM_NAME
from ramose.cache import ResultCache
from ramose.filters import load_filters_config
from ramose.hash_format import parse_auth, parse_custom_params, parse_disable_params, read_spec_file
from ramose.operation import Operation, OperationConfig

if TYPE_CHECKING:
    import types

    from ramose.filters import FiltersConfig


class APIConfig(TypedDict):
    conf: OrderedDict[str, list[dict[str, str]]]
    conf_json: list[dict[str, str]]
    base_url: str
    tp: str
    update_endpoint: str
    website: str
    engine: str
    sources_map: dict[str, str]
    disable_params: set[str]
    auth_required: bool
    addon: types.ModuleType | None
    sparql_http_method: str
    conf_file: str


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
        addon_path = (Path(conf_file).parent / addon_name).resolve()
        if addon_path.parent.joinpath(f"{addon_path.name}.py").is_file():
            path.append(str(addon_path.parent))
            return import_module(addon_path.name)
        return import_module(addon_name)

    @staticmethod
    def _process_api_metadata(
        conf_json: list[dict[str, str]],
        conf_file: str,
        endpoint_override: str | None,
    ) -> APIConfig:
        item = conf_json[0]
        base_url = item["url"]
        website = item["base"]
        website_parsed = urlsplit(website)
        if not website_parsed.scheme or not website_parsed.netloc:
            msg = "API #base must be an absolute URL"
            raise ValueError(msg)
        tp = endpoint_override or item["endpoint"]
        update_endpoint = endpoint_override or ""
        if not endpoint_override and "update_endpoint" in item:
            update_endpoint = item["update_endpoint"]
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
        auth_required = parse_auth(item["auth"]) if "auth" in item else False
        addon = APIManager._load_addon(item["addon"], conf_file) if "addon" in item else None
        sparql_http_method = item["method"].strip().lower() if "method" in item else "get"

        conf: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
        for op_item in conf_json[1:]:
            conf.setdefault(APIManager.nor_api_url(op_item, base_url), []).append(op_item)

        return {
            "conf": conf,
            "conf_json": conf_json,
            "base_url": base_url,
            "tp": tp or "",
            "update_endpoint": update_endpoint,
            "website": website,
            "engine": engine,
            "sources_map": sources_map,
            "disable_params": disable_params_api,
            "auth_required": auth_required,
            "addon": addon,
            "sparql_http_method": sparql_http_method,
            "conf_file": conf_file,
        }

    def __init__(  # noqa: PLR0913
        self,
        conf_files: list[str],
        endpoint_override: str | None = None,
        cache_dir: str | None = None,
        cache_ttl: int = 86400,
        retry_attempts: int = 3,
        retry_wait: float = 0.5,
        retry_backoff: float = 2.0,
    ) -> None:
        """This is the constructor of the APIManager class. It takes in input a list of API configuration files, each
        defined according to the Hash Format or YAML mirror format, and stores all the operations defined within a
        dictionary. Optionally, an endpoint_override parameter can be provided to override the SPARQL endpoint defined
        in the configuration files (useful for staging/production environments).
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
        as value of this key is the transformation of the related operation defined in the input spec file into a
        dictionary.

        In addition, it also defines additional structure, such as the functions to be used for interpreting the
        values returned by a SPARQL query, some operations that can be used for filtering the results, and the
        HTTP methods to call for making the request to the SPARQL endpoint specified in the configuration file."""
        APIManager.__max_size_csv()

        self._cache = ResultCache(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl
        self._config_cache: dict[str, FiltersConfig] = {}
        self._retry_attempts = retry_attempts
        self._retry_wait = retry_wait
        self._retry_backoff = retry_backoff

        self.all_conf: OrderedDict[str, APIConfig] = OrderedDict()
        self.base_url: list[str] = []
        for conf_file in conf_files:
            conf_json = read_spec_file(conf_file)
            if not conf_json:
                continue
            api_conf = APIManager._process_api_metadata(conf_json, conf_file, endpoint_override)
            self.base_url.append(api_conf["base_url"])
            self.all_conf[api_conf["base_url"]] = api_conf

        self._operation_prefixes = APIManager._build_operation_prefixes(self.all_conf)

    @staticmethod
    def _build_operation_prefixes(
        all_conf: OrderedDict[str, APIConfig],
    ) -> list[tuple[str, str, dict[str, str]]]:
        prefixes: list[tuple[str, str, dict[str, str]]] = []
        for base, api_data in all_conf.items():
            for items in api_data["conf"].values():
                for item in items:
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

    def best_match(self, u: str, method: str = "get") -> tuple[APIConfig | None, str | None, dict[str, str] | None]:
        """This method takes an URL of an API call and the HTTP method in input and finds the API operation URL,
        the related configuration and the operation matching the requested method that best match with the API
        call, if any. When the path matches but no operation declares the requested method, the first operation
        for that path is returned so that the 405 check can reject it."""
        cur_u = sub(r"\?.*$", "", u)
        requested = method.lower()
        for base_url in self.all_conf:
            if u.startswith(base_url):
                conf = self.all_conf[base_url]
                for pat, items in conf["conf"].items():
                    if match(f"^{pat}$", cur_u):
                        for op_item in items:
                            if requested in op_item["method"].split():
                                return conf, pat, op_item
                        return conf, pat, items[0]
        return None, None, None

    @staticmethod
    def _parse_format_map(op_conf: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
        op_format_map: dict[str, str] = {}
        op_media_types: dict[str, str] = {}
        if "format" not in op_conf:
            return op_format_map, op_media_types
        fm_val = op_conf["format"]
        fm_list = fm_val if isinstance(fm_val, list) else [fm_val]
        for fm in fm_list:
            for raw_part in fm.split(";"):
                part = raw_part.strip()
                if not part:
                    continue
                fields = [field.strip() for field in part.split(",")]
                op_format_map[fields[0]] = fields[1]
                if len(fields) >= FORMAT_PARTS_WITH_MEDIA_TYPE and fields[2]:
                    op_media_types[fields[0]] = fields[2]
        return op_format_map, op_media_types

    def _retry_config_for_operation(self, op_conf: dict[str, str]) -> tuple[int, float, float]:
        retry_attempts = int(op_conf["retry_attempts"]) if "retry_attempts" in op_conf else self._retry_attempts
        retry_wait = float(op_conf["retry_wait"]) if "retry_wait" in op_conf else self._retry_wait
        retry_backoff = float(op_conf["retry_backoff"]) if "retry_backoff" in op_conf else self._retry_backoff
        return retry_attempts, retry_wait, retry_backoff

    def _resolve_custom_param_configs(
        self, conf: APIConfig, custom_params_map: dict[str, dict[str, str]]
    ) -> dict[str, FiltersConfig]:
        result: dict[str, FiltersConfig] = {}
        for name, param_conf in custom_params_map.items():
            handler = param_conf["handler"]
            if param_conf["phase"] != "preprocess" or not handler.endswith((".yaml", ".yml")):
                continue
            resolved = str((Path(conf["conf_file"]).parent / handler).resolve())
            if resolved not in self._config_cache:
                self._config_cache[resolved] = load_filters_config(resolved)
            result[name] = self._config_cache[resolved]
        return result

    def get_op(self, op_complete_url: str, method: str = "get") -> Operation | tuple[int, str, str]:
        """This method returns a new object of type Operation which represent the operation specified by
        the input URL (parameter 'op_complete_url)' and the HTTP method. In case no operation can be found
        according by checking the configuration files available in the APIManager, a tuple with an HTTP error
        code and a message is returned instead."""
        url_parsed = urlsplit(op_complete_url)
        op_url = url_parsed.path

        conf, op, op_conf = self.best_match(op_url, method)
        if conf is not None and op is not None and op_conf is not None:
            op_engine = conf["engine"]
            if "engine" in op_conf:
                op_engine = op_conf["engine"].strip().lower()

            custom_params_map = parse_custom_params(op_conf["custom_params"]) if "custom_params" in op_conf else {}

            api_disabled = conf["disable_params"]
            op_disabled = parse_disable_params(op_conf["disable_params"]) if "disable_params" in op_conf else set()
            effective_disabled = api_disabled | op_disabled

            requires_auth = parse_auth(op_conf["auth"]) if "auth" in op_conf else conf["auth_required"]

            op_format_map, op_format_media_types = APIManager._parse_format_map(op_conf)
            retry_attempts, retry_wait, retry_backoff = self._retry_config_for_operation(op_conf)
            config = OperationConfig(
                sparql_endpoint=conf["tp"],
                update_endpoint=conf["update_endpoint"],
                sparql_http_method=conf["sparql_http_method"],
                addon=conf["addon"],
                format_map=op_format_map,
                format_media_types=op_format_media_types,
                sources_map=conf["sources_map"],
                engine=op_engine,
                custom_params=custom_params_map,
                disabled_params=effective_disabled,
                requires_auth=requires_auth,
                cache=self._cache,
                default_cache_ttl=self._cache_ttl,
                custom_param_configs=self._resolve_custom_param_configs(conf, custom_params_map),
                public_base_url=conf["website"],
                retry_attempts=retry_attempts,
                retry_wait=retry_wait,
                retry_backoff=retry_backoff,
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
