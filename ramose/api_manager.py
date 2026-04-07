# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import csv
from collections import OrderedDict
from importlib import import_module
from pathlib import Path
from re import findall, match, sub
from sys import maxsize, path
from urllib.parse import urlsplit

from ramose._constants import PARAM_NAME
from ramose.hash_format import HashFormatHandler
from ramose.operation import Operation


class APIManager:
    # Fixing max size for CSV
    @staticmethod
    def __max_size_csv():
        max_int = maxsize
        while True:
            try:
                csv.field_size_limit(max_int)
                break
            except OverflowError:  # pragma: no cover
                max_int = int(max_int / 10)

    def __init__(self, conf_files, endpoint_override=None):
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

        self.all_conf = OrderedDict()
        self.base_url = []
        for conf_file in conf_files:
            conf = OrderedDict()
            tp = None
            conf_json = HashFormatHandler().read(conf_file)
            base_url = None
            addon = None
            website = ""
            sparql_http_method = "post"
            sources_map = {}
            allow_inline_endpoints = False
            engine = "sparql"
            for item in conf_json:
                if base_url is None:
                    base_url = item["url"]
                    self.base_url.append(item["url"])
                    website = item["base"]
                    tp = endpoint_override or item["endpoint"]

                    # Engine selection at API level (optional)
                    if "engine" in item:
                        engine = item["engine"].strip().lower()

                    # Optional: named sources registry
                    if "sources" in item:
                        for raw_pair in item["sources"].split(";"):
                            pair = raw_pair.strip()
                            if not pair:
                                continue
                            name, url = pair.split("=", 1)
                            sources_map[name.strip()] = url.strip()

                    # Optional: allow explicit @@endpoint <url> in #sparql
                    if "allow_inline_endpoints" in item:
                        allow_inline_endpoints = str(item["allow_inline_endpoints"]).strip().lower() in (
                            "true",
                            "1",
                            "yes",
                            "y",
                        )

                    if "addon" in item:
                        addon_path = (Path(conf_file).parent / item["addon"]).resolve()
                        path.append(str(addon_path.parent))
                        addon = import_module(addon_path.name)
                    sparql_http_method = "post"
                    if "method" in item:
                        sparql_http_method = item["method"].strip().lower()
                else:
                    conf[APIManager.nor_api_url(item, base_url)] = item

            self.all_conf[base_url] = {
                "conf": conf,
                "tp": tp,
                "conf_json": conf_json,
                "base_url": base_url,
                "website": website,
                "addon": addon,
                "sparql_http_method": sparql_http_method,
                "sources_map": sources_map,
                "allow_inline_endpoints": allow_inline_endpoints,
                "engine": engine,
            }

    @staticmethod
    def nor_api_url(i, b=""):
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

    def best_match(self, u):
        """This method takes an URL of an API call in input and find the API operation URL and the related
        configuration that best match with the API call, if any."""
        cur_u = sub(r"\?.*$", "", u)
        result = None, None
        for base_url in self.all_conf:
            if u.startswith(base_url):
                conf = self.all_conf[base_url]
                for pat in conf["conf"]:
                    if match(f"^{pat}$", cur_u):
                        result = conf, pat
                        break
        return result

    def get_op(self, op_complete_url):
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

            # Build op-level format map from the operation block
            op_format_map = {}
            if "format" in op_conf:
                fm_val = op_conf["format"]
                fm_list = fm_val if isinstance(fm_val, list) else [fm_val]
                for fm in fm_list:
                    for raw_part in fm.split(";"):
                        part = raw_part.strip()
                        if not part:
                            continue
                        fmt, func = part.split(",", 1)
                        op_format_map[fmt.strip()] = func.strip()

            return Operation(
                op_complete_url,
                op,
                op_conf,
                conf["tp"],
                conf["sparql_http_method"],
                conf["addon"],
                op_format_map,
                conf.get("sources_map", {}),
                conf.get("allow_inline_endpoints", False),
                op_engine,
            )
        sc = 404
        return sc, f"HTTP status code {sc}: the operation requested does not exist", "text/plain"
