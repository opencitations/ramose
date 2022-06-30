#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2020
# Silvio Peroni <essepuntato@gmail.com>
# Marilena Daquino <marilena.daquino2@unibo.it>
#
# Permission to use, copy, modify, and/or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice
# and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER 
# ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
# SOFTWARE.

__author__ = 'essepuntato'

from abc import abstractmethod
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
from operator import add, itemgetter, gt, eq, lt
from dateutil.parser import parse
from datetime import datetime
from isodate import parse_duration
from argparse import ArgumentParser
from os.path import abspath, dirname, basename
from os import path as pt
import logging
from os import sep, getcwd
import logging
from flask import Flask, request , make_response, send_from_directory
from werkzeug.exceptions import HTTPException

FIELD_TYPE_RE = "([^\(\s]+)\(([^\)]+)\)"
PARAM_NAME = "{([^{}\(\)]+)}"

class HashFormatHandler(object):
    """
    This class creates an object capable to read files stored in Hash Format (see
    https://github.com/opencitations/ramose#Hashformat-configuration-file). A Hash Format
    file (.hf) is a specification file that includes information structured using the following
    syntax:

    ```
    #<field_name_1> <field_value_1>
    #<field_name_1> <field_value_2>
    #<field_name_3> <field_value_3>
    [...]
    #<field_name_n> <field_value_n>
    ```
    """

    def read(self, file_path):
        """
        This method takes in input a path of a file containing a document specified in
        Hash Format, and returns its representation as list of dictionaries.
        """

        result = []

        with open(file_path, "r", newline=None, encoding='utf8') as f:
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
                                result.append(cur_object)
                            cur_object = {}

                        # Add the new key to the object
                        cur_object[cur_field_name] = cur_field_content
                elif cur_object is not None and len(cur_object) > 0:
                    cur_object[cur_field_name] += line

            # Insert the last object in the result
            if cur_object is not None and len(cur_object) > 0:
                result.append(cur_object)

        # Clean the final \n
        for item in result:
            for key in item:
                item[key] = item[key].rstrip()

        return result


class DocumentationHandler(object):
    def __init__(self, api_manager):
        """
        This class provides the main structure for returning a human-readable documentation of all
        the operations described in the configuration files handled by the APIManager specified as input.
        """

        self.conf_doc = api_manager.all_conf

    @abstractmethod
    def get_documentation(self, *args, **dargs):
        """
        An abstract method that returns a string defining the human-readable documentation of the operations
        available in the input APIManager.
        """

        pass

    @abstractmethod
    def store_documentation(self, file_path, *args, **dargs):
        """
        An abstract method that store in the input file path (parameter 'file_path') the human-readable
        documentation of the operations available in the input APIManager.
        """

        pass

    @abstractmethod
    def get_index(self, *args, **dargs):
        """
        An abstract method that returns a string defining the index of all the various configuration files
        handled by the input APIManager.
        """

        pass

