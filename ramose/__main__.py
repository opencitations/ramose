# SPDX-FileCopyrightText: 2018-2021 Silvio Peroni <silvio.peroni@unibo.it>
# SPDX-FileCopyrightText: 2020-2021 Marilena Daquino <marilena.daquino2@unibo.it>
# SPDX-FileCopyrightText: 2022 Davide Brembilla
# SPDX-FileCopyrightText: 2024 Ivan Heibi <ivan.heibi2@unibo.it>
# SPDX-FileCopyrightText: 2025 Sergei Slinkin
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from argparse import ArgumentParser
from csv import writer
from io import StringIO
from json import dumps
from os import path as pt
from urllib.parse import unquote

from flask import Flask, make_response, request

from ramose.api_manager import APIManager
from ramose.html_documentation import HTMLDocumentationHandler
from ramose.openapi_documentation import OpenAPIDocumentationHandler
from ramose.operation import Operation


def main():  # pragma: no cover
    arg_parser = ArgumentParser("ramose", description="The 'Restful API Manager Over SPARQL Endpoints' (a.k.a. "
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
    arg_parser.add_argument("--openapi", dest="openapi", default=False, action="store_true",
                            help="Export the API specification to OpenAPI 3.0 YAML.")
    arg_parser.add_argument("--api-base", dest="api_base", default=None,
                            help="When exporting docs/OpenAPI with multiple specs loaded, choose which API base URL to export.")
    arg_parser.add_argument("-o", "--output", dest="output",
                            help="A file where to store the response.")
    arg_parser.add_argument("-w", "--webserver", dest="webserver", default=False,
                            help="The host:port where to deploy a Flask webserver for testing the API.")
    arg_parser.add_argument("-css", "--css", dest="css",
                            help="The path of a .css file for styling the API documentation (to be specified either with '-w' or with '-d' and '-o' arguments).")

    args = arg_parser.parse_args()
    am = APIManager(args.spec)
    dh = HTMLDocumentationHandler(am)
    oah = OpenAPIDocumentationHandler(am)

    css_path = args.css if args.css else None

    if args.webserver:
        try:
            dh.logger_ramose()

            host_name = args.webserver.rsplit(':', 1)[0] if ':' in args.webserver else '127.0.0.1'
            port = args.webserver.rsplit(':', 1)[1] if ':' in args.webserver else '8080'

            app = Flask(__name__)

            # This is due to Flask routing rules that do not accept URLs without the starting slash
            # but ramose calls start with the slash, hence we remove it if the flag args.webserver is added
            if args.call:
                args.call = args.call[1:]

            @app.route('/')
            def home():

                index = dh.get_index(css_path)
                return index

            @app.route('/<path:api_url>')
            def doc(api_url):
                res, status = dh.get_index(css_path), 404
                # --- OpenAPI export endpoint ---
                # Example: /api/v1/openapi.yaml  (or .yml)
                if api_url.endswith("openapi.yaml") or api_url.endswith("openapi.yml"):
                    base = api_url.rsplit("/", 1)[0]  # e.g. "api/v1"
                    if "/" + base in am.all_conf:
                        status, yml = oah.get_documentation(base_url=base)
                        response = make_response(yml, status)
                        response.headers.set("Content-Type", "application/yaml")
                        response.headers.set("Access-Control-Allow-Origin", "*")
                        response.headers.set("Access-Control-Allow-Credentials", "true")
                        return response
                    else:
                        return res, status
                # --- end OpenAPI export endpoint ---
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
                        if isinstance(op, Operation):
                            status, res, c_type = op.exec(content_type=content_type)
                        else:
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

            app.run(host=str(host_name), debug=True, port=int(port))

        except Exception as e:
            tb = e.__traceback__
            fname = pt.split(tb.tb_frame.f_code.co_filename)[1] if tb else "?"
            print("[ERROR]", type(e).__name__, fname, tb.tb_lineno if tb else "?")

    else:
        # run locally via shell
        if args.openapi:
            res = oah.get_documentation(base_url=args.api_base) + ("application/yaml", )
        elif args.doc:
            res = dh.get_documentation(css_path) + ("text/html", )
        else:
            op = am.get_op(args.call)
            if isinstance(op, Operation):
                res = op.exec(args.method, args.format)
            else:
                res = op

        if args.output is None:
            print("# Response HTTP code: %s\n# Body:\n%s\n# Content-type: %s" % res)
        else:
            with open(args.output, "w") as f:
                f.write(res[1])


if __name__ == "__main__":  # pragma: no cover
    main()
