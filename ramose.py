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
from urllib.parse import parse_qs, urlsplit, quote , unquote
from operator import itemgetter, gt, eq, lt
from dateutil.parser import parse
from datetime import datetime
from isodate import parse_duration
from argparse import ArgumentParser
from os.path import abspath, dirname, basename
from os import sep , getcwd


FIELD_TYPE_RE = "([^\(\s]+)\(([^\)]+)\)"
PARAM_NAME = "{([^{}\(\)]+)}"


class APIManager(object):

    # Hash format: START
    @staticmethod
    def process_hashformat(file_path):
        """This method takes in input a path of a file containing a document specified in Hash Format (see
        https://github.com/opencitations/hf), and returns its representation as a dictionary."""
        result = []

        with open(file_path, "r", newline=None) as f:
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

1. `exclude=<field_name>`: all the rows that have an empty value in the `<field_name>` specified are removed from the result set - e.g. `exclude=given_name` removes all the rows that do not have any string specified in the `given_name` field.

2. `filter=<field_name>:<operator><value>`: only the rows compliant with `<value>` are kept in the result set. The parameter `<operation>` is not mandatory. If `<operation>` is not specified, `<value>` is interpreted as a regular expression, otherwise it is compared by means of the specified operation. Possible operators are "=", "<", and ">". For instance, `filter=title:semantics?` returns all the rows that contain the string "semantic" or "semantics" in the field `title`, while `filter=date:>2016-05` returns all the rows that have a `date` greater than May 2016.

3. `sort=<order>(<field_name>)`: sort in ascending (`<order>` set to "asc") or descending (`<order>` set to "desc") order the rows in the result set according to the values in `<field_name>`. For instance, `sort=desc(date)` sorts all the rows according to the value specified in the field `date` in descending order.

4. `format=<format_type>`: the final table is returned in the format specified in `<format_type>` that can be either "csv" or "json" - e.g. `format=csv` returns the final table in CSV format. This parameter has higher priority of the type specified through the "Accept" header of the request. Thus, if the header of a request to the API specifies `Accept: text/csv` and the URL of such request includes `format=json`, the final table is returned in JSON.

5. `json=<operation_type>("<separator>",<field>,<new_field_1>,<new_field_2>,...)`: in case a JSON format is requested in return, tranform each row of the final JSON table according to the rule specified. If `<operation_type>` is set to "array", the string value associated to the field name `<field>` is converted into an array by splitting the various textual parts by means of `<separator>`. For instance, considering the JSON table `[ { "names": "Doe, John; Doe, Jane" }, ... ]`, the execution of `array("; ",names)` returns `[ { "names": [ "Doe, John", "Doe, Jane" ], ... ]`. Instead, if `<operation_type>` is set to "dict", the string value associated to the field name `<field>` is converted into a dictionary by splitting the various textual parts by means of `<separator>` and by associating the new fields `<new_field_1>`, `<new_field_2>`, etc., to these new parts. For instance, considering the JSON table `[ { "name": "Doe, John" }, ... ]`, the execution of `dict(", ",name,fname,gname)` returns `[ { "name": { "fname": "Doe", "gname": "John" }, ... ]`.

