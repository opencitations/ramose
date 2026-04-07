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
    def __init__(self, op_complete_url, op_key, i, tp, sparql_http_method, addon,
                 format_map=None, sources_map=None, allow_inline_endpoints=False, engine="sparql"):
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
        (parameter 'sources_map'), a flag controlling whether @@endpoint directives are allowed to override
        endpoints inline (parameter 'allow_inline_endpoints'), and the engine identifier selecting the execution
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
        self.allow_inline_endpoints = allow_inline_endpoints
        self.engine = engine
        self._sa_engine = None

        self.operation = {
            "=": eq,
            "<": lt,
            ">": gt
        }

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

        d_list = [d_or_l] if type(d_or_l) is dict else d_or_l

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

            if type(d_or_l) is list:
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
                                if type(v) is str:
                                    Operation.add_item_in_dict(row, keys,
                                                               v.split(separator) if v != "" else [], idx)
                            elif op_type == "dict":
                                new_fields = entries[1:]
                                new_fields_max_split = len(new_fields) - 1
                                if type(v) is str:
                                    new_values = v.split(
                                        separator, new_fields_max_split)
                                    Operation.add_item_in_dict(row, keys,
                                                               dict(
                                                                   zip(new_fields, new_values, strict=False)) if v != "" else {},
                                                               idx)
                                elif type(v) is list:
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

                param_list = ()
                for param_name in params_name:
                    param_list += (result[param_name],)

                # run function
                func = getattr(addon, func_name)
                res = func(*param_list)

                # substitute res to the current parameter in result
                for idx in range(len(res)):
                    result[params_name[idx]] = res[idx]

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

    def handling_params(self, params, table):  # noqa: C901, PLR0912
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
            for field in fields:
                field_idx = header.index(field)
                tmp_result = []
                for row in result:
                    value = Operation.pv(field_idx, row)
                    if value is not None and value != "":
                        tmp_result.append(row)
                result = tmp_result

        if "filter" in params:
            fields = params["filter"]
            for field in fields:
                field_name, field_value = field.split(":", 1)

                try:
                    field_idx = header.index(field_name)
                    flag = field_value[0]
                    if flag in ("<", ">", "="):
                        value = field_value[1:].lower()
                        tmp_result = []
                        for row in result:
                            v_result = Operation.tv(field_idx, row)
                            v_to_compare = self.dt.get_func(type(v_result).__name__)(value)

                            if self.operation[flag](v_result, v_to_compare):
                                tmp_result.append(row)
                        result = tmp_result

                    else:
                        result = list(filter(
                            lambda i: search(field_value.lower(),
                                             Operation.pv(field_idx, i).lower()), result))
                except ValueError:
                    pass  # do nothing

        if "sort" in params:
            fields = sorted(params["sort"], reverse=True)
            field_names = []
            order = []
            for field in fields:
                order_names = findall(r"^(desc|asc)\(([^\(\)]+)\)$", field)
                if order_names:
                    order.append(order_names[0][0])
                    field_names.append(order_names[0][1])
                else:
                    order.append("asc")
                    field_names.append(field)

            for idx in range(len(field_names)):
                field_name = field_names[idx]
                try:
                    desc_order = False
                    if idx < len(order):
                        field_order = order[idx].lower().strip()
                        desc_order = field_order == "desc"

                    field_idx = header.index(field_name)
                    result = sorted(result, key=itemgetter(field_idx), reverse=desc_order)
                except ValueError:
                    pass  # do nothing

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
            for idx in range(len(header)):
                heading = header[idx]
                cur_value = row[idx]
                if type(cur_value) is tuple:
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

    def _parse_steps(self, text, default_endpoint, params):  # noqa: C901, PLR0912, PLR0915
        """
        Returns a list of steps:
          - ("QUERY", endpoint_url, query_text)
          - ("JOIN", left_var, right_var, how)       # how in {"inner","left"}
          - ("REMOVE", [vars])
          - ("WITH", endpoint_url)                   # resolved from sources_map
          - ("ENDPOINT", endpoint_url)               # explicit url (if allowed)
          - ("VALUES_INJECT", [vars])                # @@values ?var1 ?var2 ...
          - ("FOREACH_SETUP", alias, var_name)       # @@values ?var:alias
          - ("FOREACH_MARK", alias, delay_seconds)   # @@foreach alias [delay]
        """
        steps = []
        cur_query = []
        current_endpoint = default_endpoint

        def flush_query():
            if cur_query:
                q = "\n".join(cur_query).strip()
                if not q:
                    cur_query.clear()
                    return
                # parameter substitution [[...]]
                for p, v in params.items():
                    q = q.replace(f"[[{p}]]", str(v))
                steps.append(("QUERY", current_endpoint, q))
                cur_query.clear()

        for raw in text.splitlines():
            line = raw.rstrip("\n")
            if not self._is_directive(line):
                cur_query.append(line)
                continue

            # directive line -> first close any pending query
            flush_query()

            body = line.strip()[2:].strip()  # remove leading @@
            parts = body.split()
            cmd = parts[0].lower()

            if cmd == "with":
                name = parts[1]
                if name not in self.sources_map:
                    raise ValueError(f"Unknown source '{name}' in @@with; declare it in #sources.")
                current_endpoint = self.sources_map[name]

            elif cmd == "endpoint":
                url = parts[1]
                if not self.allow_inline_endpoints:
                    raise ValueError("@@endpoint not allowed (enable #allow_inline_endpoints).")
                current_endpoint = url

            elif cmd == "join":
                left = parts[1]
                right = parts[2]
                how = "inner"
                if len(parts) >= 4 and parts[3].startswith("type="):
                    how = parts[3].split("=", 1)[1].lower()
                steps.append(("JOIN", left, right, how))

            elif cmd == "remove":
                vars_ = parts[1:]
                steps.append(("REMOVE", vars_))

            elif cmd == "values":
                # syntax:
                    # @@values ?var1 ?var2 ...
                    # @@values ?var:alias              -> FOREACH_SETUP (for @@foreach)
                tokens = parts[1:]
                if not tokens:
                    raise ValueError("@@values needs at least one variable")

                alias_specs = [t for t in tokens if ":" in t]
                if alias_specs:
                    # We only support exactly one ?var:alias pair for now
                    if len(tokens) != 1 or len(alias_specs) != 1:
                        raise ValueError(
                            "@@values with alias supports exactly one ?var:alias pair"
                        )
                    var_token = alias_specs[0]
                    var_name, alias = var_token.split(":", 1)
                    steps.append(("FOREACH_SETUP", alias, var_name))
                else:
                    vars_ = tokens
                    steps.append(("VALUES_INJECT", vars_))

            elif cmd == "foreach":
                # syntax: @@foreach alias [delay_seconds]
                if len(parts) < 2:
                    raise ValueError("@@foreach requires an alias name")
                alias = parts[1]
                delay = 0.0
                if len(parts) >= 3:
                    try:
                        delay = float(parts[2])
                    except ValueError:
                        raise ValueError(f"Invalid delay value in @@foreach: {parts[2]!r}") from None
                steps.append(("FOREACH_MARK", alias, delay))

            else:
                raise ValueError(f"Unknown directive @@{cmd}")

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

    def _run_sparql_anything_dicts(self, query_text, values=None):  # noqa: C901, PLR0912
        """
        Execute a SPARQL Anything SELECT query via PySPARQL-Anything and return
        a list of dicts (one per row), in the same shape as _run_sparql_dicts.

        query_text: full SPARQL (Anything) query string
                        (typically containing SERVICE <x-sparql-anything:...>).
        values: optional dict of template parameters for the query
                    (name -> value), passed to SPARQL Anything's `values=`.
        """
        # Lazily create and cache the engine so we don't re-initialise the JVM
        engine = getattr(self, "_sa_engine", None)
        if engine is None:
            engine = pysparql_anything.SparqlAnything()
            self._sa_engine = engine

        # Build kwargs for PySPARQL-Anything
        kwargs = {"query": query_text}
        if values:
            # SPARQL Anything expects a dict[str, str]
            kwargs["values"] = {str(k): str(v) for k, v in values.items()}

        # Ask PySPARQL-Anything for a Python dict structure
        result = engine.select(output_type=dict, **kwargs)

        # --- Normalisation to list[dict] -----------------------------------
        # 1) If it's already a list of dicts, just return it.
        if isinstance(result, list):
            if result and isinstance(result[0], dict):
                return result
            # list but not dicts (tuples, etc.): coerce
            return [dict(row) for row in result]

        # 2) If it's not a dict at all, just wrap it as a single-row result.
        if not isinstance(result, dict):
            return [{"result": result}]

        # 3) Try standard SPARQL JSON ResultSet shape: { "head": {vars}, "results": { "bindings": [...] } }
        head = result.get("head")
        results = result.get("results")
        if isinstance(head, dict) and isinstance(results, dict) and "bindings" in results:
            vars_ = head.get("vars") or []
            rows = []
            for b in results.get("bindings", []):
                row = {}
                for v in vars_:
                    cell = b.get(v)
                    if isinstance(cell, dict):
                        # standard SPARQL JSON: { "type": "...", "value": "..." , ... }
                        row[v] = cell.get("value")
                    else:
                        row[v] = cell
                rows.append(row)
            return rows

        # 4) Otherwise assume it is a mapping column_name -> list-of-values (or scalars)
        rows = []
        cols = list(result.keys())

        # Find maximum column length, if columns are lists/tuples
        max_len = 0
        for c in cols:
            v = result[c]
            if isinstance(v, (list, tuple)):
                max_len = max(max_len, len(v))

        if max_len:
            for i in range(max_len):
                row = {}
                for c in cols:
                    v = result[c]
                    if isinstance(v, (list, tuple)):
                        row[c] = v[i] if i < len(v) else None
                    else:
                        # scalar: repeat in every row
                        row[c] = v
                rows.append(row)
            return rows

        # 5) Fallback: treat the dict as a single-row result
        return [result]

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
        for row in (acc_rows or []):
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
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

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
            s = "https://" + s[len("http://"):]
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

    def exec(self, method="get", content_type="application/json"):  # noqa: C901, PLR0911, PLR0912, PLR0915
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
        m = self.i["method"].split()

        if str_method in m:
            try:
                par_dict = {}
                par_man = match(self.op, self.op_url).groups()  # type: ignore[union-attr]
                for idx, par in enumerate(findall("{([^{}]+)}", self.i["url"])):
                    try:
                        par_type = self.i[par].split("(")[0]
                        par_value = par_man[idx] if par_type == "str" else self.dt.get_func(par_type)(par_man[idx])
                    except KeyError:
                        par_value = par_man[idx]
                    par_dict[par] = par_value

                if self.addon is not None:
                    self.preprocess(par_dict, self.i, self.addon)

                sparql_text = self.i["sparql"]

                if "@@" not in sparql_text:
                    # Fast path: single-query (legacy behavior)

                    if self.engine == "sparql-anything":
                        query = sparql_text
                        for param, val in par_dict.items():
                            query = query.replace(f"[[{param}]]", str(val))
                        rows = self._run_sparql_anything_dicts(query)
                        header = self._header_from_field_type(self.i, rows or [])
                        csv_rows = self._to_csv_rows(header, rows or [])
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

                    # Handle in case the parameters are lists, we need to generate all possible combinations
                    par_dict = {p_k: [par_dict[p_k]] if not isinstance(par_dict[p_k], list) else par_dict[p_k] for p_k in par_dict}
                    combinations = product(*par_dict.values())

                    parameters_comb = [
                        dict(zip(list(par_dict.keys()), list(combination), strict=False))
                        for combination in combinations
                    ]

                    # the __parameters_comb__ varaible is a list of dictionaries,
                    # each dictionary stores a possible combination of parameter values
                    #
                    # Example: {"id":"5","area":["A1","A2"]}  ->  [  {"id":"5","area":"A1"}, {"id":"5","area":"A2"} ]
                    # Example: {"id":"5","area":"A1"}  ->  [  {"id":"5","area":"A1"} ]

                    # iterate over __parameters_comb__

                    list_of_res = []
                    include_header_line = True
                    sc = 200
                    for par_dict in parameters_comb:

                        query = self.i["sparql"]
                        for param in par_dict:
                            query = query.replace(f"[[{param}]]", str(par_dict[param]))

                        # GET and POST are sync
                        # TODO: use threads to make it parallel

                        if self.sparql_http_method == "get":
                            r = _http_session.get(self.tp + "?query=" + quote(query),
                                    headers={"Accept": "text/csv"}, timeout=DEFAULT_HTTP_TIMEOUT)
                        else:
                            r = _http_session.post(self.tp, data=query, headers={"Accept": "text/csv",
                                                                   "Content-Type": "application/sparql-query"}, timeout=DEFAULT_HTTP_TIMEOUT)
                        r.encoding = "utf-8"

                        sc = r.status_code
                        if sc == 200:
                            # This line has been added to avoid a strage behaviour of the 'splitlines' method in
                            # presence of strange characters (non-UTF8).
                            list_of_lines = [line.decode("utf-8") for line in r.text.encode("utf-8").splitlines()]

                        else:
                            return sc, f"HTTP status code {sc}: {r.reason}", "text/plain"

                        # each res will have a list of list_of_line
                        # include the header of the first result only
                        if not include_header_line:
                            list_of_lines = list_of_lines[1:]
                        include_header_line = False

                        list_of_res += list_of_lines

                    res = self.type_fields(list(reader(list_of_res)), self.i)
                    if self.addon is not None:
                        res = self.postprocess(res, self.i, self.addon)
                    q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
                    res = self.handling_params(q_string, res)
                    res = self.remove_types(res)
                    s_res = StringIO()
                    writer(s_res).writerows(res)
                    return (sc, *self.conv(s_res.getvalue(), q_string, content_type))

                # Multi-source path: @@ directives present
                try:
                    steps = self._parse_steps(sparql_text, self.tp, par_dict)

                    acc = None     # list of dict rows
                    pending_join = None
                    pending_values_vars = None

                    foreach_sources = {}     # alias -> column name (without '?')
                    pending_foreach = None   # (alias, delay_seconds)

                    for st in steps:
                        tag = st[0]

                        if tag == "QUERY":
                            _, endpoint_url, qtxt = st

                            # FOREACH mode: run one query per value
                            if pending_foreach is not None:
                                alias, delay = pending_foreach

                                if alias not in foreach_sources:
                                    raise ValueError(
                                        f"@@foreach refers to unknown alias '{alias}'. "
                                        f"Declare it with @@values ?var:{alias} before @@foreach."
                                    )

                                source_col = foreach_sources[alias]  # e.g. "br"

                                # Collect distinct non-empty values from the accumulator
                                values = []
                                seen = set()
                                for row in (acc or []):
                                    v = row.get(source_col)
                                    if v and v not in seen:
                                        seen.add(v)
                                        values.append(v)

                                all_rows = []
                                for idx_val, val in enumerate(values):
                                    # Substitute [[alias]] in the query text
                                    q_one = qtxt.replace(f"[[{alias}]]", str(val))
                                    sub_rows = self._run_query_dicts(endpoint_url, q_one)
                                    if sub_rows:
                                        all_rows.extend(sub_rows)
                                    # Sleep between calls if requested
                                    if delay and idx_val + 1 < len(values):
                                        time.sleep(delay)

                                rows = all_rows
                                # FOREACH applies only to this single QUERY
                                pending_foreach = None
                                # In FOREACH mode we ignore any pending VALUES_INJECT
                                pending_values_vars = None

                            else:
                                # Normal multi-source behaviour
                                if pending_values_vars:
                                    # acc is the current accumulator rows
                                    qtxt = self._inject_values_clause(qtxt, pending_values_vars, acc)
                                    pending_values_vars = None  # only affects this single query
                                rows = self._run_query_dicts(endpoint_url, qtxt)

                            if acc is None:
                                # first query defines the accumulator
                                acc = rows
                            elif pending_join:
                                lvar, rvar, how = pending_join
                                acc = self._join(acc, rows, lvar, rvar, how)
                                pending_join = None
                            else:
                                raise ValueError(
                                    "Multiple QUERY steps without an explicit @@join directive"
                                )

                        elif tag == "JOIN":
                            pending_join = (st[1], st[2], st[3] if len(st) > 3 and st[3] else "inner")

                        elif tag == "REMOVE":
                            _, vars_ = st
                            acc = self._drop_columns(acc or [], vars_)

                        elif tag == "VALUES_INJECT":
                            pending_values_vars = st[1]

                        elif tag == "FOREACH_SETUP":
                            _, alias, var_name = st
                            foreach_sources[alias] = var_name.lstrip("?")

                        elif tag == "FOREACH_MARK":
                            _, alias, delay = st
                            pending_foreach = (alias, delay)

                        else:
                            raise RuntimeError(f"Unknown step tag {tag}")

                    # Convert merged dict rows -> CSV rows; then run the usual pipeline
                    header = self._header_from_field_type(self.i, acc or [])
                    csv_rows = self._to_csv_rows(header, acc or [])

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

                except ValueError as ve:
                    sc = 400
                    return sc, f"HTTP status code {sc}: {ve}", "text/plain"
                except RuntimeError as re_err:
                    sc = 502
                    return sc, f"HTTP status code {sc}: {re_err}", "text/plain"

            except TimeoutError as e:
                sc = 408
                tb = e.__traceback__
                return sc, "HTTP status code {}: request timeout - {}: {} (line {})".format(sc, type(e).__name__, e,
                     tb.tb_lineno if tb else "?"), "text/plain"
            except TypeError as e:
                sc = 400
                tb = e.__traceback__
                return sc, "HTTP status code {}: " \
                    "parameter in the request not compliant with the type specified - {}: {} (line {})".format(sc, type(e).__name__, e,
                     tb.tb_lineno if tb else "?"), "text/plain"
            except Exception as e:  # noqa: BLE001
                sc = 500
                tb = e.__traceback__
                return sc, "HTTP status code {}: something unexpected happened - {}: {} (line {})".format(sc, type(e).__name__, e,
                     tb.tb_lineno if tb else "?"), "text/plain"
        else:
            sc = 405
            return sc, f"HTTP status code {sc}: '{str_method}' method not allowed", "text/plain"
