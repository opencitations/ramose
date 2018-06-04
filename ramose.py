#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2018, Silvio Peroni <essepuntato@gmail.com>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

__author__ = 'essepuntato'

from re import search, DOTALL, findall, sub, match, split
from requests import get, post, put, delete
from csv import DictReader, reader, writer
from json import dumps
from io import StringIO
from sys import exc_info, maxsize, path
from collections import OrderedDict
from markdown import markdown
from importlib import import_module
from urllib.parse import parse_qs, urlsplit, quote
from operator import itemgetter, gt, eq, lt
from dateutil.parser import parse
from datetime import datetime
from isodate import parse_duration
from argparse import ArgumentParser
from os.path import abspath, dirname, basename
from os import sep

FIELD_TYPE_RE = "([^\(\s]+)\(([^\)]+)\)"
PARAM_NAME = "{([^{}\(\)]+)}"


class APIManager(object):

    # Hash format: START
    @staticmethod
    def process_hashformat(file_path):
        """This method takes in input a path of a file containing a document specified in Hash Format (see
        https://github.com/opencitations/hf), and returns its representation as a dictionary."""
        result = []

        with open(file_path, "rU") as f:
            first_field_name = None
            cur_object = None
            cur_field_name = None
            cur_field_content = None
            for line in f.readlines():
                cur_matching = search("^#([^\s]+)\s(.+)$", line, DOTALL)
                if cur_matching is not None:
                    cur_field_name = cur_matching.group(1)
                    cur_field_content = cur_matching.group(2)

                    # If both the name and the content are defined, continue to process
                    if cur_field_name and cur_field_content:
                        # Identify the separator key
                        if first_field_name is None:
                            first_field_name = cur_field_name

                        # If the current field is equal to the separator key,
                        # then create a new object
                        if cur_field_name == first_field_name:
                            # If there is an already defined object, add it to the
                            # final result
                            if cur_object is not None:
                                result += [cur_object]
                            cur_object = {}

                        # Add the new key to the object
                        cur_object[cur_field_name] = cur_field_content
                elif cur_object is not None and len(cur_object) > 0:
                    cur_object[cur_field_name] += line

            # Insert the last object in the result
            if cur_object is not None and len(cur_object) > 0:
                result += [cur_object]

        # Clean the final \n
        for item in result:
            for key in item:
                item[key] = item[key].rstrip()

        return result
    # Hash format: END

    # HTML documentation: START
    def __title(self):
        """This method returns the title string defined in the API specification."""
        return self.conf_json[0]["title"]

    def __header(self):
        """This method builds the header of the API documentation"""
        result = ""

        i = self.conf_json[0]
        result += """# %s
**Version:** %s
<br />
**API URL:** [%s](%s)
<br />
**Contact:** %s
<br />
**License:** %s

## <a id="toc"></a>Table of content

1. [Description](#description)
2. [Parameters](#parameters)
3. [Operations](#operations)<ul>%s</ul>

## <a id="description"></a>1. Description [back to toc](#toc)

%s

%s""" % \
                  (i["title"], i["version"], i["base"] + i["url"], i["base"] + i["url"], i["contacts"], i["license"],
                   "".join(["<li>[%s](#%s): %s</li>" % (op["url"], op["url"], op["description"].split("\n")[0])
                            for op in self.conf_json[1:]]),
                   i["description"], self.__parameters())
        return markdown(result)

    def __parameters(self):
        result = """## <a id="parameters"></a>2. Parameters [back to toc](#toc)

Parameters can be used to filter and control the results returned by the API. They are passed as normal HTTP parameters in the URL of the call. They are:

1. `exclude=<field_name>`: all the rows that have an empty value in the `<field_name>` specified are removed from the result set - e.g. `exclude=doi` remove all the rows that do not have any string specified in the `doi` field.

2. `filter=<field_name>:<operator><value>`: only the rows compliant with `<value>` are kept in the result set. The parameter `<operation>` is not mandatory. If it is not specified, `<value>` is interpreted as a regular expression, otherwise it is compared according to the particular type associated `<field_name>`, as declared in the API specification - see the definition of the *fields* in the [permitted operations](#operations). Possible operators are "=", "<", and ">". For instance, `filter=title:semantics?` returns all the rows that contain the string "semantic" or "semantics" in the field `title`, while `filter=date:>2016-05` returns all the rows that have a `date` greater than May 2016.

3. `sort=<order>(<field_name>)`: sort in ascending (`<order>` set to "asc") or descending (`<order>` set to "desc") order the rows in the result set according to the values in `<field_name>`. For instance, `sort=desc(date)` sorts all the rows according to the value specified in the field `date` in descending order.

It is possible to specify one or more filtering operation of the same kind (e.g. `exclude=doi&exclude=title`). In addition, these filtering operations are applied in the order presented above - first all the `exclude` operation, then all the `filter` operations, and finally all the `sort` operation.

Example: `<api_operation_url>?exclude=doi&filter=date:>2015&sort=desc(date)`."""
        return markdown(result)

    def __operations(self):
        """This method returns the description of all the operations defined in the API."""
        result = """## 3. Operations [back to toc](#toc)
The operations that this API implements are:
"""
        ops = "\n"

        for op in self.conf_json[1:]:
            params = []
            for p in findall(PARAM_NAME, op["url"]):
                p_type = "str"
                p_shape = ".+"
                if p in op:
                    p_type, p_shape = findall("^\s*([^\(]+)\((.+)\)\s*$", op[p])[0]

                params.append("<em>%s</em>: type <em>%s</em>, regular expression shape <code>%s</code>" % (p, p_type, p_shape))
            result += "\n* [%s](#%s): %s" % (op["url"], op["url"], op["description"].split("\n")[0])
            ops += """<div id="%s">
<h3>%s <a href="#operations">back to operations</a></h3>

%s

<p><strong>Accepted HTTP method(s):</strong> %s</p>
<p class="params"><strong>Parameter(s):</strong></p><ul><li>%s</li></ul>
<p><strong>Result fields:</strong> %s</p>
<p><strong>Example:</strong> <a target="_blank" href="%s">%s</a></p>
<p class="ex"><strong>Exemplar output (in JSON)</strong></p>
<pre><code>%s</code></pre></div>""" % (op["url"], op["url"], markdown(op["description"]),
                                       ", ".join(split("\s+", op["method"].strip())), "</li><li>".join(params),
                                       ", ".join(["%s <em>(%s)</em>" % (f, t) for t, f in
                                                  findall(FIELD_TYPE_RE, op["field_type"])]),
                                       self.website + self.base_url + op["call"], op["call"], op["output_json"])

        return markdown(result) + ops

    def __footer(self):
        """This method returns the footer of the API documentation."""
        result = """This API and the related documentation has been created with <a href="https://github.com/opencitations/ramose" target="_blank">RAMOSE</a>, the *Restful API Manager Over SPARQL Endpoints*, developed by <a href="http://orcid.org/0000-0003-0530-4305" target="_blank">Silvio Peroni</a>."""
        return markdown(result)

    def __css(self):
        return """
            * {
                font-family: Verdana, Geneva, sans-serif;
            }
            
            body {
                margin: 3%; 
                line-height: 1.5em;
            }
            
            #operations > div {
                border: 1px solid black;
                border-radius: 15px;
                margin-top: 20px;
                margin-left: 1%;
            }
            
            #operations > div > * {
                padding-left: 2%;
            }
            
            #operations > div ul, #operations > div ol {
                padding-left: 4%;
            }
            
            .params {
                margin-bottom: 0;
            }
            
            .params + ul {
                margin-top: 0;
            }
            
            #operations h3 {
                background-color: #246375;
                color: #d8edf3;
                margin-top: 0px;
                margin-bottom: 0px;
                border-radius: 14px 14px 0 0;
                padding: 10px;
            }
            
            pre {
                background-color: #d8edf3;
                padding: 10px;
                margin-top: 0;
                margin-bottom: 0;
                border-radius: 0 0 14px 14px;
                font-family: "Lucida Console", Monaco, monospace;
                overflow-x: scroll;
                font-size: 80%;
                line-height: 1.2em;
            }
            
            p.ex {
                color: #246375;
                background-color: #d8edf3;
                margin-bottom: 0px;
                padding-top: 5px;
                padding-bottom: 5px;
                border-top: 1px solid #246375;
                border-bottom: 1px solid #246375;
            }
            
            header > h2:first-of-type {
                margin-bottom: 5px;
            }
            
            header > ol:first-of-type {
                margin-top: 0;
            }
            
            :not(pre) > code {
                background-color: #ffe6f2;
                border: 1px solid #ff99cc;
                padding: 0 2px 0 2px;
                border-radius: 3px;
            }
            
            *:not(div) > p {
                margin-left: 1.2%;
            }
            
            h1, h2, h3, h4, h5, h6 {
                font-weight: normal;
            }
            
            h2 ~ h2, section > h2 {
                border-top: 1px solid #246375;
                border-left: 1px solid #246375;
                padding-top: 2px;
                padding-left: 1%;
                border-radius: 15px 0 0 0;
                color: #246375;
                margin-top: 40px;
            }
            
            h2 a[href] {
                background-color: #d8edf3;
                color: #246375;
                padding: 1px 3px 1px 3px;
                font-size: 8pt;
                border: 1px solid #246375;
                float: right;
                position:relative;
                top: -3px;
            }
            
            h3 a[href] {
                background-color: #d8edf3;
                color: #246375;
                padding: 1px 3px 1px 3px;
                font-size: 8pt;
                border: 1px solid #246375;
                float: right;
                position:relative;
                top: -11px;
                right: -11px;
                border-radius: 0 14px 0 0;
            }
            
            p {
                overflow-wrap: break-word;
                word-wrap: break-word;
            }
            
            footer {
                margin-top: 20px;
                border-top: 1px solid lightgrey;
                text-align: center;
                color: grey;
                font-size: 9pt;
            }
        """

    def get_htmldoc(self):
        """This method generates the HTML documentation of an API described in an input Hash Format document."""
        return 200, """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <title>%s</title>
        <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
        <meta name="viewport" content="width=device-width" />
        <style>%s</style>
    </head>
    <body>
        <header>%s</header>
        <section id="operations">%s</section>
        <footer>%s</footer>
    </body>
</html>""" % (self.__title(), self.__css(), self.__header(), self.__operations(), self.__footer())

    def store_htmldoc(self, file_path):
        """This method stores the HTML documentation on an API in a file."""
        html = self.get_htmldoc()
        with open(file_path, "w") as f:
            f.write(html)
    # HTML documentation: END

    # Constructor: START
    def __init__(self, conf_files):
        """This is the constructor of the APIManager class. It takes in input a list of API configuration files, each
        defined according to the Hash Format and following a particular structure, and stores all the operations
        defined within a dictionary. The structure of each item in the dictionary of the operations is defined as
        follows:

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
        self.conf = OrderedDict()
        self.tp = None
        for conf_file in conf_files:
            self.conf_json = APIManager.process_hashformat(conf_file)
            self.base_url = None
            for item in self.conf_json:
                if self.base_url is None:
                    self.base_url = item["url"]
                    self.website = item["base"]
                    self.tp = "%s?query=" % item["endpoint"]
                    if "addon" in item:
                        addon_abspath = abspath(dirname(conf_file) + sep + item["addon"])
                        path.append(dirname(addon_abspath))
                        self.addon = import_module(basename(addon_abspath))
                else:
                    self.conf[APIManager.nor_api_url(item, self.base_url)] = item

        self.func = {
            "str": APIManager.str,
            "int": APIManager.int,
            "float": APIManager.float,
            "duration": APIManager.duration,
            "datetime": APIManager.datetime
        }

        self.operation = {
            "=": eq,
            "<": lt,
            ">": gt
        }

        self.http_method = {
            "get": get,
            "put": put,
            "post": post,
            "delete": delete
        }
    # Constructor: END

    # Data type: START
    @staticmethod
    def duration(s):
        """This method returns the data type for durations according to the XML Schema Recommendation
        (https://www.w3.org/TR/xmlschema11-2/#duration) from the input string. In case the input string is None or
        it is empty, an high duration value (i.e. 2000 years) is returned."""
        if s is None and s != "":
            d = parse_duration("PY2000")
        else:
            d = parse_duration(s)

        return datetime(1983, 1, 15) + d

    @staticmethod
    def datetime(s):
        """This method returns the data type for datetime according to the ISO 8601
           (https://en.wikipedia.org/wiki/ISO_8601) from the input string. In case the input string is None or
           it is empty, a low date value (i.e. 0001-01-01) is returned."""
        default = datetime(1, 1, 1, 0, 0)
        if s is None or s == "":
            d = parse("0001-01-01", default=default)
        else:
            d = parse(s, default=default)

        return d

    @staticmethod
    def str(s):
        """This method returns the data type for strings. In case the input string is None, an empty string
        is returned."""
        if s is None:
            l = ""
        else:
            l = str(s).lower()

        return l

    @staticmethod
    def int(s):
        """This method returns the data type for integer numbers from the input string. In case the input string is
        None or it is empty, a low integer value is returned."""
        if s is None or s == "":
            i = -maxsize
        else:
            i = int(s)

        return i

    @staticmethod
    def float(s):
        """This method returns the data type for float numbers from the input string. In case the input string is
            None or it is empty, a low float value is returned."""
        if s is None or s == "":
            f = float(-maxsize)
        else:
            f = float(s)

        return f
    # Data type: END

    # Ancillary methods: START
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
            result = result.replace("{%s}" % term, "%s" % sub("^[^\(]+(\(.+\))$", "\\1", t))

        return "%s%s" % (b, result)

    def best_match(self, u):
        """This method takes an URL of an API call in input and find the API operation URL that best match
        with the API call, if any."""
        cur_u = sub("\?.*$", "", u)
        result = None

        for pat in self.conf:
            if match("^%s$" % pat, cur_u):
                result = pat
                break

        return result

    @staticmethod
    def conv(s, content_type="text/csv"):
        """This method takes a string representing a CSV document and converts it in the requested format according
        to what content type is specified as input."""
        if "application/json" in content_type:
            with StringIO(s) as f:
                r = []
                for i in DictReader(f):
                    r.append(dict(i))
                return dumps(r, ensure_ascii=False, indent=4)
        else:
            return s

    @staticmethod
    def pv(i, r=None):
        """This method returns the plain value of a particular item 'i' of the result returned by the SPARQL query.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[1]
        else:
            return APIManager.pv(r[i])

    @staticmethod
    def tv(i, r=None):
        """This method returns the typed value of a particular item 'i' of the result returned by the SPARQL query.
        The type associated to that value is actually specified by means of the particular configuration provided
        in the specification file of the API - field 'field_type'.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row."""
        if r is None:
            return i[0]
        else:
            return APIManager.tv(r[i])
    # Ancillary methods: END

    # Processing methods: START
    def preprocess(self, op_url, op_item):
        """This method takes the operation URL (e.g. "/api/v1/citations/10.1108/JD-12-2013-0166") and the item of
        the API specification defining the behaviour of that operation, and preprocesses the URL according to the
        functions specified in the '#preprocess' field (e.g. "#preprocess lower(doi)"), which is applied to the
        specified parameters of the URL specified as input of the function in consideration (e.g.
        "/api/v1/citations/10.1108/jd-12-2013-0166", converting the DOI in lowercase).

        It is possible to run multiple functions sequentially by concatenating them with "-->" in the API
        specification document. In this case the output of the function f_i will becomes the input operation URL
        of the function f_i+1.

        Finally, it is worth mentioning that all the functions specified in the "#preprocess" field must return
        a tuple of strings defining how the particular value indicated by the URL parameter must be changed."""
        result = op_url

        if "preprocess" in op_item:
            for pre in [sub("\s+", "", i) for i in op_item["preprocess"].split(" --> ")]:
                match_url = op_item["url"]
                func_name = sub("^([^\(\)]+)\(.+$", "\\1", pre).strip()
                params_name = sub("^.+\(([^\(\)]+)\).*", "\\1", pre).split(",")

                param_list = []
                for param_name in params_name:
                    if param_name in op_item:
                        reg_ex = sub(".+\((.+)\)", "\\1", op_item[param_name])
                    else:
                        reg_ex = ".+"
                    match_url = match_url.replace("{%s}" % param_name, "(%s)" % reg_ex)

                param_list = search(match_url, result).groups()

                # run function
                func = getattr(self.addon, func_name)
                res = func(*param_list)

                # substitute res to the part considered in the url
                for idx in range(len(param_list)):
                    result = result.replace(param_list[idx], res[idx])

        return result

    def postprocess(self, res, op_item):
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
            for pre in [i.strip() for i in op_item["postprocess"].split(" --> ")]:
                func_name = sub("^([^\(\)]+)\(.+$", "\\1", pre).strip()
                params_values = next(reader(sub("^.+\(([^\(\)]+)\).*", "\\1", pre).splitlines(), skipinitialspace=True))
                func = getattr(self.addon, func_name)
                func_params = (result,) + tuple(params_values)
                result = func(*func_params)

        return result

    def handling_params(self, params, table):
        """This method is used for filtering the results that are returned after the post-processing
        phase. In particular, it is possible to:

        1. [exclude=<field_name>] exclude all the rows that have an empty value in the field specified - e.g. the
           "exclude=doi" remove all the rows that do not have any string specified in the "doi" field;

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

        Note that these filtering operations are applied in the order presented above - first the "exclude", then
        the "filter", and finally the "sort". It is possible to specify one or more filtering operation of the
        same kind (e.g. "exclude=doi&exclude=title").
        """
        header = table[0]
        result = table[1:]

        if "exclude" in params:
            fields = params["exclude"]
            for field in fields:
                field_idx = header.index(field)
                tmp_result = []
                for row in result:
                    value = APIManager.pv(field_idx, row)
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
                            v_result = APIManager.tv(field_idx, row)
                            v_to_compare = self.func[type(v_result).__name__](value)

                            if self.operation[flag](v_result, v_to_compare):
                                tmp_result.append(row)
                        result = tmp_result

                    else:
                        result = list(filter(
                            lambda i: search(field_value.lower(), APIManager.pv(field_idx, i).lower()), result))
                except ValueError:
                    pass  # do nothing

        if "sort" in params:
            fields = sorted(params["sort"], reverse=True)
            field_names = []
            order = []
            for field in fields:
                order_names = findall("^(desc|asc)\(([^\(\)]+)\)$", field)
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
                        desc_order = True if field_order == "desc" else False

                    field_idx = header.index(field_name)
                    result = sorted(result, key=itemgetter(field_idx), reverse=desc_order)
                except ValueError:
                    pass  # do nothing

        return [header] + result

    def type_fields(self, res, op_item):
        """It creates a version of the results 'res' that adds, to each value of the fields, the same value interpreted
        with the type specified in the specification file (field 'field_type'). Note that 'str' is used as default in
        case no further specifications are provided."""
        result = []

        cast_func = {}
        header = res[0]
        for heading in header:
            cast_func[heading] = APIManager.str

        if "field_type" in op_item:
            for f, p in findall(FIELD_TYPE_RE, op_item["field_type"]):
                cast_func[p] = self.func[f]

        for row in res[1:]:
            new_row = []
            for idx in range(len(header)):
                heading = header[idx]
                cur_value = row[idx]
                new_row.append((cast_func[heading](cur_value), cur_value))
            result.append(new_row)

        return [header] + result

    def remove_types(self, res):
        """This method takes the results 'res' that include also the typed value and returns a version of such
        results without the types that is ready to be stored on the file system."""
        result = [res[0]]

        for row in res[1:]:
            result.append(tuple(APIManager.pv(idx, row) for idx in range(len(row))))

        return result

    def exec_op(self, op_complete_url, method="get", content_type="application/json"):
        """This method takes in input the url of the call (i.e. the API base URL plus the operation URL), the HTTP
        method to use for the call and the content type to return, and execute the operation as indicated in the
        specification file, by running (in the following order):

        1. the methods to preprocess the query;
        2. the SPARQL query related to the operation called, by using the parameters indicated in the URL;
        3. the specification of all the types of the various rows returned;
        4. the methods to postprocess the result;
        5. the application of the filter to remove, filter, sort the result;
        6. the removal of the types added at the step 3, so as to have a data structure ready to be returned;
        7. the conversion in the format requested by the user."""
        str_method = method.lower()

        url_parsed = urlsplit(op_complete_url)
        op_url = url_parsed.path

        op = self.best_match(op_url)
        if op is not None:
            i = self.conf[op]
            m = i["method"].split()
            if str_method in m:
                try:
                    op_url = self.preprocess(op_url, i)

                    query = i["sparql"]
                    par = findall("{([^{}]+)}", i["url"])
                    par_man = match(op, op_url).groups()
                    for idx in range(len(par)):
                        try:
                            par_type = i[par[idx]].split("(")[0]
                            if par_type == "str":
                                par_value = par_man[idx]
                            else:
                                par_value = self.func[par_type](par_man[idx])
                        except KeyError:
                            par_value = par_man[idx]
                        query = query.replace("[[%s]]" % par[idx], str(par_value))

                    r = get(self.tp + quote(query), headers={"Accept": "text/csv"})
                    sc = r.status_code
                    if sc == 200:
                        res = self.type_fields(list(reader(r.text.splitlines())), i)
                        res = self.postprocess(res, i)
                        res = self.handling_params(parse_qs(quote(url_parsed.query, safe="&=")), res)
                        res = self.remove_types(res)
                        s_res = StringIO()
                        writer(s_res).writerows(res)
                        return sc, APIManager.conv(s_res.getvalue(), content_type)
                    else:
                        return sc, "HTTP status code %s: %s" % (sc, r.reason)
                except TimeoutError:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 408
                    return sc, "HTTP status code %s: request timeout - %s: %s (line %s)" % \
                           (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno)
                except TypeError:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 400
                    return sc, "HTTP status code %s: " \
                               "parameter in the request not compliant with the type specified - %s: %s (line %s)" % \
                               (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno)
                except:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 500
                    return sc, "HTTP status code %s: something unexpected happened - %s: %s (line %s)" % \
                           (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno)
            else:
                sc = 405
                return sc, "HTTP status code %s: '%s' method not allowed" % (sc, str_method)
        else:
            sc = 404
            return sc, "HTTP status code %s: the operation requested does not exist" % sc


if __name__ == "__main__":
    arg_parser = ArgumentParser("ramose.py", description="The 'Restful API Manager Over SPARQL Endpoints' (a.k.a. "
                                                         "'RAMOSE') is an application that allows one to expose a "
                                                         "Restful API interface, according to a particular "
                                                         "specification document, to interact with a SPARQL endpoint.")

    arg_parser.add_argument("-s", "--spec", dest="spec", required=True,
                            help="The file in hashformat containing the specification of the API.")
    arg_parser.add_argument("-m", "--method", dest="method", default="get",
                            help="The method to use to make a request to the API.")
    arg_parser.add_argument("-c", "--call", dest="call",
                            help="The URL to call for querying the API.")
    arg_parser.add_argument("-f", "--format", dest="format", default="application/json",
                            help="The format in which to get the response.")
    arg_parser.add_argument("-d", "--doc", dest="doc", default=False, action="store_true",
                            help="Say to generate the HTML documentation of the API (if it is specified, all "
                                 "the arguments '-m', '-c', and '-f' won't be considered).")
    arg_parser.add_argument("-o", "--output", dest="output",
                            help="A file where to store the response.")

    args = arg_parser.parse_args()
    am = APIManager([args.spec])

    if args.doc:
        res = am.get_htmldoc()
    else:
        res = am.exec_op(args.call, args.method, args.format)

    if args.output is None:
        print("# Response HTTP code: %s\n# Body:\n%s" % res)
    else:
        with open(args.output, "w") as f:
            f.write(res[1])