It is possible to specify one or more filtering operation of the same kind (e.g. `exclude=given_name&exclude=family_name`). In addition, these filtering operations are applied in the order presented above - first all the `exclude` operation, then all the `filter` operations followed by all the `sort` operation, and finally the `format` and the `json` operation (if applicable). It is worth mentioning that each of the aforementioned rules is applied in order, and it works on the structure returned after the execution of the previous rule.

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
        @import url('https://fonts.googleapis.com/css?family=Karla:400,700&display=swap');
        * {
            font-family: Karla, Geneva, sans-serif;
        }

        body {
          margin: 7% 15%;
          line-height: 1.5em;
          font-size : 1.2em;
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
            padding-left: 7% ;
        }

        .params {
            margin-bottom: 0;
        }

        .params + ul {
            margin-top: 0;
        }

        #operations h3 {
            background-color: rgba(47, 34, 222,.5);
            color: white;
            margin-top: 0px;
            margin-bottom: 0px;
            border-radius: 14px 14px 0 0;
            padding: 10px;
        }

        pre {
            background-color: rgba(47, 34, 222,.1);
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
            background-color: rgba(47, 34, 222,.1);
            margin-bottom: 0px;
            padding-top: 5px;
            padding-bottom: 5px;
            border-top: 1px solid #246375;
            border-bottom: 1px solid #246375;
        }

        header > h2:first-of-type {
            margin-bottom: 15px;
        }

        header > ol:first-of-type {
            margin-top: 0;
        }

        :not(pre) > code {
            background-color: #fcf5f9;
            color: #fc3f9e;
            padding: 0 2px 0 2px;
            border-radius: 3px;
        }

        *:not(div) > p {
            margin-left: 1.2%;
        }


        h1, h2, h3, h4, h5, h6 {
            font-weight: 700;
            line-height: 1.2em;
            padding-top:1em;
        }

        h2 ~ h2, section > h2 {
            border-top: 1px solid #246375;
            padding-top: 5px;
            padding-left: 1%;
            margin-top: 40px;
        }

        h2 a[href] {
            background-image: none;
            text-transform:uppercase;
            padding: 1px 3px 1px 3px;
            font-size: 12pt;
            float: right;
            position:relative;
            top: -3px;
        }

        h2 a[href]::before {
            content: " \u2191 ";
        }

        /*h3 a[href] {
            color:white
            background-image: none;
            text-transform:uppercase;
            padding: 1px 3px 1px 3px;
            font-size: 8pt !important;
            border: 1px solid #246375;
            float: right;
            position:relative;
            top: -11px;
            right: -11px;
            border-radius: 0 14px 0 0;
        }*/

        p {
            overflow-wrap: break-word;
            word-wrap: break-word;
        }

        a {
            color : black;
            font-weight: 700;
            text-decoration: none;
            background-image: -webkit-gradient(linear,left top, left bottom,color-stop(50%, transparent),color-stop(0, rgba(154, 49, 252,.5)));
            background-image: linear-gradient(180deg,transparent 50%,rgba(154, 49, 252,.5) 0);
            background-position-y: 3px;
            background-position-x: 0px;
            background-repeat: no-repeat;
            -webkit-transition: .15s ease;
            transition: .15s ease;
        }

        a:hover {
            color: #282828;
            background-position: top 6px right 0px;
            background-image: -webkit-gradient(linear,left top, left bottom,color-stop(60%, transparent),color-stop(0, #9931FC));
            background-image: linear-gradient(180deg,transparent 60%,#9931FC 0);
        }

        footer {
            margin-top: 20px;
            border-top: 1px solid lightgrey;
            text-align: center;
            color: grey;
            font-size: 9pt;
        }

        .api_calls {
            height : 20em;
            scroll-behavior: smooth;
            overflow: auto;
            overflow-y: scroll;
            scrollbar-color: #9931FC rgb(154, 49, 252);
        }

        .api_calls:hover {
          overflow-y: scroll;
        }


        .api_calls p {
          padding: 0.2em 1em;
        }

        .api_calls p:nth-child(odd) {
          background-color: 	#F8F8F8;
        }

        .api_calls p {
          padding-right: 1em;
        }

        .date_log , .method_log {
          clear:left;
          display: block;
          color: grey;
          font-size: 0.8em;
        }

        .date_log {
          margin-left: 2.2em;
        }

        .group_log:nth-child(odd) {
          width: 20%;
          display: inline-block;
        }

        .group_log:nth-child(even) {
          width: 75%;
          display: inline-block;
        }

        .status_log::before {
          content: '';
           display: inline-block;
           width: 1em;
           height: 1em;
           vertical-align: middle;
           -moz-border-radius: 50%;
           -webkit-border-radius: 50%;
           border-radius: 50%;
           background-color: grey;
           margin-right: 0.8em;
        }

        .code_200::before {
          background-color: #00cc00;
        }

        .code_404::before {
          background-color: #cccc00;
        }

        .code_500::before {
          background-color: #cc0000;
        }

        """

    def __css_path(self, css_path=None):
        """Add link to a css file if specified in argument -css"""
        return """<link rel="stylesheet" type="text/css" href='"""+css_path+"""'>""" if css_path else ""

    def logger_ramose(self):
        """This method adds logging info to a local file"""
        # logging
        logFormatter = logging.Formatter("[%(asctime)s] [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
        rootLogger = logging.getLogger()

        fileHandler = logging.FileHandler("ramose.log")
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

    def __parse_logger_ramose(self):
        """This method reads logging info stored into a local file, so as to be browsed in the dashboard.
        Returns: the list of URL of current working APIs, basic logging info """
        with open("ramose.log") as l_f:
            logs = ''.join(l_f.readlines())
        rev_list = set()
        rev_list_add = rev_list.add
        rev_list = [x for x in list(reversed(logs.splitlines())) if not (x in rev_list or rev_list_add(x))]
        clean_list = [l for l in rev_list if self.base_url in l and "debug" not in l]

        api_logs_list = ''.join(["<p>"+self.clean_log(l) +"</p>" for l in clean_list if self.clean_log(l) !=''])

        html = """
        <div class="info_api">
            <p><strong>API</strong>: %s<br/>
            <strong>API Documentation</strong>: <a href="%s">%s</a><br/>
            <strong>Endpoint</strong>: <a href="%s">%s</a><br/>

        </div>

        <h2>Last API calls</h2>
        <div class="api_calls">

            %s
        </div>

        """ % (self.__title(), self.base_url,self.base_url, self.tp, self.tp, api_logs_list)
        return html

    def get_htmldoc(self, css_path=None):
        """This method generates the HTML documentation of an API described in an input Hash Format document."""
        return 200, """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <title>%s</title>
        <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
        <meta name="viewport" content="width=device-width" />
        <style>%s</style>
        %s
    </head>
    <body>
        <header>%s</header>
        <section id="operations">%s</section>
        <footer>%s</footer>
    </body>
</html>""" % (self.__title(), self.__css(), self.__css_path(css_path), self.__header(), self.__operations(), self.__footer())

    def get_htmlindex(self,css_path=None):
        """This method generates the HTML documentation of RAMOSE as described in the ramose.html document"""

        return """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <title>RAMOSE</title>
              <meta name="description" content="Documentation of RAMOSE API Manager">
              <style>%s</style>
              %s
            </head>
            <body>
                <h1>Restful API Manager Over SPARQL Endpoints (RAMOSE)</h1>
                %s
                <footer>%s</footer>
            </body>
            </html>
        """ % (self.__css(), self.__css_path(css_path), self.__parse_logger_ramose(), self.__footer())

    def store_htmldoc(self, file_path,css_path=None):
        """This method stores the HTML documentation on an API in a file."""
        html = self.get_htmldoc(css_path)
        with open(file_path, "w") as f:
            f.write(html)

    def clean_log(self, l):
        """This method parses logs lines into structured data"""
        s = l.split("- - ",1)[1]
        date = s[s.find("[")+1:s.find("]")]
        method = s.split('"')[1::2][0].split()[0]
        cur_call = s.split('"')[1::2][0].split()[1].strip()
        print(cur_call)
        status = sub(r"\D+", "", s.split('"',2)[2])
        if cur_call != self.base_url+'/':
            full_str = "<span class='group_log'><span class='status_log code_"+status+"'>"+status+"</span>"+"<span class='date_log'>"+date+"</span></span>"+"<span class='group_log'><span class='call_log'><a href='"+cur_call+"' target='_blank'>"+cur_call+"</a></span>"+"<span class='method_log'>"+method+"</span></span>"
        else:
            full_str = ''
        return full_str
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
                    self.tp = item["endpoint"]
                    if "addon" in item:
                        addon_abspath = abspath(dirname(conf_file) + sep + item["addon"])
                        path.append(dirname(addon_abspath))
                        self.addon = import_module(basename(addon_abspath))
                    self.sparql_http_method = "post"
                    if "method" in item:
                        self.sparql_http_method = item["method"].strip().lower()
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
        """This method returns the data type for durations according to the XML Schema
        Recommendation (https://www.w3.org/TR/xmlschema11-2/#duration) from the input string.
        In case the input string is None or it is empty, an high duration value
        (i.e. 2000 years) is returned."""
        if s is None or s == "":
            d = parse_duration("P2000Y")
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
        #u = u.decode('UTF8') if isinstance(u, (bytes, bytearray)) else u
        cur_u = sub("\?.*$", "", u)
        result = None

        for pat in self.conf:
            if match("^%s$" % pat, cur_u):
                result = pat
                break

        return result

    @staticmethod
    def get_content_type(ct):
        content_type = ct

        if ct == "csv":
            content_type = "text/csv"
        elif ct == "json":
            content_type = "application/json"

        return content_type

    @staticmethod
    def conv(s, query_string, c_type="text/csv"):
        """This method takes a string representing a CSV document and converts it in the requested format according
        to what content type is specified as input."""

        content_type = APIManager.get_content_type(c_type)

        # Overrite if requesting a particular format via the URL
        if "format" in query_string:
            req_formats = query_string["format"]

            for req_format in req_formats:
                content_type = APIManager.get_content_type(req_format)

        if "application/json" in content_type:
            with StringIO(s) as f:
                r = []
                for i in DictReader(f):
                    r.append(dict(i))

                # See if any restructuring of the final JSON is required
                r = APIManager.structured(query_string, r)

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
        if prev is None:
            res = []
        else:
            res = prev.copy()

        if type(d_or_l) is dict:
            d_list = [d_or_l]
        if type(d_or_l) is list:
            d_list = d_or_l

        for d in d_list:
            key_list_len = len(key_list)

            if key_list_len >= 1:
                key = key_list[0]
                if key in d:
                    if key_list_len == 1:
                        res.append(d[key])
                    else:
                        res = APIManager.get_item_in_dict(d[key], key_list[1:], res)

        return res

    @staticmethod
    def add_item_in_dict(d_or_l, key_list, item, idx):
        """This method takes as input a dictionary or a list of dictionaries, browses it until the value
        specified following the chain indicated in 'key_list' is not found, adn then substitute it with 'item'.
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
                        APIManager.add_item_in_dict(i, key_list, item, idx)
            else:
                if key in d_or_l:
                    if key_list_len == 1:
                        d_or_l[key] = item
                    else:
                        APIManager.add_item_in_dict(d_or_l[key], key_list[1:], item, idx)

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
                ops = findall('([a-z]+)\(("[^"]+"),([^\)]+)\)', field)
                for op_type, s, es in ops:
                    separator = sub('"(.+)"', "\\1", s)
                    entries = [i.strip() for i in es.split(",")]
                    keys = entries[0].split(".")

                    for row in json_table:
                        v_list = APIManager.get_item_in_dict(row, keys)
                        for idx, v in enumerate(v_list):
                            if op_type == "array":
                                if type(v) is str:
                                    APIManager.add_item_in_dict(row, keys,
                                                                v.split(separator) if v != "" else [], idx)
                            elif op_type == "dict":
                                new_fields = entries[1:]
                                new_fields_max_split = len(new_fields) - 1
                                if type(v) is str:
                                    new_values = v.split(separator, new_fields_max_split)
                                    APIManager.add_item_in_dict(row, keys,
                                                                dict(zip(new_fields, new_values)) if v != "" else {},
                                                                idx)
                                elif type(v) is list:
                                    new_list = []
                                    for i in v:
                                        new_values = i.split(separator, new_fields_max_split)
                                        new_list.append(dict(zip(new_fields, new_values)))
                                    APIManager.add_item_in_dict(row, keys, new_list, idx)

        return json_table
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
                        reg_ex = sub("^[^\(]+\((.+)\)", "\\1", op_item[param_name])
                    else:
                        reg_ex = ".+"

                    match_url = match_url.replace("{%s}" % param_name, "(%s)" % reg_ex)

                # Get only the groups that are not overlapping with others
                param_list = ()
                search_groups = search(match_url, result)
                for i in range(1, len(search_groups.groups()) + 1):
                    i_span = search_groups.span(i)
                    if i_span != (-1, -1) and all(not APIManager.do_overlap(i_span, p) for p in param_list):
                        param_list += (search_groups.group(i), )

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
            for post in [i.strip() for i in op_item["postprocess"].split(" --> ")]:
                func_name = sub("^([^\(\)]+)\(.+$", "\\1", post).strip()
                param_str = sub("^.+\(([^\(\)]*)\).*", "\\1", post)
                if param_str == "":
                    params_values = ()
                else:
                    params_values = next(reader(param_str.splitlines(), skipinitialspace=True))

                func = getattr(self.addon, func_name)
                func_params = (result,) + tuple(params_values)
                result, do_type_fields = func(*func_params)
                if do_type_fields:
                    result = self.type_fields(result, op_item)

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
                if type(cur_value) is tuple:
                    cur_value = cur_value[1]
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

                    if self.sparql_http_method == "get":
                        r = get(self.tp + "?query=" + quote(query), headers={"Accept": "text/csv"})
                    else:
                        r = post(self.tp, data=query, headers={"Accept": "text/csv",
                                                               "Content-Type": "application/sparql-query"})
                    r.encoding = "utf-8"
                    sc = r.status_code
                    if sc == 200:
                        # This line has been added to avoid a strage behaviour of the 'splitlines' method in
                        # presence of strange characters (non-UTF8).
                        list_of_lines = [line.decode("utf-8") for line in r.text.encode("utf-8").splitlines()]
                        res = self.type_fields(list(reader(list_of_lines)), i)
                        res = self.postprocess(res, i)
                        q_string = parse_qs(quote(url_parsed.query, safe="&="))
                        res = self.handling_params(q_string, res)
                        res = self.remove_types(res)
                        s_res = StringIO()
                        writer(s_res).writerows(res)
                        return (sc,) + APIManager.conv(s_res.getvalue(), q_string, content_type)
                    else:
                        return sc, "HTTP status code %s: %s" % (sc, r.reason), "text/plain"
                except TimeoutError:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 408
                    return sc, "HTTP status code %s: request timeout - %s: %s (line %s)" % \
                           (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno), "text/plain"
                except TypeError:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 400
                    return sc, "HTTP status code %s: " \
                               "parameter in the request not compliant with the type specified - %s: %s (line %s)" % \
                               (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno), "text/plain"
                except:
                    exc_type, exc_obj, exc_tb = exc_info()
                    sc = 500
                    return sc, "HTTP status code %s: something unexpected happened - %s: %s (line %s)" % \
                           (sc, exc_type.__name__, exc_obj, exc_tb.tb_lineno), "text/plain"
            else:
                sc = 405
                return sc, "HTTP status code %s: '%s' method not allowed" % (sc, str_method), "text/plain"
        else:
            sc = 404
            return sc, "HTTP status code %s: the operation requested does not exist" % sc, "text/plain"


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
    arg_parser.add_argument("-w", "--webserver", dest="webserver", default=False,
                            help="The host:port where to deploy a Flask webserver for testing the API.")
    arg_parser.add_argument("-css", "--css", dest="css",
                            help="The path of a .css file for styling the API documentation (to be specified either with '-w' or with '-d' and '-o' arguments).")

    args = arg_parser.parse_args()
    am = APIManager([args.spec])
    css_path = args.css if args.css else None

    if args.webserver:
        try:
            import logging
            from flask import Flask, request , make_response, send_from_directory
            from werkzeug.exceptions import HTTPException

            # logs
            logs = am.logger_ramose()

            # web server
            host_name = args.webserver.rsplit(':', 1)[0] if ':' in args.webserver else '127.0.0.1'
            port = args.webserver.rsplit(':', 1)[1] if ':' in args.webserver else '8080'
            api_url = am.conf_json[0]['url']
            app = Flask(__name__)

            # This is due to Flask routing rules that do not accept URLs without the starting slash
            # but ramose calls start with the slash, hence we remove it if the flag args.webserver is added
            if args.call:
                args.call = args.call[1:]

            @app.route('/')
            def home():
                index = am.get_htmlindex(css_path)
                return index

            @app.route(api_url)
            @app.route(api_url+'/')
            def doc():
                status, res = am.get_htmldoc(css_path)[0] , am.get_htmldoc(css_path)[1]
                return res , status

            @app.route(api_url+'/<path:call>')
            def ramose(call):
                cur_call = api_url+'/'+call # put back that slash -- does not include parameters
                format = request.args.get('format')
                content_type = "text/csv" if format is not None and "csv" in format else "application/json"
                status, res, c_type = am.exec_op(cur_call+'?'+unquote(request.query_string.decode('utf8')), content_type=content_type)

                if status == 200:
                    response = make_response(res, status)
                    response.headers.set('Content-Type', c_type)
                else:
                    # The API Manager returns a text/plain message when there is an error.
                    # Now set to return the header requested by the user
                    if content_type == "text/csv":
                        si = StringIO()
                        cw = writer(si)
                        cw.writerows([["error","message"], [str(status),str(res)]])
                        response = make_response(si.getvalue(), status)
                        response.headers.set("Content-Disposition", "attachment", filename="error.csv")
                    else:
                        m_res , m_res["error"] , m_res["message"] = {} , status, res
                        mes = dumps(m_res)
                        response = make_response(mes, status)
                    response.headers.set('Content-Type', content_type) # overwrite text/plain

                # allow CORS anyway
                response.headers.set('Access-Control-Allow-Origin', '*')
                response.headers.set('Access-Control-Allow-Credentials', 'true')

                return response

            app.run(host=str(host_name), debug=True, port=str(port))

        except Exception as e:
            exc_type, exc_obj, exc_tb = exc_info()
            fname = path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("[ERROR]", exc_type, fname, exc_tb.tb_lineno)

    else:
        # run locally via shell
        if args.doc:
            res = am.get_htmldoc(css_path)
        else:
            print(args.call)
            res = am.exec_op(args.call, args.method, args.format)

        if args.output is None:
            print("# Response HTTP code: %s\n# Body:\n%s\n# Content-type: %s" % res)
        else:
            with open(args.output, "w") as f:
                f.write(res[1])