class HTMLDocumentationHandler(DocumentationHandler):
    # HTML documentation: START
    def __title(self, conf):
        """
        This method returns the title string defined in the API specification.
        """

        return conf["conf_json"][0]["title"]

    def __sidebar(self, conf):
        """
        This method builds the sidebar of the API documentation
        """

        result = ""

        i = conf["conf_json"][0]
        result += """

        <h4>%s</h4>
        <ul id="sidebar_menu" class="sidebar_menu">
            <li><a class="btn active" href="#description">DESCRIPTION</a></li>
            <li><a class="btn" href="#parameters">PARAMETERS</a></li>
            <li><a class="btn" href="#operations">OPERATIONS</a>
                <ul class="sidebar_submenu">%s</ul>
            </li>
            <li><a class="btn active" href="/">HOME</a></li>
        </ul>
        """ % \
                    (i["title"], "".join(["<li><a class='btn' href='#%s'>%s</a></li>" % (op["url"], op["url"])
                             for op in conf["conf_json"][1:]]))
        return result

    def __header(self, conf):
        """
        This method builds the header of the API documentation
        """

        result = ""

        i = conf["conf_json"][0]
        result += """
<a id='toc'></a>
# %s

**Version:** %s <br/>
**API URL:** <a href="%s">%s</a><br/>
**Contact:** %s<br/>
**License:** %s<br/>



## <a id="description"></a>Description [back to top](#toc)

%s

%s""" % \
                  (i["title"], i["version"], i["base"] + i["url"], i["base"] + i["url"],  i["contacts"], i["license"],

                   i["description"], self.__parameters())
                   # (i["title"], i["version"], i["base"] + i["url"], i["base"] + i["url"], i["contacts"], i["contacts"], i["license"],
                   #  "".join(["<li>[%s](#%s): %s</li>" % (op["url"], op["url"], op["description"].split("\n")[0])
                   #           for op in self.conf_json[1:]]),
                   #  i["description"], self.__parameters())
        return markdown(result)

    def __parameters(self):

        result = """## <a id="parameters"></a>Parameters [back to top](#toc)

Parameters can be used to filter and control the results returned by the API. They are passed as normal HTTP parameters in the URL of the call. They are:

1. `require=<field_name>`: all the rows that have an empty value in the `<field_name>` specified are removed from the result set - e.g. `require=given_name` removes all the rows that do not have any string specified in the `given_name` field.

2. `filter=<field_name>:<operator><value>`: only the rows compliant with `<value>` are kept in the result set. The parameter `<operation>` is not mandatory. If `<operation>` is not specified, `<value>` is interpreted as a regular expression, otherwise it is compared by means of the specified operation. Possible operators are "=", "<", and ">". For instance, `filter=title:semantics?` returns all the rows that contain the string "semantic" or "semantics" in the field `title`, while `filter=date:>2016-05` returns all the rows that have a `date` greater than May 2016.

3. `sort=<order>(<field_name>)`: sort in ascending (`<order>` set to "asc") or descending (`<order>` set to "desc") order the rows in the result set according to the values in `<field_name>`. For instance, `sort=desc(date)` sorts all the rows according to the value specified in the field `date` in descending order.

4. `format=<format_type>`: the final table is returned in the format specified in `<format_type>` that can be either "csv" or "json" - e.g. `format=csv` returns the final table in CSV format. This parameter has higher priority of the type specified through the "Accept" header of the request. Thus, if the header of a request to the API specifies `Accept: text/csv` and the URL of such request includes `format=json`, the final table is returned in JSON.

5. `json=<operation_type>("<separator>",<field>,<new_field_1>,<new_field_2>,...)`: in case a JSON format is requested in return, tranform each row of the final JSON table according to the rule specified. If `<operation_type>` is set to "array", the string value associated to the field name `<field>` is converted into an array by splitting the various textual parts by means of `<separator>`. For instance, considering the JSON table `[ { "names": "Doe, John; Doe, Jane" }, ... ]`, the execution of `array("; ",names)` returns `[ { "names": [ "Doe, John", "Doe, Jane" ], ... ]`. Instead, if `<operation_type>` is set to "dict", the string value associated to the field name `<field>` is converted into a dictionary by splitting the various textual parts by means of `<separator>` and by associating the new fields `<new_field_1>`, `<new_field_2>`, etc., to these new parts. For instance, considering the JSON table `[ { "name": "Doe, John" }, ... ]`, the execution of `dict(", ",name,fname,gname)` returns `[ { "name": { "fname": "Doe", "gname": "John" }, ... ]`.

It is possible to specify one or more filtering operation of the same kind (e.g. `require=given_name&require=family_name`). In addition, these filtering operations are applied in the order presented above - first all the `require` operation, then all the `filter` operations followed by all the `sort` operation, and finally the `format` and the `json` operation (if applicable). It is worth mentioning that each of the aforementioned rules is applied in order, and it works on the structure returned after the execution of the previous rule.

Example: `<api_operation_url>?require=doi&filter=date:>2015&sort=desc(date)`."""
        return markdown(result)

    def __operations(self, conf):
        """
        This method returns the description of all the operations defined in the API.
        """

        result = """## Operations [back to top](#toc)
The operations that this API implements are:
"""
        ops = "\n"

        for op in conf["conf_json"][1:]:
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

