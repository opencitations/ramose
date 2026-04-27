# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

import time
from csv import DictReader, reader, writer
from io import StringIO
from itertools import product
from json import dumps
from operator import eq, gt, itemgetter, lt
from re import findall, match, search, sub
from urllib.parse import parse_qs, quote, urlsplit

import pysparql_anything
from requests.exceptions import RequestException

from ramose._constants import DEFAULT_HTTP_TIMEOUT, FIELD_TYPE_RE, _http_session
from ramose.datatype import DataType


class Operation:
    def __init__(
        self,
        op_complete_url,
        op_key,
        i,
        tp,
        sparql_http_method,
        addon,
        format_map=None,
        sources_map=None,
        engine="sparql",
    ):
        """This class is responsible for materialising a API operation to be run against a SPARQL endpoint
        (or, depending on configuration, through the SPARQL.Anything engine).

        It takes in input a full URL referring to a call to an operation (parameter 'op_complete_url'),
        the particular shape representing an operation (parameter 'op_key'), the definition (in JSON) of such
        operation (parameter 'i'), the URL of the triplestore to contact (parameter 'tp'), the HTTP method
        to use for the SPARQL request (parameter 'sparql_http_method', set to either 'get' or 'post'), the path
        of the Python file which defines additional functions for use in the operation (parameter 'addon'), and formats
        with the names of the corresponding functions responsible for converting CSV data into the specified formats
        (parameter 'format').
        It also accepts a mapping of named sources to endpoint URLs referenced by @@with directives
        (parameter 'sources_map') and the engine identifier selecting the execution
        backend (parameter 'engine')."""
        self.url_parsed = urlsplit(op_complete_url)
        self.op_url = self.url_parsed.path
        self.op = op_key
        self.i = i
        self.tp = tp
        self.sparql_http_method = sparql_http_method
        self.addon = addon
        self.format = format_map or {}
        self.sources_map = sources_map or {}
        self.engine = engine
        self._sa_engine = None

        self.operation = {"=": eq, "<": lt, ">": gt}

        self.dt = DataType()

    @staticmethod
    def get_content_type(ct):
        """It returns the mime type of a given textual representation of a format, being it either
        'csv' or 'json."""
        content_type = ct

        if ct == "csv":
            content_type = "text/csv"
        elif ct == "json":
            content_type = "application/json"

        return content_type

    def conv(self, s, query_string, c_type="text/csv"):
        """This method takes a string representing a CSV document and converts it in the requested format according
        to what content type is specified as input."""

        content_type = Operation.get_content_type(c_type)

        # Overwrite if requesting a particular format via the URL
        if "format" in query_string:
            req_formats = query_string["format"]

            for req_format in req_formats:
                content_type = Operation.get_content_type(req_format)

                if req_format in self.format:
                    converter_func = getattr(self.addon, self.format[req_format])
                    return converter_func(s), content_type
        elif "default_format" in self.i:
            default_fmt = self.i["default_format"].strip()
            content_type = Operation.get_content_type(default_fmt)
            if default_fmt in self.format:
                converter_func = getattr(self.addon, self.format[default_fmt])
                return converter_func(s), content_type

        # If a non built-in format was requested but no converter ran,
        # force CSV Content-Type instead of echoing the requested token.
        if content_type not in ("text/csv", "application/json"):
            content_type = "text/csv"

        if "application/json" in content_type:
            with StringIO(s) as f:
                r = [dict(i) for i in DictReader(f)]

                # See if any restructuring of the final JSON is required
                r = Operation.structured(query_string, r)

                return dumps(r, ensure_ascii=False, indent=4), content_type
        else:
            return s, content_type

    @staticmethod
    def pv(i, r=None):
        """This method returns the plain value of a particular item 'i' of the result returned by the SPARQL query.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[1]
        return Operation.pv(r[i])

    @staticmethod
    def tv(i, r=None):
        """This method returns the typed value of a particular item 'i' of the result returned by the SPARQL query.
        The type associated to that value is actually specified by means of the particular configuration provided
        in the specification file of the API - field 'field_type'.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[0]
        return Operation.tv(r[i])

    @staticmethod
    def do_overlap(r1, r2):
        """This method returns a boolean that says if the two ranges (i.e. two pairs of integers) passed as inputs
        actually overlap one with the other."""
        r1_s, r1_e = r1
        r2_s, r2_e = r2

        return r1_s <= r2_s <= r1_e or r2_s <= r1_s <= r2_e

    @staticmethod
    def get_item_in_dict(d_or_l, key_list, prev=None):
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
                        res = Operation.get_item_in_dict(d[key], key_list[1:], res)

        return res

    @staticmethod
    def add_item_in_dict(d_or_l, key_list, item, idx):
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
                    Operation.add_item_in_dict(d_or_l[key], key_list[1:], item, idx)

    @staticmethod
    def structured(params, json_table):
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
                        for idx, v in enumerate(v_list):
                            if op_type == "array":
                                if isinstance(v, str):
                                    Operation.add_item_in_dict(row, keys, v.split(separator) if v != "" else [], idx)
                            elif op_type == "dict":
                                new_fields = entries[1:]
                                new_fields_max_split = len(new_fields) - 1
                                if isinstance(v, str):
                                    new_values = v.split(separator, new_fields_max_split)
                                    Operation.add_item_in_dict(
                                        row,
                                        keys,
                                        dict(zip(new_fields, new_values, strict=False)) if v != "" else {},
                                        idx,
                                    )
                                elif isinstance(v, list):
                                    new_list = []
                                    for i in v:
                                        new_values = i.split(separator, new_fields_max_split)
                                        new_list.append(dict(zip(new_fields, new_values, strict=False)))
                                    Operation.add_item_in_dict(row, keys, new_list, idx)

        return json_table

    def preprocess(self, par_dict, op_item, addon):
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

    def postprocess(self, res, op_item, addon):
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
    def _apply_require(header, result, fields):
        """Exclude rows with empty values in the specified fields."""
        for field in fields:
            field_idx = header.index(field)
            result = [row for row in result if Operation.pv(field_idx, row) not in (None, "")]
        return result

    def _apply_filter(self, header, result, fields):
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
    def _apply_sort(header, result, fields):
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

    def handling_params(self, params, table):
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

        if "exclude" in params or "require" in params:
            fields = params["exclude"] if "exclude" in params else params["require"]
            result = self._apply_require(header, result, fields)

        if "filter" in params:
            result = self._apply_filter(header, result, params["filter"])

        if "sort" in params:
            result = self._apply_sort(header, result, params["sort"])

        return [header, *result]

    def type_fields(self, res, op_item):
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

        return [header, *result]

    def remove_types(self, res):
        """This method takes the results 'res' that include also the typed value and returns a version of such
        results without the types that is ready to be stored on the file system."""
        result = [res[0]]
        result.extend(tuple(Operation.pv(idx, row) for idx in range(len(row))) for row in res[1:])
        return result

    @staticmethod
    def _is_directive(line):
        return line.strip().startswith("@@")

    @staticmethod
    def _parse_directive_args(tokens, param_names, defaults=None):
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
                        raise ValueError(f"Duplicate parameter {key!r}")
                    seen_keyword = True
                    result[key] = value
                    continue
            if seen_keyword:
                raise ValueError(f"Positional argument {token!r} cannot follow keyword argument")
            if positional_index >= len(param_names):
                raise ValueError(f"Unexpected argument {token!r}")
            result[param_names[positional_index]] = token
            positional_index += 1

        for name, default in defaults.items():
            if name not in result:
                result[name] = default

        missing = [name for name in param_names if name not in result]
        if missing:
            raise ValueError(f"Missing required parameter(s): {', '.join(missing)}")

        return result

    def _handle_directive_with(self, parts):
        args = Operation._parse_directive_args(parts[1:], ["source"])
        name = args["source"]
        if name not in self.sources_map:
            raise ValueError(f"Unknown source '{name}' in @@with; declare it in #sources.")
        return self.sources_map[name], None

    @staticmethod
    def _handle_directive_endpoint(parts):
        args = Operation._parse_directive_args(parts[1:], ["target"])
        return args["target"], None

    @staticmethod
    def _handle_directive_join(parts):
        args = Operation._parse_directive_args(parts[1:], ["left_var", "right_var"], defaults={"type": "inner"})
        return None, ("JOIN", args["left_var"], args["right_var"], args["type"].lower())

    @staticmethod
    def _handle_directive_values(parts):
        tokens = parts[1:]
        if not tokens:
            raise ValueError("@@values needs at least one variable")
        return None, ("VALUES_INJECT", tokens)

    @staticmethod
    def _handle_directive_foreach(parts):
        args = Operation._parse_directive_args(parts[1:], ["variable", "placeholder"], defaults={"wait": "0"})
        var_name = args["variable"]
        if not var_name.startswith("?"):
            raise ValueError(f"@@foreach variable must start with '?', got {var_name!r}")
        try:
            delay = float(args["wait"])
        except ValueError:
            raise ValueError(f"Invalid wait value in @@foreach: {args['wait']!r}") from None
        return None, ("FOREACH", var_name, args["placeholder"], delay)

    def _parse_steps(self, text, default_endpoint, params):
        """
        Returns a list of steps:
          - ("QUERY", endpoint_url, query_text)
          - ("JOIN", left_var, right_var, how)       # how in {"inner","left"}
          - ("REMOVE", [vars])
          - ("VALUES_INJECT", [vars])                # @@values ?var1 ?var2 ...
          - ("FOREACH", var_name, placeholder, delay)  # @@foreach ?var placeholder [wait=N]
        """
        steps = []
        cur_query = []
        current_endpoint = default_endpoint

        directive_handlers = {
            "with": self._handle_directive_with,
            "endpoint": self._handle_directive_endpoint,
            "join": self._handle_directive_join,
            "remove": lambda parts: (None, ("REMOVE", parts[1:])),
            "values": self._handle_directive_values,
            "foreach": self._handle_directive_foreach,
        }

        def flush_query():
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

            body = line.strip()[2:].strip()
            parts = body.split()
            cmd = parts[0].lower()

            handler = directive_handlers.get(cmd)
            if handler is None:
                raise ValueError(f"Unknown directive @@{cmd}")

            new_endpoint, step = handler(parts)
            if new_endpoint is not None:
                current_endpoint = new_endpoint
            if step is not None:
                steps.append(step)

        flush_query()
        return steps

    def _run_sparql_dicts(self, endpoint_url, query_text):
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
            raise RuntimeError(f"SPARQL request failed: {e}") from e

        r.encoding = "utf-8"
        if r.status_code != 200:
            raise RuntimeError(f"SPARQL {r.status_code}: {r.reason}")
        text = r.content.decode("utf-8-sig", errors="replace")
        list_of_lines = text.splitlines()
        return list(DictReader(list_of_lines))

    @staticmethod
    def _normalize_sparql_json_resultset(result):
        """Convert a SPARQL JSON ResultSet dict to a list of flat dicts."""
        vars_ = result["head"].get("vars") or []
        return [
            {v: (b[v].get("value") if isinstance(b.get(v), dict) else b.get(v)) for v in vars_}
            for b in result["results"].get("bindings", [])
        ]

    @staticmethod
    def _normalize_columnar_dict(result):
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

    def _run_sparql_anything_dicts(self, query_text, values=None):
        """
        Execute a SPARQL Anything SELECT query via PySPARQL-Anything and return
        a list of dicts (one per row), in the same shape as _run_sparql_dicts.

        query_text: full SPARQL (Anything) query string
                        (typically containing SERVICE <x-sparql-anything:...>).
        values: optional dict of template parameters for the query
                    (name -> value), passed to SPARQL Anything's `values=`.
        """
        # Lazily create and cache the engine so we don't re-initialise the JVM
        if self._sa_engine is None:
            self._sa_engine = pysparql_anything.SparqlAnything()

        kwargs = {"query": query_text}
        if values:
            kwargs["values"] = {str(k): str(v) for k, v in values.items()}

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

    def _run_query_dicts(self, endpoint_url, query_text):
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

    def _inject_values_clause(self, query_text, vars_, acc_rows):
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
        def fmt(x):
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
    def _drop_columns(rows, vars_):
        if not rows:
            return rows
        vars_set = {v.lstrip("?") for v in vars_}
        return [{k: v for k, v in r.items() if k not in vars_set and ("?" + k) not in vars_set} for r in rows]

    def _norm_join_key(self, v):
        if v is None:
            return None
        s = str(v).strip()
        # unify scheme for w3id IRIs (and similar)
        if s.startswith("http://"):
            s = "https://" + s[len("http://") :]
        # drop a single trailing slash for stability
        return s.removesuffix("/")

    def _join(self, left_rows, right_rows, lkey, rkey, how="inner"):
        """
        Merge two row sets on lkey (from left_rows) and rkey (from right_rows).
        - lkey/rkey may be passed as '?var' or 'var' -> we normalize to bare names.
        - Keys are normalized with _norm_join_key (e.g., http -> https, trim slash).
        - When 'left', all left rows are preserved even if no match on the right.
        - Right-hand columns are copied into the merged row; collisions are avoided.
        """
        # 1) Normalize column names (strip leading '?')
        lcol = lkey.lstrip("?")
        rcol = rkey.lstrip("?")

        left_rows = left_rows or []
        right_rows = right_rows or []

        # 2) Build an index for right_rows on normalized rcol values
        rindex = {}
        for r in right_rows:
            rk = self._norm_join_key(r.get(rcol))
            if rk is None:
                continue
            rindex.setdefault(rk, []).append(r)

        # determine right columns to copy (excluding the join key)
        right_cols = [c for c in (right_rows[0].keys() if right_rows else []) if c != rcol]

        out = []
        for left_row in left_rows:
            lk = self._norm_join_key(left_row.get(lcol))
            matches = rindex.get(lk, [])
            if matches:
                for r in matches:
                    merged = dict(left_row)
                    for c in right_cols:
                        rv = r.get(c)
                        if rv is None:
                            continue
                        if c not in merged or merged[c] in ("", None):
                            merged[c] = rv
                        else:
                            alt = f"{c}_r"
                            if alt not in merged or merged[alt] in ("", None):
                                merged[alt] = rv
                    out.append(merged)
            elif how == "left":
                out.append(dict(left_row))
        return out

    def _finalize_result(self, csv_rows, content_type):
        """Run the shared pipeline: type fields, postprocess, filter, remove types, convert format."""
        res = self.type_fields(csv_rows, self.i)
        if self.addon is not None:
            res = self.postprocess(res, self.i, self.addon)
        q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
        res = self.handling_params(q_string, res)
        res = self.remove_types(res)
        s_res = StringIO()
        writer(s_res).writerows(res)
        body, ctype = self.conv(s_res.getvalue(), q_string, content_type)
        return 200, body, ctype

    @staticmethod
    def _header_from_field_type(op_item, acc):
        # Respect #field_type order if provided, else derive from data
        if "field_type" in op_item:
            # FIELD_TYPE_RE is global in this file
            return [f for (_, f) in findall(FIELD_TYPE_RE, op_item["field_type"])]
        # fallback to keys of first row
        return list(acc[0].keys()) if acc else []

    @staticmethod
    def _to_csv_rows(header, acc):
        rows = [header]
        rows.extend([d.get(h, "") for h in header] for d in acc)
        return rows

    def _extract_params(self):
        """Extract URL parameters and apply type conversions based on the operation spec."""
        par_dict = {}
        par_man = match(self.op, self.op_url).groups()  # type: ignore[union-attr]
        for idx, par in enumerate(findall("{([^{}]+)}", self.i["url"])):
            try:
                par_type = self.i[par].split("(")[0]
                par_value = par_man[idx] if par_type == "str" else self.dt.get_func(par_type)(par_man[idx])
            except KeyError:
                par_value = par_man[idx]
            par_dict[par] = par_value
        return par_dict

    def _exec_sparql_anything_single(self, par_dict, content_type):
        """Execute a single SPARQL Anything query and return the finalized result."""
        query = self.i["sparql"]
        for param, val in par_dict.items():
            query = query.replace(f"[[{param}]]", str(val))
        rows = self._run_sparql_anything_dicts(query)
        header = self._header_from_field_type(self.i, rows or [])
        csv_rows = self._to_csv_rows(header, rows or [])
        return self._finalize_result(csv_rows, content_type)

    def _exec_standard_sparql(self, par_dict, content_type):
        """Execute standard SPARQL queries, handling parameter combinations via cartesian product."""
        # Wrap scalar values in lists for cartesian product
        par_dict = {k: v if isinstance(v, list) else [v] for k, v in par_dict.items()}

        parameters_comb = [
            dict(zip(par_dict.keys(), combination, strict=False)) for combination in product(*par_dict.values())
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

            if r.status_code != 200:
                return r.status_code, f"HTTP status code {r.status_code}: {r.reason}", "text/plain"

            # Re-encode to handle non-UTF8 characters in splitlines
            list_of_lines = [line.decode("utf-8") for line in r.text.encode("utf-8").splitlines()]

            # Include the CSV header only from the first response
            if not include_header_line:
                list_of_lines = list_of_lines[1:]
            include_header_line = False

            list_of_res += list_of_lines

        return self._finalize_result(list(reader(list_of_res)), content_type)

    def _exec_foreach_query(self, endpoint_url, qtxt, var_name, placeholder, delay, acc):
        """Run one query per distinct value collected from the accumulator (@@foreach)."""
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

    def _exec_multi_source_query_step(self, endpoint_url, qtxt, state):
        """Handle a QUERY step in the multi-source pipeline."""
        if state["pending_foreach"] is not None:
            var_name, placeholder, delay = state["pending_foreach"]
            rows = self._exec_foreach_query(endpoint_url, qtxt, var_name, placeholder, delay, state["acc"])
            state["pending_foreach"] = None
            state["pending_values_vars"] = None
        else:
            if state["pending_values_vars"]:
                qtxt = self._inject_values_clause(qtxt, state["pending_values_vars"], state["acc"])
                state["pending_values_vars"] = None
            rows = self._run_query_dicts(endpoint_url, qtxt)

        if state["acc"] is None:
            state["acc"] = rows
        elif state["pending_join"]:
            lvar, rvar, how = state["pending_join"]
            state["acc"] = self._join(state["acc"], rows, lvar, rvar, how)
            state["pending_join"] = None
        else:
            raise ValueError("Multiple QUERY steps without an explicit @@join directive")

    def _exec_multi_source(self, par_dict, content_type):
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
                state["acc"] = self._drop_columns(state["acc"] or [], st[1])
            elif tag == "VALUES_INJECT":
                state["pending_values_vars"] = st[1]
            elif tag == "FOREACH":
                state["pending_foreach"] = (st[1], st[2], st[3])
            else:
                raise RuntimeError(f"Unknown step tag {tag}")

        header = self._header_from_field_type(self.i, state["acc"] or [])
        csv_rows = self._to_csv_rows(header, state["acc"] or [])
        return self._finalize_result(csv_rows, content_type)

    @staticmethod
    def _format_error(sc, e, prefix=""):
        """Format an error response tuple with traceback line info."""
        tb = e.__traceback__
        line = tb.tb_lineno if tb else "?"
        msg = f"HTTP status code {sc}: {prefix}{type(e).__name__}: {e} (line {line})"
        return sc, msg, "text/plain"

    def exec(self, method="get", content_type="application/json"):
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
            return 405, f"HTTP status code 405: '{str_method}' method not allowed", "text/plain"

        try:
            return self._dispatch_exec(content_type)
        except TimeoutError as e:
            return self._format_error(408, e, "request timeout - ")
        except TypeError as e:
            return self._format_error(400, e, "parameter in the request not compliant with the type specified - ")
        except Exception as e:  # noqa: BLE001
            return self._format_error(500, e, "something unexpected happened - ")

    def _dispatch_exec(self, content_type):
        """Dispatch to the appropriate execution path based on SPARQL text content."""
        par_dict = self._extract_params()
        if self.addon is not None:
            self.preprocess(par_dict, self.i, self.addon)

        sparql_text = self.i["sparql"]

        if "@@" not in sparql_text:
            if self.engine == "sparql-anything":
                return self._exec_sparql_anything_single(par_dict, content_type)
            return self._exec_standard_sparql(par_dict, content_type)

        try:
            return self._exec_multi_source(par_dict, content_type)
        except ValueError as ve:
            return 400, f"HTTP status code 400: {ve}", "text/plain"
        except RuntimeError as re_err:
            return 502, f"HTTP status code 502: {re_err}", "text/plain"
