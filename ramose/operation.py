# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import time
from csv import DictReader, reader, writer
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from http import HTTPStatus
from io import StringIO
from itertools import product
from json import dumps
from math import ceil
from operator import eq, gt, itemgetter, lt
from re import findall, match, search, sub
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote, urlsplit

from requests.exceptions import RequestException

try:
    from pysparql_anything import SparqlAnything
except ImportError:
    SparqlAnything = None

from ramose._constants import DEFAULT_HTTP_TIMEOUT, FIELD_TYPE_RE, _http_session, media_type_for_format
from ramose.datatype import DataType
from ramose.paging import PaginationInfo, build_link_header, build_pagination_info

if TYPE_CHECKING:
    import types
    from collections.abc import Callable

    from ramose.cache import ResultCache


class HttpError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class OperationConfig:
    sparql_endpoint: str = ""
    sparql_http_method: str = "get"
    addon: types.ModuleType | None = None
    format_map: dict = dataclass_field(default_factory=dict)
    format_media_types: dict = dataclass_field(default_factory=dict)
    sources_map: dict = dataclass_field(default_factory=dict)
    engine: str = "sparql"
    custom_params: dict = dataclass_field(default_factory=dict)
    disabled_params: set = dataclass_field(default_factory=set)
    cache: ResultCache | None = None
    default_cache_ttl: int = 86400