<p class="attr"><strong>Accepted HTTP method(s)</strong> <span class="attr_val method">%s</span></p>
<p class="attr params"><strong>Parameter(s)</strong> <span class="attr_val">%s</span></p>
<p class="attr"><strong>Result fields type</strong><span class="attr_val">%s</span></p>
<p class="attr"><strong>Example</strong><span class="attr_val"><a target="_blank" href="%s">%s</a></span></p>
<p class="ex attr"><strong>Exemplar output (in JSON)</strong></p>
<pre><code>%s</code></pre></div>""" % (op["url"], op["url"], markdown(op["description"]),
                                       ", ".join(split("\s+", op["method"].strip())), "</li><li>".join(params),
                                       ", ".join(["%s <em>(%s)</em>" % (f, t) for t, f in
                                                  findall(FIELD_TYPE_RE, op["field_type"])]),
                                       conf["website"] + conf["base_url"] + op["call"], op["call"], op["output_json"])
        return markdown(result) + ops

    def __footer(self):
        """
        This method returns the footer of the API documentation.
        """

        result = """This API and the related documentation has been created with <a href="https://github.com/opencitations/ramose" target="_blank">RAMOSE</a>, the *Restful API Manager Over SPARQL Endpoints*, developed by <a href="http://orcid.org/0000-0003-0530-4305" target="_blank">Silvio Peroni</a> and <a href="https://marilenadaquino.github.io">Marilena Daquino</a>."""
        return markdown(result)

    def __css(self):
        return """
        @import url('https://fonts.googleapis.com/css2?family=Karla:wght@300;400&display=swap');
        @media screen and (max-width: 850px) {
              aside { display: none; }
              main, #operations, .dashboard, body>footer {margin-left: 15% !important;}
              #operations > ul:nth-of-type(1) li { display:block !important; max-width: 100% !important; }
              h3 a[href] {display:block !important; float: none !important; font-size: 0.5em !important;}
              a {overflow: hidden; text-overflow: ellipsis;}
              .info_api, .api_calls {display: block !important; max-width: 100% !important;}
            }

        * {
            font-family: 'Karla', Geneva, sans-serif;
        }

        body {
          margin: 3% 15% 7% 0px;
          line-height: 1.5em;
          letter-spacing: 0.02em;
          font-size : 1em;
          font-weight:300;
          color: #303030;
          text-align: justify;
          background-color: #edf0f2;
        }

        aside {
            height : 100%;
            width: 20%;
            position: fixed;
            z-index: 1;
            top: 0;
            left: 0;
            /*background-color: #404040;*/
            overflow-x: hidden;
            background-color: white;
            box-shadow:0px 10px 30px 0px rgba(133,66,189,0.1);
        }
        p strong {
            text-transform: uppercase;
            font-size: 0.9em;
        }
        aside h4 {
            padding: 20px 9%;
            margin: 0px !important;
            color: #9931FC;
            text-align: left !important;
        }

        .sidebar_menu , .sidebar_submenu {
            list-style-type: none;
            padding-left:0px !important;
            margin-top: 10px;

        }

        .sidebar_menu > li {
            padding: 2% 0px;
            border-top : solid 0.7px grey;
        }

        .sidebar_menu a {
            padding: 1% 9%;
            background-image: none !important;
            color: grey;
            display: block;
        }

        .sidebar_menu a:hover {
            border-left: solid 5px rgba(154, 49, 252,.5);
            font-weight: 400;
        }

        .sidebar_submenu > li {
            padding-left:0px !important;
            background-color:#edf0f2;
            font-size: 0.8em;
        }

        main , #operations , .dashboard, body>footer {
            margin-left: 33%;
        }
        .dashboard {text-align: center;}
        main h1+p , .info_api{

            padding-left: 3%;
            font-size: 0.9em;
            line-height: 1.4em;
        }

        main h1+p {border-left: solid 5px rgba(154, 49, 252,.5);}

        #operations h3 {
            color: #9931FC;
            margin-bottom: 0px;
            padding: 10px;
        }

        #operations > ul:nth-of-type(1) {
            padding-left: 0px !important;
            text-align: center;
        }

        #operations > ul:nth-of-type(1) li {
            background-color: white;
            text-align: left;
            display: inline-block;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 35%;
            height: 200px;
            padding:4%;
            margin: 1% 2% 1% 0px;
            border-radius: 10px;
            box-shadow: 0px 10px 30px 0px rgba(133,66,189,0.1);
            vertical-align:top;
        }

        #operations > div {
            background-color: white;
            margin-top: 20px;
            padding: 2%;
            border-radius: 18px;
            box-shadow: 0px 10px 30px 0px rgba(133,66,189,0.1);
        }

        #operations > div > * {
            padding: 0px 2%;
        }

        #operations > div ul, .params+ul{
            list-style-type: none;
            font-size: 0.85em;
        }
        #operations > div ul:nth-of-type(1) li, .params+ul li {
            margin: 10px 0px;
        }

        #operations > div ul:nth-of-type(1) li em, .params+ul li em {
            font-style: normal;
            font-weight: 400;
            color: #9931FC;
            border-left: solid 2px #9931FC;
            padding:5px;
        }

        .attr {
            border-top: solid 1px rgba(133,66,189,0.1);
            padding: 2% !important;
            display:block;
            vertical-align: top;
            font-size: 0.8em;
            text-align: left;
        }

        .attr strong {
            width: 30%;
            color: grey;
            font-weight: 400;
            font-style: normal;
            display:inline-block;
            vertical-align: top;
        }

        .attr_val {
            max-width: 50%;
            display:inline-table;
            height: 100%;
            vertical-align: top;
        }

        .method {
            text-transform: uppercase;
        }

        .params {
            margin-bottom: 0;
        }

        pre {
            background-color: #f0f0f5;
            padding: 10px;
            margin-top: 0;
            margin-bottom: 0;
            border-radius: 0 0 14px 14px;
            font-family: monospace !important;
            overflow: scroll;
            line-height: 1.2em;
            height: 250px;
        }

        pre code {
            font-family: monospace !important;
        }

        p.ex {
            background-color: #f0f0f5;
            margin-bottom: 0px;
            padding-top: 5px;
            padding-bottom: 5px;
        }

        h2:first-of-type {
            margin-bottom: 15px;
        }

        ol:first-of-type {
            margin-top: 0;
        }

        :not(pre) > code {
            background-color:  #f0f0f5;
            color: #8585ad;
            padding: 0 2px 0 2px;
            border-radius: 3px;
            font-family : monospace;
            font-size: 1.2em !important;
        }

        /**:not(div) > p {
            margin-left: 1.2%;
        }*/

        h1 {font-size: 2.5em;}
        h1, h2 {
            text-transform: uppercase;
        }

        h1, h2, h3, h4, h5, h6 {
            line-height: 1.2em;
            padding-top:1em;
            text-align: left !important;
            font-weight:400;
        }

        h2 ~ h2, section > h2 {

            padding-top: 5px;
            margin-top: 40px;
        }

        h2 a[href], h3 a[href] {
            background-image: none;
            text-transform:uppercase;
            padding: 1px 3px 1px 3px;
            font-size: 12pt;
            float: right;
            position:relative;
            top: -3px;
        }

        h2 a[href]::before , h3 a[href]::before {
            content: " \u2191";
            width: 20px;
            height: 20px;
            display:inline-block;
            color: #9931FC;
            text-align:center;
            margin-right: 10px;
        }

        /*h3 a[href] {
            color:white
            background-image: none;
            text-transform:uppercase;
            padding: 1px 3px 1px 3px;
            font-size: 8pt !important;
            border: 1px solid #9931FC;
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
        /* dashboard */

        .info_api {
            max-width: 35%;
            border-radius: 15px;
            text-align: left;
            vertical-align: top;
            background-color: #9931FC;
            color: white;
        }

        .info_api, .api_calls {
            display: inline-block;
            text-align: left;
            height: 200px;
            padding:4%;
            margin: 1% 2% 1% 0px;
            border-radius: 10px;
            box-shadow: 0px 10px 30px 0px rgba(133,66,189,0.1);
            vertical-align:top;
        }

        .api_calls {
            max-width: 40%;
            background-color: white;
            scroll-behavior: smooth;
            overflow: auto;
            overflow-y: scroll;
            scrollbar-color: #9931FC rgb(154, 49, 252);
            border-radius: 10px;
        }
        .api_calls div {padding-bottom:2%;}

        .api_calls:hover {
          overflow-y: scroll;
        }
        .api_calls h4, .info_api h2 {padding-top: 0px !important; margin-top: 0px !important;}
        .api_calls div p {
          padding: 0.2em 0.5em;
          border-top: solid 1px #F8F8F8;
          }
        

        .date_log , .method_log {
          color: grey;
          font-size: 0.8em;

        }
        .method_log {margin-left: 15px;}
        .date_log {display:inline-grid;}

        .group_log:nth-child(odd) {
          margin-right:5px;
          font-size: 0.9em;
        }

        .group_log:nth-child(even) {
          display: inline-grid;
          vertical-align: top;
        }
        .status_log {padding-right:15px;}
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
        """
        Add link to a css file if specified in argument -css
        """

        return """<link rel="stylesheet" type="text/css" href='"""+css_path+"""'>""" if css_path else ""

    def logger_ramose(self):
        """
        This method adds logging info to a local file
        """

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
        """
        This method reads logging info stored into a local file, so as to be browsed in the dashboard.
        Returns: the html including the list of URLs of current working APIs and basic logging info 
        """

        with open("ramose.log") as l_f:
            logs = ''.join(l_f.readlines())
        rev_list = set()
        rev_list_add = rev_list.add
        rev_list = [x for x in list(reversed(logs.splitlines())) if not (x in rev_list or rev_list_add(x))]

        html = """
        <p></p>
        <aside>
            <h4>RAMOSE API DASHBOARD</h4>
            <ul id="sidebar_menu" class="sidebar_menu">"""

        for api_url, api_dict in self.conf_doc.items():
            html +="""
                    <li><a class="btn active" href="%s">%s</a></li>
                """ % (api_url, api_dict["conf_json"][0]["title"])

        html += """
            </ul>
        </aside>
        <header class="dashboard">
            <h1>API MONITORING</h1>"""

        for api_url, api_dict in self.conf_doc.items():
            clean_list = [l for l in rev_list if api_url in l and "debug" not in l]
            api_logs_list = ''.join(["<p>"+self.clean_log(l,api_url) +"</p>" for l in clean_list if self.clean_log(l,api_url) !=''])
            api_title = api_dict["conf_json"][0]["title"]
            html += """
                <div class="info_api">
                    <h2>%s</h2>
                    <a id="view_doc" href="%s">VIEW DOCUMENTATION</a><br/>
                    <a href="%s">GO TO SPARQL ENDPOINT</a><br/>
                </div>
                <div class="api_calls">
                    <h4>Last calls</h4>
                    <div>
                        %s
                    </div>

                </div>
                """ % ( api_title,api_url, api_dict["tp"], api_logs_list)
        return html

    def get_documentation(self, css_path=None, base_url=None):
        """
        This method generates the HTML documentation of an API described in configuration file.
        """

        if base_url is None:
            first_key = next(iter(self.conf_doc))
            conf = self.conf_doc[first_key]
        else:
            conf = self.conf_doc['/'+base_url]

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
        <aside>%s</aside>
        <main>%s</main>
        <section id="operations">%s</section>
        <footer>%s</footer>
    </body>
