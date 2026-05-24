# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import logging
from pathlib import Path
from re import findall, split, sub
from typing import TYPE_CHECKING

from markdown import markdown

from ramose._constants import FIELD_TYPE_RE, PARAM_NAME
from ramose.documentation import DocumentationHandler
from ramose.hash_format import parse_custom_params, parse_disable_params

if TYPE_CHECKING:
    from ramose.api_manager import APIConfig


class HTMLDocumentationHandler(DocumentationHandler):
    # HTML documentation: START
    def __title(self, conf: APIConfig) -> str:
        """This method returns the title string defined in the API specification."""
        return conf["conf_json"][0]["title"]

    def __htmlmetadescription(self, conf: APIConfig) -> str:
        """This method returns the HTML meta-description tag defined in the API specification."""
        desc = conf["conf_json"][0].get("html_meta_description")
        if desc:
            return f'<meta name="description" content="{desc}"/>'
        return ""  # pragma: no cover

    def __sidebar(self, conf: APIConfig) -> str:
        """This method builds the sidebar of the API documentation"""
        i = conf["conf_json"][0]
        ops_html = "".join(
            f"<li><a class='btn' href='#{op['url']}'>{op['url']}</a></li>" for op in conf["conf_json"][1:]
        )
        return f"""

        <h4>{i["title"]}</h4>
        <ul id="sidebar_menu" class="sidebar_menu">
            <li><a class="btn active" href="#description">DESCRIPTION</a></li>
            <li><a class="btn" href="#parameters">PARAMETERS</a></li>
            <li><a class="btn" href="#operations">OPERATIONS</a>
                <ul class="sidebar_submenu">{ops_html}</ul>
            </li>
            <li><a class="btn active" href="/">HOME</a></li>
        </ul>
        """

    def __header(self, conf: APIConfig) -> str:
        """This method builds the header of the API documentation"""
        i = conf["conf_json"][0]
        api_url = i["base"] + i["url"]
        result = f"""
<a id='toc'></a>
# {i["title"]}

**Version:** {i["version"]} <br/>
**API URL:** <a href="{api_url}">{api_url}</a><br/>
**Contact:** {i["contacts"]}<br/>
**License:** {i["license"]}<br/>



## <a id="description"></a>Description [back to top](#toc)

{i["description"]}

{self.__parameters(conf)}"""
        return markdown(result)

    _BUILTIN_PARAM_DOCS: tuple[tuple[str, str], ...] = (
        (
            "require",
            "`require=<field_name>`: all the rows that have an empty value in the `<field_name>` specified are "
            "removed from the result set - e.g. `require=given_name` removes all the rows that do not have any "
            "string specified in the `given_name` field.",
        ),
        (
            "filter",
            "`filter=<field_name>:<operator><value>`: only the rows compliant with `<value>` are kept in the "
            "result set. The parameter `<operation>` is not mandatory. If `<operation>` is not specified, "
            "`<value>` is interpreted as a regular expression, otherwise it is compared by means of the specified "
            'operation. Possible operators are "=", "<", and ">". For instance, `filter=title:semantics?` returns '
            'all the rows that contain the string "semantic" or "semantics" in the field `title`, while '
            "`filter=date:>2016-05` returns all the rows that have a `date` greater than May 2016.",
        ),
        (
            "sort",
            '`sort=<order>(<field_name>)`: sort in ascending (`<order>` set to "asc") or descending (`<order>` '
            'set to "desc") order the rows in the result set according to the values in `<field_name>`. For '
            "instance, `sort=desc(date)` sorts all the rows according to the value specified in the field `date` "
            "in descending order.",
        ),
        (
            "format",
            "`format=<format_type>`: the final table is returned in the format specified in `<format_type>` that "
            'can be either "csv" or "json" - e.g. `format=csv` returns the final table in CSV format. This '
            'parameter has higher priority of the type specified through the "Accept" header of the request. Thus, '
            "if the header of a request to the API specifies `Accept: text/csv` and the URL of such request "
            "includes `format=json`, the final table is returned in JSON.",
        ),
        (
            "json",
            '`json=<operation_type>("<separator>",<field>,<new_field_1>,<new_field_2>,...)`: in case a JSON format '
            "is requested in return, tranform each row of the final JSON table according to the rule specified. "
            'If `<operation_type>` is set to "array", the string value associated to the field name `<field>` is '
            "converted into an array by splitting the various textual parts by means of `<separator>`. For "
            'instance, considering the JSON table `[ { "names": "Doe, John; Doe, Jane" }, ... ]`, the execution '
            'of `array("; ",names)` returns `[ { "names": [ "Doe, John", "Doe, Jane" ], ... ]`. Instead, if '
            '`<operation_type>` is set to "dict", the string value associated to the field name `<field>` is '
            "converted into a dictionary by splitting the various textual parts by means of `<separator>` and by "
            "associating the new fields `<new_field_1>`, `<new_field_2>`, etc., to these new parts. For instance, "
            'considering the JSON table `[ { "name": "Doe, John" }, ... ]`, the execution of '
            '`dict(", ",name,fname,gname)` returns `[ { "name": { "fname": "Doe", "gname": "John" }, ... ]`.',
        ),
    )

    def __parameters(self, conf: APIConfig) -> str:
        overridden: set[str] = set()
        api_meta = conf["conf_json"][0]
        if "disable_params" in api_meta:
            overridden.update(parse_disable_params(api_meta["disable_params"]))
        for op in conf["conf_json"][1:]:
            if "custom_params" in op:
                overridden.update(parse_custom_params(op["custom_params"]))
            if "disable_params" in op:
                overridden.update(parse_disable_params(op["disable_params"]))

        builtin_params = [text for param_name, text in self._BUILTIN_PARAM_DOCS if param_name not in overridden]

        if not builtin_params:
            return ""

        items = "\n\n".join(f"{idx}. {text}" for idx, text in enumerate(builtin_params, 1))
        params_intro = (
            "Parameters can be used to filter and control the results returned by the API."
            " They are passed as normal HTTP parameters in the URL of the call. They are:"
        )
        filtering_note = (
            "It is possible to specify one or more filtering operation of the same kind"
            " (e.g. `require=given_name&require=family_name`). In addition, these filtering"
            " operations are applied in the order presented above - first all the `require`"
            " operation, then all the `filter` operations followed by all the `sort`"
            " operation, and finally the `format` and the `json` operation (if applicable)."
            " It is worth mentioning that each of the aforementioned rules is applied in"
            " order, and it works on the structure returned after the execution of the"
            " previous rule."
        )
        result = f"""## <a id="parameters"></a>Parameters [back to top](#toc)

{params_intro}

{items}

{filtering_note}

Example: `<api_operation_url>?require=doi&filter=date:>2015&sort=desc(date)`."""
        return markdown(result)

    def __operations(self, conf: APIConfig) -> str:
        """This method returns the description of all the operations defined in the API."""
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
                    p_type, p_shape = findall(r"^\s*([^\(]+)\((.+)\)\s*$", op[p])[0]

                params.append(
                    f"<em>{p}</em>: type <code>{p_type}</code>, regular expression shape <code>{p_shape}</code>",
                )

            if "custom_params" in op:
                for param_name, param_conf in parse_custom_params(op["custom_params"]).items():
                    params.append(f"<em>{param_name}</em> (query, optional): {param_conf['description']}")

            op_url = op["url"]
            methods = ", ".join(split(r"\s+", op["method"].strip()))
            params_html = "<ul><li>" + "</li>\n<li>".join(params) + "</li></ul>" if params else ""
            has_custom_default = "default_format" in op and op["default_format"].strip().lower() not in ("csv", "json")
            fields_html = (
                ", ".join(f"{f} <em>({t})</em>" for t, f in findall(FIELD_TYPE_RE, op["field_type"]))
                if "field_type" in op and not has_custom_default
                else ""
            )
            example_url = conf["website"] + conf["base_url"] + op["call"]

            fields_type_html = (
                '<p class="attr"><strong>Result fields type</strong>'
                '<span class="attr_val">' + fields_html + "</span></p>"
                if fields_html
                else ""
            )
            exemplar_html = (
                '<p class="ex attr"><strong>Exemplar output (in JSON)'
                "</strong></p>" + chr(10) + "<pre><code>" + op["output_json"] + "</code></pre>"
                if "output_json" in op
                else ""
            )
            example_link = f'<a target="_blank" href="{example_url}">{op["call"]}</a>'

            result += f"\n* [{op_url}](#{op_url}): {op['description'].split(chr(10))[0]}"
            ops += f"""<div id="{op_url}">
<h3>{op_url} <a href="#operations">back to operations</a></h3>

{markdown(op["description"])}

<p class="attr"><strong>Accepted HTTP method(s)</strong> <span class="attr_val method">{methods}</span></p>
<div class="attr params"><strong>Parameter(s)</strong>{params_html}</div>
{fields_type_html}
<p class="attr"><strong>Example</strong><span class="attr_val">{example_link}</span></p>
{exemplar_html}</div>"""
        return markdown(result) + ops

    def __footer(self) -> str:
        """This method returns the footer of the API documentation."""
        result = (
            "This API and the related documentation has been created with"
            ' <a href="https://github.com/opencitations/ramose"'
            ' target="_blank">RAMOSE</a>, the *Restful API Manager Over'
            " SPARQL Endpoints*, developed by"
            ' <a href="https://orcid.org/0000-0003-0530-4305"'
            ' target="_blank">Silvio Peroni</a>,'
            ' <a href="https://orcid.org/0000-0002-1113-7550"'
            ' target="_blank">Marilena Daquino</a> and'
            ' <a href="https://orcid.org/0000-0002-8420-0696"'
            ' target="_blank">Arcangelo Massari</a>.'
        )
        return markdown(result)

    def __css(self) -> str:
        return (
            """
        @import url('https://fonts.googleapis.com/css2?family=Karla:wght@300;400&display=swap');
        @media screen and (max-width: 850px) {
              aside { display: none; }
              main, #operations, .dashboard, body>footer {margin-left: 15% !important;}
              #operations > ul:nth-of-type(1) li { display:block !important; max-width: 100% !important; }
              h3 a[href] {display:block !important; float: none !important; font-size: 1rem !important;}
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
            font-size: 1rem;
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
            border-top : solid 0.7px #595959;
        }

        .sidebar_menu a {
            padding: 1% 9%;
            background-image: none !important;
            color: #595959;
            display: block;
        }

        .sidebar_menu a:hover {
            border-left: solid 5px rgba(154, 49, 252,.5);
            font-weight: 400;
        }

        .sidebar_submenu > li {
            padding-left:0px !important;
            background-color:#edf0f2;
            font-size: 1rem;
        }

        main , #operations , .dashboard, body>footer {
            margin-left: 33%;
        }
        .dashboard {text-align: center;}
        main h1+p , .info_api{

            padding-left: 3%;
            font-size: 1rem;
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
            overflow: visible;
            text-overflow: ellipsis;
            max-width: 35%;
            min-height: 200px;
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
            font-size: 1rem;
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
            font-size: 1rem;
            text-align: left;
        }

        .attr > strong {
            width: 30%;
            color: #595959;
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
            color: #54547a;
            padding: 0 2px 0 2px;
            border-radius: 3px;
            font-family : monospace;
            font-size: 1em !important;
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
            font-size: 1rem;
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
            background-image: -webkit-gradient(linear,"""
            "left top, left bottom,"
            "color-stop(70%, transparent),"
            "color-stop(0, rgba(154, 49, 252,.5)));\n"
            """            background-image: linear-gradient(180deg,transparent 70%,rgba(154, 49, 252,.5) 0);
            background-position-y: 3px;
            background-position-x: 0px;
            background-repeat: no-repeat;
            -webkit-transition: .15s ease;
            transition: .15s ease;
        }

        a:hover {
            color: #282828;
            background-image: -webkit-gradient(linear,"""
            "left top, left bottom,"
            "color-stop(70%, transparent),"
            "color-stop(0, rgba(154, 49, 252,.25)));\n"
            """            background-image: linear-gradient(180deg,transparent 70%,rgba(154, 49, 252,.25) 0);
        }

        footer {
            margin-top: 20px;
            border-top: 1px solid lightgrey;
            text-align: center;
            color: #595959;
            font-size: 1rem;
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
            overflow-wrap: break-word;
            word-break: break-word;
        }
        .api_calls div {padding-bottom:2%; overflow-wrap: break-word; word-break: break-word;}

        .api_calls:hover {
          overflow-y: scroll;
        }
        .api_calls h4, .info_api h2 {padding-top: 0px !important; margin-top: 0px !important;}
        .api_calls div p {
          padding: 0.2em 0.5em;
          border-top: solid 1px #F8F8F8;
        }

        .date_log , .method_log {
          color: #595959;
          font-size: 1rem;

        }
        .method_log {margin-left: 15px;}
        .date_log {display:inline-grid;}

        .group_log:nth-child(odd) {
          margin-right:5px;
          font-size: 1rem;
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
           background-color: #595959;
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
        )

    def __css_path(self, css_path: str | None = None) -> str:
        """Add link to a css file if specified in argument -css"""
        return f'<link rel="stylesheet" type="text/css" href=\'{css_path}\'>' if css_path else ""

    def logger_ramose(self) -> None:  # pragma: no cover
        """This method adds logging info to a local file"""
        # logging
        log_formatter = logging.Formatter("[%(asctime)s] [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
        root_logger = logging.getLogger()

        file_handler = logging.FileHandler("ramose.log")
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)

    def __parse_logger_ramose(self) -> str:
        """This method reads logging info stored into a local file, so as to be browsed in the dashboard.
        Returns: the html including the list of URLs of current working APIs and basic logging info"""
        try:
            with Path("ramose.log").open() as l_f:
                logs = l_f.read()
        except FileNotFoundError:
            logs = ""

        seen = set()
        rev_list = []
        for x in reversed(logs.splitlines()):
            if x not in seen:
                seen.add(x)
                rev_list.append(x)

        sidebar_items = "".join(
            f"\n                    "
            f'<li><a class="btn active" href="{api_url}">'
            f"{api_dict['conf_json'][0]['title']}"
            f"</a></li>\n                "
            for api_url, api_dict in self.conf_doc.items()
        )

        html = f"""
        <p></p>
        <aside>
            <h4>RAMOSE API DASHBOARD</h4>
            <ul id="sidebar_menu" class="sidebar_menu">{sidebar_items}
            </ul>
        </aside>
        <header class="dashboard">
            <h1>API MONITORING</h1>"""

        for api_url, api_dict in self.conf_doc.items():
            clean_list = [line for line in rev_list if api_url in line and "debug" not in line]
            api_logs_list = "".join(
                f"<p>{self.clean_log(line, api_url)}</p>" for line in clean_list if self.clean_log(line, api_url) != ""
            )
            api_title = api_dict["conf_json"][0]["title"]
            html += f"""
                <div class="info_api">
                    <h2>{api_title}</h2>
                    <a id="view_doc" href="{api_url}">VIEW DOCUMENTATION</a><br/>
                    <a href="{api_dict["tp"]}" target="_blank">GO TO SPARQL ENDPOINT</a><br/>
                </div>
                <div class="api_calls">
                    <h4>Last calls</h4>
                    <div>
                        {api_logs_list}
                    </div>

                </div>
                """
        return html

    def get_documentation(
        self,
        css_path: str | None = None,
        base_url: str | None = None,
        *_args: object,
        **_dargs: object,
    ) -> tuple[int, str]:
        """This method generates the HTML documentation of an API described in configuration file."""
        if base_url is None:
            first_key = next(iter(self.conf_doc))
            conf = self.conf_doc[first_key]
        else:
            conf = self.conf_doc["/" + base_url]

        return (
            200,
            f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <title>{self.__title(conf)}</title>
        {self.__htmlmetadescription(conf)}
        <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
        <meta name="viewport" content="width=device-width" />
        <style>{self.__css()}</style>
        {self.__css_path(css_path)}
    </head>
    <body>
        <aside>{self.__sidebar(conf)}</aside>
        <main>{self.__header(conf)}</main>
        <section id="operations">{self.__operations(conf)}</section>
        <footer>{self.__footer()}</footer>
    </body>
</html>""",
        )

    def get_index(self, css_path: str | None = None, *_args: object, **_dargs: object) -> str:
        """This method generates the index of all the HTML documentations that can be
        created from the configuration file."""

        return f"""
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <title>RAMOSE</title>
              <meta name="description" content="Documentation of RAMOSE API Manager">
              <style>{self.__css()}</style>
              {self.__css_path(css_path)}
            </head>
            <body>
                {self.__parse_logger_ramose()}
                <footer>{self.__footer()}</footer>
            </body>
            </html>
        """

    def store_documentation(
        self,
        file_path: str,
        css_path: str | None = None,
        *_args: object,
        **_dargs: object,
    ) -> None:
        """This method stores the HTML documentation of an API in a file."""
        _, html = self.get_documentation(css_path)
        with Path(file_path).open("w") as f:
            f.write(html)

    def clean_log(self, log_line: str, api_url: str) -> str:
        """This method parses logs lines into structured data."""
        if "- - " not in log_line:
            return ""
        s = log_line.split("- - ", 1)[1]
        date = s[s.find("[") + 1 : s.find("]")]
        method = s.split('"')[1::2][0].split()[0]
        cur_call = s.split('"')[1::2][0].split()[1].strip()
        status = sub(r"\D+", "", s.split('"', 2)[2])
        if cur_call != api_url + "/":
            full_str = (
                "<span class='group_log'><span class='status_log code_"
                + status
                + "'>"
                + status
                + "</span>"
                + "<span class='date_log'>"
                + date
                + "</span><span class='method_log'>"
                + method
                + "</span></span>"
                + "<span class='group_log'><span class='call_log'><a href='"
                + cur_call
                + "' target='_blank'>"
                + cur_call
                + "</a></span></span>"
            )
        else:
            full_str = ""
        return full_str