class Operation:
    def __init__(
        self,
        op_complete_url: str,
        op_key: str,
        op_item: dict[str, str],
        config: OperationConfig | None = None,
    ) -> None:
        if config is None:
            config = OperationConfig()
        self.url_parsed = urlsplit(op_complete_url)
        self.op_url = self.url_parsed.path
        self.op = op_key
        self.i = op_item
        self.tp = config.sparql_endpoint
        self.sparql_http_method = config.sparql_http_method
        self.addon = config.addon
        self.format = config.format_map
        self.format_media_types = config.format_media_types
        self.sources_map = config.sources_map
        self.engine = config.engine
        self.custom_params = config.custom_params
        self.disabled_params = config.disabled_params
        self._sa_engine = None
        self._cache = config.cache
        self._default_cache_ttl = config.default_cache_ttl
        self.pagination_info: PaginationInfo | None = None

        self.operation = {"=": eq, "<": lt, ">": gt}

        self.dt = DataType()

    @staticmethod
    def get_content_type(ct: str) -> str:
        """It returns the mime type of a given textual representation of a format, being it either
        'csv' or 'json."""
        content_type = ct

        if ct == "csv":
            content_type = "text/csv"
        elif ct == "json":
            content_type = "application/json"

        return content_type

    def _resolve_format(self, s: str, query_string: dict[str, list[str]]) -> tuple[str, str] | None:
        if self.pagination_info is not None:
            request_url = self.pagination_info.self_url
        elif self.url_parsed.query:
            request_url = f"{self.op_url}?{self.url_parsed.query}"
        else:
            request_url = self.op_url

        if "format" in query_string and "format" not in self.disabled_params:
            for req_format in query_string["format"]:
                if req_format in self.format:
                    converter_func = getattr(self.addon, self.format[req_format])
                    return converter_func(s, request_url=request_url), self._media_type_for_format(req_format)
        elif "default_format" in self.i:
            default_fmt = self.i["default_format"].strip()
            if default_fmt in self.format:
                converter_func = getattr(self.addon, self.format[default_fmt])
                return converter_func(s, request_url=request_url), self._media_type_for_format(default_fmt)
        return None

    def _media_type_for_format(self, fmt: str) -> str:
        if fmt in self.format_media_types:
            return self.format_media_types[fmt]
        return Operation.get_content_type(fmt)

    def media_type_to_format(self) -> dict[str, str]:
        if "format" in self.disabled_params:
            return {}
        default_token = self.i["default_format"].strip() if "default_format" in self.i else "json"
        media_type_to_token: dict[str, str] = {}
        for token in [default_token, "json", "csv", *self.format]:
            if token in self.format_media_types:
                media_type = self.format_media_types[token]
            else:
                media_type = media_type_for_format(token)
            if media_type is not None:
                media_type_to_token.setdefault(media_type, token)
        return media_type_to_token

    def conv(self, s: str, query_string: dict[str, list[str]], c_type: str = "text/csv") -> tuple[str, str]:
        """This method takes a string representing a CSV document and converts it in the requested format according
        to what content type is specified as input."""

        content_type = Operation.get_content_type(c_type)

        resolved = self._resolve_format(s, query_string)
        if resolved is not None:
            return resolved

        if "format" in query_string and "format" not in self.disabled_params:
            for req_format in query_string["format"]:
                content_type = Operation.get_content_type(req_format)
        elif "default_format" in self.i:
            content_type = Operation.get_content_type(self.i["default_format"].strip())

        if content_type not in ("text/csv", "application/json"):
            content_type = "text/csv"

        if "application/json" in content_type:
            with StringIO(s) as f:
                r = [dict(i) for i in DictReader(f)]

                if "json" not in self.disabled_params:
                    r = Operation.structured(query_string, r)  # type: ignore[arg-type]

                return dumps(r, ensure_ascii=False, indent=4), content_type
        else:
            return s, content_type

    @staticmethod
    def pv(i: int | tuple[object, str], r: list[tuple[object, str]] | None = None) -> str:
        """This method returns the plain value of a particular item 'i' of the result returned by the SPARQL query.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[1]  # type: ignore[index]
        return Operation.pv(r[i])  # type: ignore[index]

    @staticmethod
    def tv(i: int | tuple[object, str], r: list[tuple[object, str]] | None = None) -> object:
        """This method returns the typed value of a particular item 'i' of the result returned by the SPARQL query.
        The type associated to that value is actually specified by means of the particular configuration provided
        in the specification file of the API - field 'field_type'.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[0]  # type: ignore[index]
        return Operation.tv(r[i])  # type: ignore[index]

    @staticmethod
    def do_overlap(r1: tuple[int, int], r2: tuple[int, int]) -> bool:
        """This method returns a boolean that says if the two ranges (i.e. two pairs of integers) passed as inputs
        actually overlap one with the other."""
        r1_s, r1_e = r1
        r2_s, r2_e = r2

        return r1_s <= r2_s <= r1_e or r2_s <= r1_s <= r2_e

    @staticmethod
    def get_item_in_dict(
        d_or_l: dict[str, object] | list[dict[str, object]], key_list: list[str], prev: list[object] | None = None
    ) -> list[object]:
        """This method takes as input a dictionary or a list of dictionaries and browses it until the value
        specified following the chain indicated in 'key_list' is not found. It returns a list of all the
        values that matched with such search."""
        res = [] if prev is None else prev.copy()

        d_list = [d_or_l] if isinstance(d_or_l, dict) else d_or_l

        for d in d_list:
            key_list_len = len(key_list)

            if key_list_len >= 1:
                key = key_list[0]
                if key in d:
                    if key_list_len == 1:
                        res.append(d[key])
                    else:
                        res = Operation.get_item_in_dict(d[key], key_list[1:], res)  # type: ignore[arg-type]

        return res

    @staticmethod
    def add_item_in_dict(
        d_or_l: dict[str, object] | list[dict[str, object]], key_list: list[str], item: object, idx: int
    ) -> None:
        """This method takes as input a dictionary or a list of dictionaries, browses it until the value
        specified following the chain indicated in 'key_list' is not found, and then substitutes it with 'item'.
        In case the final object retrieved is a list, it selects the object in position 'idx' before the
        substitution."""
        key_list_len = len(key_list)

        if key_list_len >= 1:
            key = key_list[0]

            if isinstance(d_or_l, list):
                if key_list_len == 1:
                    d_or_l[idx][key] = item
                else:
                    for i in d_or_l:
                        Operation.add_item_in_dict(i, key_list, item, idx)
            elif key in d_or_l:
                if key_list_len == 1:
                    d_or_l[key] = item
                else:
                    Operation.add_item_in_dict(d_or_l[key], key_list[1:], item, idx)  # type: ignore[arg-type]

    @staticmethod
    def _apply_array_transform(row: dict[str, object], keys: list[str], separator: str, v_list: list[object]) -> None:
        for idx, v in enumerate(v_list):
            if isinstance(v, str):
                Operation.add_item_in_dict(row, keys, v.split(separator) if v != "" else [], idx)

    @staticmethod
    def _apply_dict_transform(
        row: dict[str, object], keys: list[str], separator: str, entries: list[str], v_list: list[object]
    ) -> None:
        new_fields = entries[1:]
        new_fields_max_split = len(new_fields) - 1
        for idx, v in enumerate(v_list):
            if isinstance(v, str):
                new_values = v.split(separator, new_fields_max_split)
                Operation.add_item_in_dict(
                    row,
                    keys,
                    dict(zip(new_fields, new_values, strict=False)) if v != "" else {},
                    idx,
                )
            elif isinstance(v, list):
                new_list = [dict(zip(new_fields, i.split(separator, new_fields_max_split), strict=False)) for i in v]
                Operation.add_item_in_dict(row, keys, new_list, idx)

    @staticmethod
    def structured(params: dict[str, list[str]], json_table: list[dict[str, object]]) -> list[dict[str, object]]:
        """This method checks if there are particular transformation rules specified in 'params' for a JSON output,
        and convert each row of the input table ('json_table') according to these rules.
        There are two specific rules that can be applied:

        1. array("<separator>",<field>): it converts the string value associated to the field name '<field>' into
        an array by splitting the various textual parts by means of '<separator>'. For instance, consider the
        following JSON structure:

        [
            { "names": "Doe, John; Doe, Jane" },
            { "names": "Doe, John; Smith, John" }
        ]

        Executing the rule 'array("; ",names)' returns the following new JSON structure:

        [
            { "names": [ "Doe, John", "Doe, Jane" ],
            { "names": [ "Doe, John", "Smith, John" ]
        ]

        2. dict("separator",<field>,<new_field_1>,<new_field_2>,...): it converts the string value associated to
        the field name '<field>' into an dictionary by splitting the various textual parts by means of
        '<separator>' and by associating the new fields '<new_field_1>', '<new_field_2>', etc., to these new
        parts. For instance, consider the following JSON structure:

        [
            { "name": "Doe, John" },
            { "name": "Smith, John" }
        ]

        Executing the rule 'array(", ",name,family_name,given_name)' returns the following new JSON structure:

        [
            { "name": { "family_name": "Doe", "given_name: "John" } },
            { "name": { "family_name": "Smith", "given_name: "John" } }
        ]

        Each of the specified rules is applied in order, and it works on the JSON structure returned after
        the execution of the previous rule."""
        if "json" in params:
            fields = params["json"]
            for field in fields:
                ops = findall(r'([a-z]+)\(("[^"]+"),([^\)]+)\)', field)
                for op_type, s, es in ops:
                    separator = sub('"(.+)"', "\\1", s)
                    entries = [i.strip() for i in es.split(",")]
                    keys = entries[0].split(".")

                    for row in json_table:
                        v_list = Operation.get_item_in_dict(row, keys)
                        if op_type == "array":
                            Operation._apply_array_transform(row, keys, separator, v_list)
                        elif op_type == "dict":
                            Operation._apply_dict_transform(row, keys, separator, entries, v_list)

        return json_table

    def preprocess(
        self, par_dict: dict[str, object], op_item: dict[str, str], addon: types.ModuleType
    ) -> dict[str, object]:
        """This method takes the a dictionary of parameters with the current typed values associated to them and
        the item of the API specification defining the behaviour of that operation, and preprocesses the parameters
        according to the functions specified in the '#preprocess' field (e.g. "#preprocess lower(doi)"), which is
        applied to the specified parameters as input of the function in consideration (e.g.
        "/api/v1/citations/10.1108/jd-12-2013-0166", converting the DOI in lowercase).

        It is possible to run multiple functions sequentially by concatenating them with "-->" in the API
        specification document. In this case the output of the function f_i will becomes the input operation URL
        of the function f_i+1.

        Finally, it is worth mentioning that all the functions specified in the "#preprocess" field must return
        a tuple of values defining how the particular value passed in the dictionary must be changed."""
        result = par_dict

        if "preprocess" in op_item:
            for pre in [sub(r"\s+", "", i) for i in op_item["preprocess"].split(" --> ")]:
                func_name = sub(r"^([^\(\)]+)\(.+$", r"\1", pre).strip()
                params_name = sub(r"^.+\(([^\(\)]+)\).*", r"\1", pre).split(",")

                param_list = tuple(result[param_name] for param_name in params_name)

                # run function
                func = getattr(addon, func_name)
                res = func(*param_list)

                # substitute res to the current parameter in result
                for idx, val in enumerate(res):
                    result[params_name[idx]] = val

        return result

    def postprocess(
        self, res: list[list[str] | list[tuple[object, str]]], op_item: dict[str, str], addon: types.ModuleType
    ) -> list[list[str] | list[tuple[object, str]]]:
        """This method takes the result table returned by running the SPARQL query in an API operation (specified
        as input) and change some of such results according to the functions specified in the '#postprocess'
        field (e.g. "#postprocess remove_date("2018")"). These functions can take parameters as input, while the first
        unspecified parameters will be always the result table. It is worth mentioning that this result table (i.e.
        a list of tuples) actually contains, in each cell, a tuple defining the plain value as well as the typed
        value for enabling better comparisons and operations if needed. An example of this table of result is shown as
        follows:

        [
            ("id", "date"),
            ("my_id_1", "my_id_1"), (datetime(2018, 3, 2), "2018-03-02"),
            ...
        ]

        Note that the typed value and the plain value of each cell can be selected by using the methods "tv" and "pv"
        respectively. In addition, it is possible to run multiple functions sequentially by concatenating them
        with "-->" in the API specification document. In this case the output of the function f_i will becomes
        the input result table of the function f_i+1."""
        result = res

        if "postprocess" in op_item:
            for post in [i.strip() for i in op_item["postprocess"].split(" --> ")]:
                func_name = sub(r"^([^\(\)]+)\(.+$", r"\1", post).strip()
                param_str = sub(r"^.+\(([^\(\)]*)\).*", r"\1", post)
                params_values = () if param_str == "" else next(reader(param_str.splitlines(), skipinitialspace=True))

                func = getattr(addon, func_name)
                func_params = (result, *tuple(params_values))
                result, do_type_fields = func(*func_params)
                if do_type_fields:
                    result = self.type_fields(result, op_item)

        return result

    @staticmethod
    def _apply_require(
        header: list[str], result: list[list[tuple[object, str]]], fields: list[str]
    ) -> list[list[tuple[object, str]]]:
        """Exclude rows with empty values in the specified fields."""
        for field in fields:
            field_idx = header.index(field)
            result = [row for row in result if Operation.pv(field_idx, row) not in (None, "")]
        return result

    def _apply_filter(
        self, header: list[str], result: list[list[tuple[object, str]]], fields: list[str]
    ) -> list[list[tuple[object, str]]]:
        """Filter rows by comparison operators or regex patterns."""
        for field in fields:
            field_name, field_value = field.split(":", 1)
            try:
                field_idx = header.index(field_name)
                flag = field_value[0]
                if flag in ("<", ">", "="):
                    value = field_value[1:].lower()
                    result = [
                        row
                        for row in result
                        if self.operation[flag](
                            Operation.tv(field_idx, row),
                            self.dt.get_func(type(Operation.tv(field_idx, row)).__name__)(value),
                        )
                    ]
                else:
                    pattern = field_value.lower()
                    result = [row for row in result if search(pattern, Operation.pv(field_idx, row).lower())]
            except ValueError:
                pass
        return result

    @staticmethod
    def _apply_sort(
        header: list[str], result: list[list[tuple[object, str]]], fields: list[str]
    ) -> list[list[tuple[object, str]]]:
        """Sort rows by the specified fields and directions."""
        for field in sorted(fields, reverse=True):
            order_names = findall(r"^(desc|asc)\(([^\(\)]+)\)$", field)
            if order_names:
                direction, field_name = order_names[0]
            else:
                direction, field_name = "asc", field
            try:
                field_idx = header.index(field_name)
                result = sorted(result, key=itemgetter(field_idx), reverse=(direction == "desc"))
            except ValueError:
                pass
        return result

    def handling_params(
        self, params: dict[str, list[str]], table: list[list[str] | list[tuple[object, str]]]
    ) -> list[list[str] | list[tuple[object, str]]]:
        """This method is used for filtering the results that are returned after the post-processing
        phase. In particular, it is possible to:

        1. [require=<field_name>] exclude all the rows that have an empty value in the field specified - e.g. the
           "require=doi" remove all the rows that do not have any string specified in the "doi" field;

        2. [filter=<field_name>:<operator><value>] consider only the rows where the string in the input field
           is compliant with the value specified. If no operation is specified, the value is interpreted as a
           regular expression, otherwise it is compared according to the particular type associated to that field.
           Possible operators are "=", "<", and ">" - e.g. "filter=title:semantics?" returns all the rows that contain
           the string "semantic" or "semantics" in the field title, while "filter=date:>2016-05" returns all the rows
           that have a date greater than May 2016;

        3. [sort=<order>(<field_name>)] sort all the results according to the value and type of the particular
           field specified in input. It is possible to sort the rows either in ascending ("asc") or descending
           ("desc") order - e.g. "sort=desc(date)" sort all the rows according to the value specified in the
           field "date" in descending order.

        Note that these filtering operations are applied in the order presented above - first the "require", then
        the "filter", and finally the "sort". It is possible to specify one or more filtering operation of the
        same kind (e.g. "require=doi&require=title").
        """
        header = table[0]
        result = table[1:]

        overridden = set(self.custom_params) | self.disabled_params

        if ("exclude" in params or "require" in params) and "require" not in overridden and "exclude" not in overridden:
            fields = params["exclude"] if "exclude" in params else params["require"]
            result = self._apply_require(header, result, fields)  # type: ignore[arg-type]

        if "filter" in params and "filter" not in overridden:
            result = self._apply_filter(header, result, params["filter"])  # type: ignore[arg-type]

        if "sort" in params and "sort" not in overridden:
            result = self._apply_sort(header, result, params["sort"])  # type: ignore[arg-type]

        return [header, *result]

    def type_fields(
        self, res: list[list[str] | list[tuple[object, str]] | list[str | object]], op_item: dict[str, str]
    ) -> list[list[str] | list[tuple[object, str]]]:
        """It creates a version of the results 'res' that adds, to each value of the fields, the same value interpreted
        with the type specified in the specification file (field 'field_type'). Note that 'str' is used as default in
        case no further specifications are provided."""
        result = []
        cast_func = {}
        header = res[0]
        for heading in header:
            cast_func[heading] = DataType.str

        if "field_type" in op_item:
            for f, p in findall(FIELD_TYPE_RE, op_item["field_type"]):
                cast_func[p] = self.dt.get_func(f)

        for row in res[1:]:
            new_row = []
            for idx, heading in enumerate(header):
                cur_value = row[idx]
                if isinstance(cur_value, tuple):
                    cur_value = cur_value[1]
                new_row.append((cast_func[heading](cur_value), cur_value))
            result.append(new_row)

        return [header, *result]  # type: ignore[return-value]

    def remove_types(self, res: list[list[str] | list[tuple[object, str]]]) -> list[list[str] | tuple[str, ...]]:
        """This method takes the results 'res' that include also the typed value and returns a version of such
        results without the types that is ready to be stored on the file system."""
        result = [res[0]]
        result.extend(tuple(Operation.pv(idx, row) for idx in range(len(row))) for row in res[1:])  # type: ignore[arg-type]
        return result  # type: ignore[return-value]

    @staticmethod
    def _is_directive(line: str) -> bool:
        return line.strip().startswith("@@")

    @staticmethod
    def _parse_directive_args(
        tokens: list[str], param_names: list[str], defaults: dict[str, str] | None = None
    ) -> dict[str, str]:
        defaults = defaults or {}
        all_names = set(param_names) | set(defaults)
        result = {}
        positional_index = 0
        seen_keyword = False

        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)
                if key in all_names:
                    if key in result:
                        msg = f"Duplicate parameter {key!r}"
                        raise ValueError(msg)
                    seen_keyword = True
                    result[key] = value
                    continue
            if seen_keyword:
                msg = f"Positional argument {token!r} cannot follow keyword argument"
                raise ValueError(msg)
            if positional_index >= len(param_names):
                msg = f"Unexpected argument {token!r}"
                raise ValueError(msg)
            result[param_names[positional_index]] = token
            positional_index += 1

        for name, default in defaults.items():
            if name not in result:
                result[name] = default

        missing = [name for name in param_names if name not in result]
        if missing:
            msg = f"Missing required parameter(s): {', '.join(missing)}"
            raise ValueError(msg)

        return result

    def _handle_directive_with(self, parts: list[str]) -> tuple[str, None]:
        args = Operation._parse_directive_args(parts[1:], ["source"])
        name = args["source"]
        if name not in self.sources_map:
            msg = f"Unknown source '{name}' in @@with; declare it in #sources."
            raise ValueError(msg)
        return self.sources_map[name], None

    @staticmethod
    def _handle_directive_endpoint(parts: list[str]) -> tuple[str, None]:
        args = Operation._parse_directive_args(parts[1:], ["target"])
        return args["target"], None

    @staticmethod
    def _handle_directive_join(parts: list[str]) -> tuple[None, tuple[str, str, str, str]]:
        args = Operation._parse_directive_args(parts[1:], ["left_var", "right_var"], defaults={"type": "inner"})
        return None, ("JOIN", args["left_var"], args["right_var"], args["type"].lower())

    @staticmethod
    def _handle_directive_values(parts: list[str]) -> tuple[None, tuple[str, list[str]]]:
        tokens = parts[1:]
        if not tokens:
            msg = "@@values needs at least one variable"
            raise ValueError(msg)
        return None, ("VALUES_INJECT", tokens)

    @staticmethod
    def _handle_directive_foreach(parts: list[str]) -> tuple[None, tuple[str, str, str, float]]:
        args = Operation._parse_directive_args(parts[1:], ["variable", "placeholder"], defaults={"wait": "0"})
        var_name = args["variable"]
        if not var_name.startswith("?"):
            msg = f"@@foreach variable must start with '?', got {var_name!r}"
            raise ValueError(msg)
        try:
            delay = float(args["wait"])
        except ValueError:
            msg = f"Invalid wait value in @@foreach: {args['wait']!r}"
            raise ValueError(msg) from None
        return None, ("FOREACH", var_name, args["placeholder"], delay)

    def _process_directive(
        self, line: str, directive_handlers: dict[str, Callable[..., object]]
    ) -> tuple[str | None, tuple[str, ...] | None]:
        body = line.strip()[2:].strip()
        parts = body.split()
        cmd = parts[0].lower()

        handler = directive_handlers.get(cmd)
        if handler is None:
            msg = f"Unknown directive @@{cmd}"
            raise ValueError(msg)

        return handler(parts)  # type: ignore[return-value]

    def _parse_steps(self, text: str, default_endpoint: str, params: dict[str, object]) -> list[tuple[str, ...]]:
        """
        Returns a list of steps:
          - ("QUERY", endpoint_url, query_text)
          - ("JOIN", left_var, right_var, how)       # how in {"inner","left"}
          - ("REMOVE", [vars])
          - ("VALUES_INJECT", [vars])                # @@values ?var1 ?var2 ...
          - ("FOREACH", var_name, placeholder, delay)  # @@foreach ?var placeholder [wait=N]
        """
        for p, v in params.items():
            text = text.replace(f"[[{p}]]", str(v))
        steps: list[tuple[str, ...]] = []
        cur_query: list[str] = []
        current_endpoint = default_endpoint

        directive_handlers = {
            "with": self._handle_directive_with,
            "endpoint": self._handle_directive_endpoint,
            "join": self._handle_directive_join,
            "remove": lambda parts: (None, ("REMOVE", parts[1:])),
            "values": self._handle_directive_values,
            "foreach": self._handle_directive_foreach,
        }

        def flush_query() -> None:
            if cur_query:
                q = "\n".join(cur_query).strip()
                if not q:
                    cur_query.clear()
                    return
                for p, v in params.items():
                    q = q.replace(f"[[{p}]]", str(v))
                steps.append(("QUERY", current_endpoint, q))
                cur_query.clear()

        for raw in text.splitlines():
            line = raw.rstrip("\n")
            if not self._is_directive(line):
                cur_query.append(line)
                continue

            flush_query()

            new_endpoint, step = self._process_directive(line, directive_handlers)
            if new_endpoint is not None:
                current_endpoint = new_endpoint
            if step is not None:
                steps.append(step)

        flush_query()
        return steps

    def _run_sparql_dicts(self, endpoint_url: str, query_text: str) -> list[dict[str, object]]:
        """Run a SELECT query against a SPARQL endpoint and return a list of dict rows.

        This always requests CSV and parses it via DictReader, to stay consistent
        with RAMOSE's legacy pipeline.
        """
        try:
            if self.sparql_http_method == "get":
                r = _http_session.get(
                    endpoint_url + "?query=" + quote(query_text),
                    headers={
                        "Accept": "text/csv",
                        "User-Agent": "RAMOSE/2.0.0",
                    },
                    timeout=DEFAULT_HTTP_TIMEOUT,
                )
            else:
                r = _http_session.post(
                    endpoint_url,
                    data=query_text,
                    headers={
                        "Accept": "text/csv",
                        "Content-Type": "application/sparql-query",
                        "User-Agent": "RAMOSE/2.0.0",
                    },
                    timeout=DEFAULT_HTTP_TIMEOUT,
                )
        except RequestException as e:
            msg = f"SPARQL request failed: {e}"
            raise RuntimeError(msg) from e

        r.encoding = "utf-8"
        if r.status_code != HTTPStatus.OK:
            msg = f"SPARQL {r.status_code}: {r.reason}"
            raise RuntimeError(msg)
        text = r.content.decode("utf-8-sig", errors="replace")
        list_of_lines = text.splitlines()
        return list(DictReader(list_of_lines))  # type: ignore[return-value]

    @staticmethod
    def _normalize_sparql_json_resultset(result: dict[str, object]) -> list[dict[str, object]]:
        """Convert a SPARQL JSON ResultSet dict to a list of flat dicts."""
        vars_ = result["head"].get("vars") or []  # type: ignore[union-attr]
        return [
            {v: (b[v].get("value") if isinstance(b.get(v), dict) else b.get(v)) for v in vars_}
            for b in result["results"].get("bindings", [])  # type: ignore[union-attr]
        ]

    @staticmethod
    def _normalize_columnar_dict(result: dict[str, object]) -> list[dict[str, object]]:
        """Convert a column-oriented dict {col: [values]} to a list of row dicts."""
        cols = list(result.keys())
        max_len = max((len(v) for v in result.values() if isinstance(v, (list, tuple))), default=0)

        if not max_len:
            return [result]

        rows = []
        for i in range(max_len):
            row = {}
            for c in cols:
                v = result[c]
                row[c] = (
                    v[i]
                    if isinstance(v, (list, tuple)) and i < len(v)
                    else (v if not isinstance(v, (list, tuple)) else None)
                )
            rows.append(row)
        return rows

    def _run_sparql_anything_dicts(
        self, query_text: str, values: dict[str, str] | None = None
    ) -> list[dict[str, object]]:
        """
        Execute a SPARQL Anything SELECT query via PySPARQL-Anything and return
        a list of dicts (one per row), in the same shape as _run_sparql_dicts.

        query_text: full SPARQL (Anything) query string
                        (typically containing SERVICE <x-sparql-anything:...>).
        values: optional dict of template parameters for the query
                    (name -> value), passed to SPARQL Anything's `values=`.
        """
        if self._sa_engine is None:
            if SparqlAnything is None:
                msg = "pysparql_anything not installed. Install with: pip install ramose[sparql-anything]"
                raise ImportError(msg)
            self._sa_engine = SparqlAnything()

        kwargs = {"query": query_text}
        if values:
            kwargs["values"] = {str(k): str(v) for k, v in values.items()}  # type: ignore[assignment]

        result = self._sa_engine.select(output_type=dict, **kwargs)

        # Normalize to list[dict]
        if isinstance(result, list):
            if result and isinstance(result[0], dict):
                return result
            return [dict(row) for row in result]

        if not isinstance(result, dict):
            return [{"result": result}]

        # Standard SPARQL JSON ResultSet shape
        head = result.get("head")
        results_obj = result.get("results")
        if isinstance(head, dict) and isinstance(results_obj, dict) and "bindings" in results_obj:
            return self._normalize_sparql_json_resultset(result)

        # Column-oriented dict or single-row fallback
        return self._normalize_columnar_dict(result)

    def _run_query_dicts(self, endpoint_url: str, query_text: str) -> list[dict[str, object]]:
        """
        Dispatch query execution to the appropriate backend, with support
        for per-query engine selection in multi-source mode.

        Rules:
        - If endpoint_url is the special string "sparql-anything" (case-insensitive),
        then always use SPARQL.ANYTHING (PySPARQL-Anything) for this query.
        - Otherwise, fall back to the operation-level engine:
            * engine == "sparql-anything" -> SPARQL.ANYTHING
            * else                        -> standard HTTP SPARQL
        """

        # Per-query override: @@endpoint sparql-anything
        if endpoint_url and str(endpoint_url).strip().lower() == "sparql-anything":
            return self._run_sparql_anything_dicts(query_text)

        # Default behaviour: operation-level engine
        if self.engine == "sparql-anything":
            return self._run_sparql_anything_dicts(query_text)
        return self._run_sparql_dicts(endpoint_url, query_text)

    def _inject_values_clause(self, query_text: str, vars_: list[str], acc_rows: list[dict[str, object]] | None) -> str:
        # build distinct tuples for requested vars from the accumulator
        cols = [v.lstrip("?") for v in vars_]
        tuples, seen = [], set()
        for row in acc_rows or []:
            tup = tuple(row.get(c, "") for c in cols)
            if all(tup) and tup not in seen:
                seen.add(tup)
                tuples.append(tup)
        if not tuples:
            return query_text  # nothing to inject

        # format literals vs IRIs
        def fmt(x: object) -> str:
            s = str(x)
            if s.startswith(("http://", "https://")):
                return f"<{s}>"
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

        head = "VALUES (" + " ".join(vars_) + ") {\n"
        body = "\n".join("  (" + " ".join(fmt(v) for v in tup) + ")" for tup in tuples)
        tail = "\n}\n"

        i = query_text.find("{")
        if i == -1:
            # no WHERE brace: put VALUES at top (legal SPARQL)
            return head + body + tail + query_text
        j = i + 1
        return query_text[:j] + "\n" + head + body + tail + query_text[j:]

    @staticmethod
    def _drop_columns(rows: list[dict[str, object]], vars_: list[str]) -> list[dict[str, object]]:
        if not rows:
            return rows
        vars_set = {v.lstrip("?") for v in vars_}
        return [{k: v for k, v in r.items() if k not in vars_set and ("?" + k) not in vars_set} for r in rows]

    def _norm_join_key(self, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        # unify scheme for w3id IRIs (and similar)
        if s.startswith("http://"):
            s = "https://" + s[len("http://") :]
        # drop a single trailing slash for stability
        return s.removesuffix("/")

    @staticmethod
    def _merge_row(
        left_row: dict[str, object], right_row: dict[str, object], right_cols: list[str]
    ) -> dict[str, object]:
        merged = dict(left_row)
        for col in right_cols:
            right_val = right_row.get(col)
            if right_val is None:
                continue
            if col not in merged or merged[col] in ("", None):
                merged[col] = right_val
            else:
                alt = f"{col}_r"
                if alt not in merged or merged[alt] in ("", None):
                    merged[alt] = right_val
        return merged

    def _join(
        self,
        left_rows: list[dict[str, object]] | None,
        right_rows: list[dict[str, object]] | None,
        lkey: str,
        rkey: str,
        how: str = "inner",
    ) -> list[dict[str, object]]:
        """
        Merge two row sets on lkey (from left_rows) and rkey (from right_rows).
        - lkey/rkey may be passed as '?var' or 'var' -> we normalize to bare names.
        - Keys are normalized with _norm_join_key (e.g., http -> https, trim slash).
        - When 'left', all left rows are preserved even if no match on the right.
        - Right-hand columns are copied into the merged row; collisions are avoided.
        """
        lcol = lkey.lstrip("?")
        rcol = rkey.lstrip("?")

        left_rows = left_rows or []
        right_rows = right_rows or []

        rindex: dict[str, list[dict[str, object]]] = {}
        for r in right_rows:
            rk = self._norm_join_key(r.get(rcol))
            if rk is None:
                continue
            rindex.setdefault(rk, []).append(r)

        right_cols = [c for c in (right_rows[0].keys() if right_rows else []) if c != rcol]

        out: list[dict[str, object]] = []
        for left_row in left_rows:
            lk = self._norm_join_key(left_row.get(lcol))
            matches = rindex.get(lk, [])  # type: ignore[arg-type]
            if matches:
                out.extend(self._merge_row(left_row, r, right_cols) for r in matches)
            elif how == "left":
                out.append(dict(left_row))
        return out

    def _apply_custom_postprocess_params(
        self, table: list[list[str] | list[tuple[object, str]] | tuple[str, ...]], q_string: dict[str, list[str]]
    ) -> list[list[str] | list[tuple[object, str]] | tuple[str, ...]]:
        for param_name, param_conf in self.custom_params.items():
            if param_conf["phase"] != "postprocess":
                continue
            if param_name in q_string:
                handler = getattr(self.addon, param_conf["handler"])
                table = handler(table, q_string[param_name])
        return table

    @property
    def _cache_ttl(self) -> int:
        if "cache_duration" in self.i:
            return int(self.i["cache_duration"])
        return self._default_cache_ttl

    def _build_cache_key(self, q_string: dict[str, list[str]]) -> str:
        presentation_params = {"page", "page_size", "format", "json"}
        data_params = sorted((name, values) for name, values in q_string.items() if name not in presentation_params)
        if data_params:
            query_string = "&".join(f"{name}={value}" for name, values in data_params for value in values)
            return f"{self.tp}:{self.op_url}?{query_string}"
        return f"{self.tp}:{self.op_url}"

    def _extract_pagination_params(self, q_string: dict[str, list[str]]) -> tuple[int, int] | None:
        if "page_size" not in q_string or "page_size" in self.disabled_params:
            return None
        page_size = int(q_string["page_size"][0])
        if page_size < 1:
            msg = f"page_size must be >= 1, got {page_size}"
            raise ValueError(msg)
        page = 1
        if "page" in q_string and "page" not in self.disabled_params:
            page = int(q_string["page"][0])
            if page < 1:
                msg = f"page must be >= 1, got {page}"
                raise ValueError(msg)
        return page, page_size

    def _has_custom_converter(self, q_string: dict[str, list[str]]) -> bool:
        if "format" in q_string and "format" not in self.disabled_params:
            for req_format in q_string["format"]:
                if req_format in self.format:
                    return True
        elif "default_format" in self.i and self.i["default_format"].strip() in self.format:
            return True
        return False

    def _paginate_and_format(
        self,
        table: list[list[str] | list[tuple[object, str]] | tuple[str, ...]],
        q_string: dict[str, list[str]],
        content_type: str,
    ) -> tuple[int, str, str]:
        if self._has_custom_converter(q_string):
            self.pagination_info = None
        else:
            page_params = self._extract_pagination_params(q_string)
            if page_params is not None:
                page, page_size = page_params
                total_items = len(table) - 1
                total_pages = ceil(total_items / page_size)
                if page > total_pages:
                    msg = f"page {page} exceeds total pages {total_pages}"
                    raise ValueError(msg)
                start = (page - 1) * page_size
                end = start + page_size
                table = [table[0], *table[1 + start : 1 + end]]
                self.pagination_info = build_pagination_info(self.op_url, q_string, page, page_size, total_items)
            else:
                self.pagination_info = None

        s_res = StringIO()
        writer(s_res).writerows(table)
        body, ctype = self.conv(s_res.getvalue(), q_string, content_type)

        return 200, body, ctype

    def _finalize_result(
        self, csv_rows: list[list[str]] | list[list[str | object]], content_type: str
    ) -> tuple[int, str, str]:
        """Run the shared pipeline: type fields, postprocess, filter, remove types, cache, paginate, format."""
        q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
        res = self.type_fields(csv_rows, self.i)  # type: ignore[arg-type]
        if self.addon is not None:
            res = self.postprocess(res, self.i, self.addon)
        res = self.handling_params(q_string, res)
        res = self.remove_types(res)
        if self.custom_params:
            res = self._apply_custom_postprocess_params(res, q_string)  # type: ignore[arg-type]
        if self._cache is not None and "cache_disable" not in self.i:
            self._cache.set(self._build_cache_key(q_string), res, expire=self._cache_ttl)
        return self._paginate_and_format(res, q_string, content_type)  # type: ignore[arg-type]

    @staticmethod
    def _header_from_field_type(op_item: dict[str, str], acc: list[dict[str, object]]) -> list[str]:
        # Respect #field_type order if provided, else derive from data
        if "field_type" in op_item:
            # FIELD_TYPE_RE is global in this file
            return [f for (_, f) in findall(FIELD_TYPE_RE, op_item["field_type"])]
        # fallback to keys of first row
        return list(acc[0].keys()) if acc else []

    @staticmethod
    def _to_csv_rows(header: list[str], acc: list[dict[str, object]]) -> list[list[object]]:
        rows: list[list[object]] = [header]  # type: ignore[list-item]
        rows.extend([d.get(h, "") for h in header] for d in acc)
        return rows

    def _extract_params(self) -> dict[str, object]:
        """Extract URL parameters and apply type conversions based on the operation spec."""
        par_dict = {}
        url_match = match(self.op, self.op_url)
        if url_match is None:
            msg = f"URL {self.op_url} does not match pattern {self.op}"
            raise ValueError(msg)
        par_man = url_match.groups()
        for idx, par in enumerate(findall("{([^{}]+)}", self.i["url"])):
            try:
                par_type = self.i[par].split("(")[0]
                par_value = par_man[idx] if par_type == "str" else self.dt.get_func(par_type)(par_man[idx])
            except KeyError:
                par_value = par_man[idx]
            par_dict[par] = par_value
        return par_dict

    def _apply_custom_preprocess_params(self, par_dict: dict[str, object]) -> None:
        q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
        for param_name, param_conf in self.custom_params.items():
            if param_conf["phase"] != "preprocess":
                continue
            if param_name in q_string:
                handler = getattr(self.addon, param_conf["handler"])
                par_dict.update(handler(q_string[param_name]))
            elif param_name not in par_dict:
                par_dict[param_name] = ""
        for placeholder in findall(r"\[\[(\w+)\]\]", self.i["sparql"]):
            if placeholder not in par_dict:
                par_dict[placeholder] = ""

    def _exec_sparql_anything_single(self, par_dict: dict[str, object], content_type: str) -> tuple[int, str, str]:
        """Execute a single SPARQL Anything query and return the finalized result."""
        query = self.i["sparql"]
        for param, val in par_dict.items():
            query = query.replace(f"[[{param}]]", str(val))
        rows = self._run_sparql_anything_dicts(query)
        header = self._header_from_field_type(self.i, rows or [])
        csv_rows = self._to_csv_rows(header, rows or [])
        return self._finalize_result(csv_rows, content_type)

    def _exec_standard_sparql(self, par_dict: dict[str, object], content_type: str) -> tuple[int, str, str]:
        """Execute standard SPARQL queries, handling parameter combinations via cartesian product."""
        # Wrap scalar values in lists for cartesian product
        par_dict = {k: v if isinstance(v, list) else [v] for k, v in par_dict.items()}

        parameters_comb = [
            dict(zip(par_dict.keys(), combination, strict=False))
            for combination in product(*par_dict.values())  # type: ignore[arg-type]
        ]

        # Example: {"id":"5","area":["A1","A2"]}  ->  [{"id":"5","area":"A1"}, {"id":"5","area":"A2"}]

        list_of_res = []
        include_header_line = True
        for comb in parameters_comb:
            query = self.i["sparql"]
            for param, val in comb.items():
                query = query.replace(f"[[{param}]]", str(val))

            if self.sparql_http_method == "get":
                r = _http_session.get(
                    self.tp + "?query=" + quote(query),
                    headers={"Accept": "text/csv"},
                    timeout=DEFAULT_HTTP_TIMEOUT,
                )
            else:
                r = _http_session.post(
                    self.tp,
                    data=query,
                    headers={"Accept": "text/csv", "Content-Type": "application/sparql-query"},
                    timeout=DEFAULT_HTTP_TIMEOUT,
                )
            r.encoding = "utf-8"

            if r.status_code != HTTPStatus.OK:
                return r.status_code, f"HTTP status code {r.status_code}: {r.reason}", "text/plain"

            # Re-encode to handle non-UTF8 characters in splitlines
            list_of_lines = [line.decode("utf-8") for line in r.text.encode("utf-8").splitlines()]

            # Include the CSV header only from the first response
            if not include_header_line:
                list_of_lines = list_of_lines[1:]
            include_header_line = False

            list_of_res += list_of_lines

        return self._finalize_result(list(reader(list_of_res)), content_type)

    def _exec_foreach_query(
        self,
        endpoint_url: str,
        qtxt: str,
        foreach: tuple[str, str, float],
        acc: list[dict[str, object]] | None,
    ) -> list[dict[str, object]]:
        """Run one query per distinct value collected from the accumulator (@@foreach)."""
        var_name, placeholder, delay = foreach
        column = var_name.lstrip("?")

        values = []
        seen = set()
        for row in acc or []:
            v = row.get(column)
            if v and v not in seen:
                seen.add(v)
                values.append(v)

        all_rows = []
        for idx_val, val in enumerate(values):
            q_one = qtxt.replace(f"[[{placeholder}]]", str(val))
            sub_rows = self._run_query_dicts(endpoint_url, q_one)
            if sub_rows:
                all_rows.extend(sub_rows)
            if delay and idx_val + 1 < len(values):
                time.sleep(delay)

        return all_rows

    def _exec_multi_source_query_step(self, endpoint_url: str, qtxt: str, state: dict[str, object]) -> None:
        """Handle a QUERY step in the multi-source pipeline."""
        if state["pending_foreach"] is not None:
            rows = self._exec_foreach_query(endpoint_url, qtxt, state["pending_foreach"], state["acc"])  # type: ignore[arg-type]
            state["pending_foreach"] = None
            state["pending_values_vars"] = None
        else:
            if state["pending_values_vars"]:
                qtxt = self._inject_values_clause(qtxt, state["pending_values_vars"], state["acc"])  # type: ignore[arg-type]
                state["pending_values_vars"] = None
            rows = self._run_query_dicts(endpoint_url, qtxt)

        if state["acc"] is None:
            state["acc"] = rows
        elif state["pending_join"]:
            lvar, rvar, how = state["pending_join"]  # type: ignore[misc]
            state["acc"] = self._join(state["acc"], rows, lvar, rvar, how)  # type: ignore[arg-type]
            state["pending_join"] = None
        else:
            msg = "Multiple QUERY steps without an explicit @@join directive"
            raise ValueError(msg)

    def _exec_multi_source(self, par_dict: dict[str, object], content_type: str) -> tuple[int, str, str]:
        """Execute a multi-source query pipeline with @@ directives."""
        steps = self._parse_steps(self.i["sparql"], self.tp, par_dict)

        state: dict[str, object] = {
            "acc": None,
            "pending_join": None,
            "pending_values_vars": None,
            "pending_foreach": None,
        }

        for st in steps:
            tag = st[0]

            if tag == "QUERY":
                self._exec_multi_source_query_step(st[1], st[2], state)
            elif tag == "JOIN":
                state["pending_join"] = (st[1], st[2], st[3])
            elif tag == "REMOVE":
                state["acc"] = self._drop_columns(state["acc"] or [], st[1])  # type: ignore[arg-type]
            elif tag == "VALUES_INJECT":
                state["pending_values_vars"] = st[1]
            elif tag == "FOREACH":
                state["pending_foreach"] = (st[1], st[2], st[3])
            else:
                msg = f"Unknown step tag {tag}"
                raise RuntimeError(msg)

        header = self._header_from_field_type(self.i, state["acc"] or [])  # type: ignore[arg-type]
        csv_rows = self._to_csv_rows(header, state["acc"] or [])  # type: ignore[arg-type]
        return self._finalize_result(csv_rows, content_type)

    @staticmethod
    def _format_error(sc: int, e: Exception, prefix: str = "") -> tuple[int, str, str]:
        """Format an error response tuple with traceback line info."""
        tb = e.__traceback__
        line = tb.tb_lineno if tb else "?"
        msg = f"HTTP status code {sc}: {prefix}{type(e).__name__}: {e} (line {line})"
        return sc, msg, "text/plain"

    def exec(self, method: str = "get", content_type: str = "application/json") -> tuple[int, str, str, dict[str, str]]:
        """This method takes in input the HTTP method to use for the call
        and the content type to return, and execute the operation as indicated
        in the specification file, by running (in the following order):

        1. the methods to preprocess the query;
        2. the SPARQL query related to the operation called, by using the parameters indicated in the URL;
        3. the specification of all the types of the various rows returned;
        4. the methods to postprocess the result;
        5. the application of the filter to remove, filter, sort the result;
        6. the removal of the types added at the step 3, so as to have a data structure ready to be returned;
        7. the conversion in the format requested by the user."""
        str_method = method.lower()
        if str_method not in self.i["method"].split():
            return 405, f"HTTP status code 405: '{str_method}' method not allowed", "text/plain", {}

        try:
            status, body, ctype = self._dispatch_exec(content_type)
        except HttpError as err:
            return err.status_code, str(err), "text/plain", {}
        except TimeoutError as e:
            return *self._format_error(408, e, "request timeout - "), {}
        except (TypeError, ValueError) as e:
            return *self._format_error(400, e, "parameter in the request not compliant with the type specified - "), {}
        except Exception as e:  # noqa: BLE001
            return *self._format_error(500, e, "something unexpected happened - "), {}

        headers = {}
        if self.pagination_info is not None:
            link_header = build_link_header(self.pagination_info)
            if link_header:
                headers["Link"] = link_header
        return status, body, ctype, headers

    def _dispatch_exec(self, content_type: str) -> tuple[int, str, str]:
        """Dispatch to the appropriate execution path based on SPARQL text content."""
        par_dict = self._extract_params()
        if self.addon is not None:
            self.preprocess(par_dict, self.i, self.addon)
        if self.custom_params:
            self._apply_custom_preprocess_params(par_dict)

        if self._cache is not None and "cache_disable" not in self.i:
            q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
            cached_table = self._cache.get(self._build_cache_key(q_string))
            if cached_table is not None:
                return self._paginate_and_format(cached_table, q_string, content_type)  # type: ignore[arg-type]

        sparql_text = self.i["sparql"]
        resolved_text = sparql_text
        for param, val in par_dict.items():
            resolved_text = resolved_text.replace(f"[[{param}]]", str(val))

        if "@@" not in resolved_text:
            if self.engine == "sparql-anything":
                return self._exec_sparql_anything_single(par_dict, content_type)
            return self._exec_standard_sparql(par_dict, content_type)

        try:
            return self._exec_multi_source(par_dict, content_type)
        except ValueError as ve:
            return 400, f"HTTP status code 400: {ve}", "text/plain"
        except RuntimeError as re_err:
            return 502, f"HTTP status code 502: {re_err}", "text/plain"