</html>""" % (self.__title(conf), self.__css(), self.__css_path(css_path), self.__sidebar(conf), self.__header(conf), self.__operations(conf), self.__footer())

    def get_index(self, css_path=None):
        """
        This method generates the index of all the HTML documentations that can be
        created from the configuration file.
        """

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
                %s
                <footer>%s</footer>
            </body>
            </html>
        """ % (self.__css(), self.__css_path(css_path), self.__parse_logger_ramose(), self.__footer())

    def store_documentation(self, file_path, css_path=None):
        """
        This method stores the HTML documentation of an API in a file.
        """

        html = self.get_documentation(css_path)[1]
        with open(file_path, "w+", encoding='utf8') as f:
            f.write(html)

    def clean_log(self, l, api_url):
        """
        This method parses logs lines into structured data.
        """

        full_str = ''
        if len(l.split("- - ",1)) > 1:
            s = l.split("- - ",1)[1]
            date = s[s.find("[")+1:s.find("]")]
            method = s.split('"')[1::2][0].split()[0]
            cur_call = s.split('"')[1::2][0].split()[1].strip()
            status = sub(r"\D+", "", s.split('"',2)[2])

            if cur_call != api_url+'/':
                full_str = "<span class='group_log'><span class='status_log code_"+status+"'>"+status+"</span>"+"<span class='date_log'>"+date+"</span><span class='method_log'>"+method+"</span></span>"+"<span class='group_log'><span class='call_log'><a href='"+cur_call+"' target='_blank'>"+cur_call+"</a></span></span>"

        return full_str


class DataType(object):

    def __init__(self):
        """
        This class implements all the possible data types that can be used within
        the configuration file of RAMOSE. In particular, it provides methods for converting
        a string into the related Python data type representation.
        """

        self.func = {
            "str": DataType.str,
            "int": DataType.int,
            "float": DataType.float,
            "duration": DataType.duration,
            "datetime": DataType.datetime
        }

    def get_func(self, name_str):
        """
        This method returns the method for handling a given data type expressed as a string name.
        """

        return self.func.get(name_str)

    @staticmethod
    def duration(s):
        """
        This method returns the data type for durations according to the XML Schema
        Recommendation (https://www.w3.org/TR/xmlschema11-2/#duration) from the input string.
        In case the input string is None or it is empty, an high duration value
        (i.e. 2000 years) is returned.
        """

        if s is None or s == "":
            d = parse_duration("P2000Y")
        else:
            d = parse_duration(s)

        return datetime(1983, 1, 15) + d

    @staticmethod
    def datetime(s):
        """
        This method returns the data type for datetime according to the ISO 8601
           (https://en.wikipedia.org/wiki/ISO_8601) from the input string. In case the input string is None or
           it is empty, a low date value (i.e. 0001-01-01) is returned.
           """

        default = datetime(1, 1, 1, 0, 0)
        if s is None or s == "":
            d = parse("0001-01-01", default=default)
        else:
            d = parse(s, default=default)

        return d

    @staticmethod
    def str(s):
        """
        This method returns the data type for strings. In case the input string is None, an empty string
        is returned.
        """

        if s is None:
            l = ""
        else:
            l = str(s).lower()

        return l

    @staticmethod
    def int(s):
        """
        This method returns the data type for integer numbers from the input string. In case the input string is
        None or it is empty, a low integer value is returned.
        """

        if s is None or s == "":
            i = -maxsize
        else:
            i = int(s)

        return i

    @staticmethod
    def float(s):
        """
        This method returns the data type for float numbers from the input string. In case the input string is 
        None or it is empty, a low float value is returned.
        """

        if s is None or s == "":
            f = float(-maxsize)
        else:
            f = float(s)

        return f


class Operation(object):
    def __init__(self, op_complete_url, op_key, i, tp, sparql_http_method, addon):
        """ 
        This class is responsible for materialising a API operation to be run against a SPARQL endpoint.

        It takes in input a full URL referring to a call to an operation (parameter 'op_complete_url'),
        the particular shape representing an operation (parameter 'op_key'), the definition (in JSON) of such
        operation (parameter 'i'), the URL of the triplestore to contact (parameter 'tp'), the HTTP method
        to use for the SPARQL request (paramenter 'sparql_http_method', set to either 'get' or 'post'), and the path
        of the Python file which defines additional functions for use in the operation (parameter 'addon').
        """

        self.url_parsed = urlsplit(op_complete_url)
        self.op_url = self.url_parsed.path
        self.op = op_key
        self.i = i
        self.tp = tp
        self.sparql_http_method = sparql_http_method
        self.addon = addon

        self.operation = {
            "=": eq,
            "<": lt,
            ">": gt
        }

        self.dt = DataType()

    # START: Ancillary methods
    @staticmethod
    def get_content_type(ct):
        """
        It returns the mime type of a given textual representation of a format, being it either
        'csv' or 'json.
        """
        content_type = ct

        if ct == "csv":
            content_type = "text/csv"
        elif ct == "json":
            content_type = "application/json"

        return content_type

    @staticmethod
    def conv(s, query_string, c_type="text/csv"):
        """
        This method takes a string representing a CSV document and converts it in the requested format according
        to what content type is specified as input.
        """

        content_type = Operation.get_content_type(c_type)

        # Overrite if requesting a particular format via the URL
        if "format" in query_string:
            req_formats = query_string["format"]

            for req_format in req_formats:
                content_type = Operation.get_content_type(req_format)

        if "application/json" in content_type:
            with StringIO(s) as f:
                r = []
                for i in DictReader(f):
                    r.append(dict(i))

                # See if any restructuring of the final JSON is required
                r = Operation.structured(query_string, r)

                return dumps(r, ensure_ascii=False, indent=4), content_type
        else:
            return s, content_type

    @staticmethod
    def pv(i, r=None):
        """
        This method returns the plain value of a particular item 'i' of the result returned by the SPARQL query.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row.
        """

        if r is None:
            return i[1]
        else:
            return Operation.pv(r[i])

    @staticmethod
    def tv(i, r=None):
        """
        This method returns the typed value of a particular item 'i' of the result returned by the SPARQL query.
        The type associated to that value is actually specified by means of the particular configuration provided
        in the specification file of the API - field 'field_type'.

        In case 'r' is specified (i.e. a row containing a set of results), then 'i' must be the index of the item
        within that row.
        """

        if r is None:
            return i[0]
        else:
            return Operation.tv(r[i])

    @staticmethod
    def do_overlap(r1, r2):
        """
        This method returns a boolean that says if the two ranges (i.e. two pairs of integers) passed as inputs
        actually overlap one with the other.
        """

        r1_s, r1_e = r1
        r2_s, r2_e = r2

        return r1_s <= r2_s <= r1_e or r2_s <= r1_s <= r2_e

    @staticmethod
    def get_item_in_dict(d_or_l, key_list, prev=None):
        """
        This method takes as input a dictionary or a list of dictionaries and browses it until the value
        specified following the chain indicated in 'key_list' is not found. It returns a list of all the
        values that matched with such search.
        """

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
                        res = Operation.get_item_in_dict(d[key], key_list[1:], res)

        return res

    @staticmethod
    def add_item_in_dict(d_or_l, key_list, item, idx):
        """
        This method takes as input a dictionary or a list of dictionaries, browses it until the value
        specified following the chain indicated in 'key_list' is not found, and then substitutes it with 'item'.
        In case the final object retrieved is a list, it selects the object in position 'idx' before the
        substitution.
        """

        key_list_len = len(key_list)

        if key_list_len >= 1:
            key = key_list[0]

            if type(d_or_l) is list:
                if key_list_len == 1:
                    d_or_l[idx][key] = item
                else:
                    for i in d_or_l:
                        Operation.add_item_in_dict(i, key_list, item, idx)
            else:
                if key in d_or_l:
                    if key_list_len == 1:
                        d_or_l[key] = item
                    else:
                        Operation.add_item_in_dict(d_or_l[key], key_list[1:], item, idx)

    @staticmethod
    def structured(params, json_table):
        """
        This method checks if there are particular transformation rules specified in 'params' for a JSON output,
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
        the execution of the previous rule.
        """

        if "json" in params:
            fields = params["json"]
            for field in fields:
                ops = findall('([a-z]+)\(("[^"]+"),([^\)]+)\)', field)
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
                                    new_values = v.split(separator, new_fields_max_split)
                                    Operation.add_item_in_dict(row, keys,
                                                                dict(zip(new_fields, new_values)) if v != "" else {},
                                                                idx)
                                elif type(v) is list:
                                    new_list = []
                                    for i in v:
                                        new_values = i.split(separator, new_fields_max_split)
                                        new_list.append(dict(zip(new_fields, new_values)))
                                    Operation.add_item_in_dict(row, keys, new_list, idx)

        return json_table
    # END: Ancillary methods

    # START: Processing methods
    def preprocess(self, par_dict, op_item, addon):
        """
        This method takes the a dictionary of parameters with the current typed values associated to them and
        the item of the API specification defining the behaviour of that operation, and preprocesses the parameters
        according to the functions specified in the '#preprocess' field (e.g. "#preprocess lower(doi)"), which is
        applied to the specified parameters as input of the function in consideration (e.g.
        "/api/v1/citations/10.1108/jd-12-2013-0166", converting the DOI in lowercase).

        It is possible to run multiple functions sequentially by concatenating them with "-->" in the API
        specification document. In this case the output of the function f_i will becomes the input operation URL
        of the function f_i+1.

        Finally, it is worth mentioning that all the functions specified in the "#preprocess" field must return
        a tuple of values defining how the particular value passed in the dictionary must be changed.
        """
        result = par_dict

        if "preprocess" in op_item:

            for pre in [sub("\s+", "", i) for i in op_item["preprocess"].split(" --> ")]:
                func_name = sub("^([^\(\)]+)\(.+$", "\\1", pre).strip()
                params_name = sub("^.+\(([^\(\)]+)\).*", "\\1", pre).split(",")

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
        """
        This method takes the result table returned by running the SPARQL query in an API operation (specified
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
        the input result table of the function f_i+1.

        The postprocess function should output a tuple containing the result and whether the function needs to return the type of values in the result.
        """

        result = res

        if "postprocess" in op_item:
            for post in [i.strip() for i in op_item["postprocess"].split(" --> ")]:
                func_name = sub("^([^\(\)]+)\(.+$", "\\1", post).strip()
                param_str = sub("^.+\(([^\(\)]*)\).*", "\\1", post)
                if param_str == "":
                    params_values = ()
                else:
                    params_values = next(reader(param_str.splitlines(), skipinitialspace=True))

                func = getattr(addon, func_name)
                func_params = (result,) + tuple(params_values)
                result, do_type_fields = func(*func_params)
                if do_type_fields:
                    result = self.type_fields(result, op_item)

        return result

    def handling_params(self, params, table):
        """
        This method is used for filtering the results that are returned after the post-processing
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
        """
        It creates a version of the results 'res' that adds, to each value of the fields, the same value interpreted
        with the type specified in the specification file (field 'field_type'). Note that 'str' is used as default in
        case no further specifications are provided.
        """
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

        return [header] + result

    def remove_types(self, res):
        """This method takes the results 'res' that include also the typed value and returns a version of such
        results without the types that is ready to be stored on the file system."""
        result = [res[0]]

        for row in res[1:]:
            result.append(tuple(Operation.pv(idx, row) for idx in range(len(row))))

        return result

    def exec(self, method="get", content_type="application/json"):
        """
        This method takes in input the the HTTP method to use for the call
        and the content type to return, and executes the operation as indicated
        in the specification file, by running (in the following order):

        1. the methods to preprocess the query;
        2. the SPARQL query related to the operation called, by using the parameters indicated in the URL;
        3. the specification of all the types of the various rows returned;
        4. the methods to postprocess the result;
        5. the application of the filter to remove, filter, sort the result;
        6. the removal of the types added at the step 3, so as to have a data structure ready to be returned;
        7. the conversion in the format requested by the user.
        """
        str_method = method.lower()
        m = self.i["method"].split()

        if str_method in m:
            try:
                par_dict = {}
                par_man = match(self.op, self.op_url).groups()
                for idx, par in enumerate(findall("{([^{}]+)}", self.i["url"])):
                    try:
                        par_type = self.i[par].split("(")[0]
                        if par_type == "str":
                            par_value = par_man[idx]
                        else:
                            par_value = self.dt.get_func(par_type)(par_man[idx])
                    except KeyError:
                        par_value = par_man[idx]
                    par_dict[par] = par_value

                if self.addon is not None:
                    self.preprocess(par_dict, self.i, self.addon)

                query = self.i["sparql"]
                for param in par_dict:
                    query = query.replace("[[%s]]" % param, str(par_dict[param]))

                if self.sparql_http_method == "get":
                    r = get(self.tp + "?query=" + quote(query),
                            headers={"Accept": "text/csv"})
                else:
                    r = post(self.tp, data=query, headers={"Accept": "text/csv",
                                                           "Content-Type": "application/sparql-query"})
                r.encoding = "utf-8"
                sc = r.status_code
                if sc == 200:
                    # This line has been added to avoid a strage behaviour of the 'splitlines' method in
                    # presence of strange characters (non-UTF8).
                    list_of_lines = [line.decode("utf-8")
                                     for line in r.text.encode("utf-8").splitlines()]
                    res = self.type_fields(list(reader(list_of_lines)), self.i)
                    if self.addon is not None:
                        res = self.postprocess(res, self.i, self.addon)
                    q_string = parse_qs(quote(self.url_parsed.query, safe="&="))
                    res = self.handling_params(q_string, res)
                    res = self.remove_types(res)
                    s_res = StringIO()
                    writer(s_res).writerows(res)
                    return (sc,) + Operation.conv(s_res.getvalue(), q_string, content_type)
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
    # END: Processing methods


class APIManager(object):

    # Fixing max size for CSV

    @staticmethod
    def __max_size_csv():
        from sys import maxsize
        import csv
        maxInt = maxsize
        while True:
            try:
                csv.field_size_limit(maxInt)
                break
            except OverflowError:
                maxInt = int(maxInt/10)

    # Constructor: START
    
    def __init__(self, conf_files):
        
        """
        This is the constructor of the APIManager class. It takes in input a list of API configuration files, each
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
        HTTP methods to call for making the request to the SPARQL endpoint specified in the configuration file.
        """

        APIManager.__max_size_csv()

        self.all_conf = OrderedDict()
        self.base_url = []
        for conf_file in conf_files:
            conf = OrderedDict()
            tp = None
            conf_json = HashFormatHandler().read(conf_file)
            base_url = None
            addon = None
            for item in conf_json:
                if base_url is None:
                    base_url = item["url"]
                    self.base_url.append(item["url"])
                    website = item["base"]
                    tp = item["endpoint"]
                    if "addon" in item:
                        addon_abspath = abspath(dirname(conf_file) + sep + item["addon"])
                        path.append(dirname(addon_abspath))
                        addon = import_module(basename(addon_abspath))
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
                "sparql_http_method": sparql_http_method
            }
    # Constructor: END

    # START: Ancillary methods
    @staticmethod
    def nor_api_url(i, b=""):
        """
        This method takes an API operation object and an optional base URL (e.g. "/api/v1") as input
        and returns the URL composed by the base URL plus the API URL normalised according to specific rules. In
        particular, these normalisation rules takes the operation URL (e.g. "#url /citations/{oci}") and the
        specification of the shape of all the parameters between brackets in the URL (e.g. "#oci str([0-9]+-[0-9]+)"),
        and returns a new operation URL where the parameters have been substituted with the regular expressions
        defining them (e.g. "/citations/([0-9]+-[0-9]+)"). This URL will be used by RAMOSE for matching the
        particular API calls with the specific operation to execute.
        """
        result = i["url"]

        for term in findall(PARAM_NAME, result):
            try:
                t = i[term]
            except KeyError:
                t = "str(.+)"
            result = result.replace("{%s}" % term, "%s" % sub("^[^\(]+(\(.+\))$", "\\1", t))

        return "%s%s" % (b, result)

    def best_match(self, u):
        """
        This method takes an URL of an API call in input and find the API operation URL and the related
        configuration that best match with the API call, if any.
        """
        #u = u.decode('UTF8') if isinstance(u, (bytes, bytearray)) else u
        cur_u = sub("\?.*$", "", u)
        result = None, None
        for base_url in self.all_conf:
            if u.startswith(base_url):
                conf = self.all_conf[base_url]
                for pat in conf["conf"]:
                    if match("^%s$" % pat, cur_u):
                        result = conf, pat
                        break
        return result
    # END: Ancillary methods

    # START: Processing methods
    def get_op(self, op_complete_url):
        """
        This method returns a new object of type Operation which represent the operation specified by
        the input URL (parameter 'op_complete_url)'. In case no operation can be found according by checking
        the configuration files available in the APIManager, a tuple with an HTTP error code and a message
        is returned instead.
        """
        url_parsed = urlsplit(op_complete_url)
        op_url = url_parsed.path

        conf, op = self.best_match(op_url)
        if op is not None:
            return Operation(op_complete_url,
                             op,
                             conf["conf"][op],
                             conf["tp"],
                             conf["sparql_http_method"],
                             conf["addon"])
        else:
            sc = 404
            return sc, "HTTP status code %s: the operation requested does not exist" % sc, "text/plain"
    # END: Processing methods


if __name__ == "__main__": # pragma: no cover
    arg_parser = ArgumentParser("ramose.py", description="The 'Restful API Manager Over SPARQL Endpoints' (a.k.a. "
                                                         "'RAMOSE') is an application that allows one to expose a "
                                                         "Restful API interface, according to a particular "
                                                         "specification document, to interact with a SPARQL endpoint.")

    arg_parser.add_argument("-s", "--spec", dest="spec", required=True, nargs='+',
                            help="The file(s) in hash format containing the specification of the API(s).")
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
    am = APIManager(args.spec)
    dh = HTMLDocumentationHandler(am)

    css_path = args.css if args.css else None

    if args.webserver:
        try:


            # logs
            dh.logger_ramose()

            # web server
            host_name = args.webserver.rsplit(':', 1)[0] if ':' in args.webserver else '127.0.0.1'
            port = args.webserver.rsplit(':', 1)[1] if ':' in args.webserver else '8080'

            app = Flask(__name__)
            # This is due to Flask routing rules that do not accept URLs without the starting slash
            # but ramose calls start with the slash, hence we remove it if the flag args.webserver is added
            if args.call:
                args.call = args.call[1:]

            # routing
            @app.route('/')
            def home():
                index = dh.get_index(css_path)
                return index

            @app.route('/<path:api_url>')
            # @app.route('/<path:api_url>/')
            def doc(api_url):
                """ APIs documentation page and operations """
                res, status = dh.get_index(css_path), 404
                if any(api_u in '/'+api_url for api_u, api_dict in am.all_conf.items()):
                    # documentation
                    if any(api_u == '/'+api_url for api_u,api_dict in am.all_conf.items()):
                        status, res = dh.get_documentation(css_path, api_url)
                        return res, status
                    # api calls
                    else:
                        cur_call = '/'+api_url
                        format = request.args.get('format')
                        content_type = "text/csv" if format is not None and "csv" in format else "application/json"

                        op = am.get_op(cur_call+'?'+unquote(request.query_string.decode('utf8')))
                        if type(op) is Operation:  # Operation found
                            status, res, c_type = op.exec(content_type=content_type)
                        else:  # HTTP error
                            status, res, c_type = op

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
                                m_res = {"error": status, "message": res}
                                mes = dumps(m_res)
                                response = make_response(mes, status)
                            response.headers.set('Content-Type', content_type) # overwrite text/plain

                            # allow CORS anyway
                        response.headers.set('Access-Control-Allow-Origin', '*')
                        response.headers.set('Access-Control-Allow-Credentials', 'true')

                        return response
                else:
                    return res, status
            app.run(host=str(host_name), debug=False, port=str(port))

        except Exception as e:
            exc_type, exc_obj, exc_tb = exc_info()
            fname = pt.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print("[ERROR]", exc_type, fname, exc_tb.tb_lineno)

    else:
        # run locally via shell
        if args.doc:
            res = dh.get_documentation(css_path) + ("text/html", )
        else:
            op = am.get_op(args.call)
            if type(op) is Operation:  # Operation found
                res = op.exec(args.method, args.format)
            else:  # HTTP error
                res = op

        if args.output is None:
            print("# Response HTTP code: %s\n# Body:\n%s\n# Content-type: %s" % res)
        else:
            with open(args.output, "w", encoding='utf8') as f:
                f.write(res[1])
