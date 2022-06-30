[![Python package](https://github.com/dbrembilla/ramose/actions/workflows/python-package.yml/badge.svg)](https://github.com/dbrembilla/ramose/actions/workflows/python-package.yml)
[![Coverage](./test/coverage/coverage.svg)](https://github.com/dbrembilla/ramose/actions/workflows/python-package.yml)
# Restful API Manager Over SPARQL Endpoints (RAMOSE)

Restful API Manager Over SPARQL Endpoints (RAMOSE) is an application that allows agile development and publication of documented RESTful APIs for querying SPARQL endpoints, according to a particular specification document.

## TOC

 * [Configuration](#Configuration)
    * [Requirements](#Requirements)
    * [Arguments](#Arguments)
    * [Hashformat configuration file](#Hashformat-configuration-file)
    * [Addon python files](#Addon-python-files)
 * [Run RAMOSE](#Run-RAMOSE)
    * [Run locally](#Run-locally)
    * [Run with webserver](#Run-with-webserver)
 * [RAMOSE APIManager](#RAMOSE-APIManager)
 * [Other functionalities and examples](#Other-functionalities-and-examples)
    * [Parameters and filters](#Parameters-and-filters)
    * [Examples](#Examples)

## Configuration

### Requirements

RAMOSE is compatible to Python 3.7 to 3.10. To install RAMOSE use: `pip install ramose` or `pip3 install ramose`. You can find the documentation [here](https://ramose.readthedocs.io/en/latest/).

### Arguments

RAMOSE application accepts the following arguments:

```
    -h, --help            show this help message and exit
    -s SPEC, --spec SPEC  The file in hashformat containing the specification of the API.
    -m METHOD, --method METHOD
                          The method to use to make a request to the API.
    -c CALL, --call CALL  The URL to call for querying the API.
    -f FORMAT, --format FORMAT
                          The format in which to get the response.
    -d, --doc             Say to generate the HTML documentation of the API (if it is specified, all the arguments '-m', '-c', and '-f' won't be considered).
    -o OUTPUT, --output OUTPUT
                          A file where to store the response.
    -w WEBSERVER, --webserver WEBSERVER
                          The host:port where to deploy a Flask webserver for testing the API.
    -css CSS, --css CSS   The path of a .css file for styling the API documentation (to be specified either with '-w' or with '-d' and '-o' arguments).
```

`-s` is a mandatory argument identifying the configuration file of the API (an hashformat specification file, `.hf`).

### Hashformat configuration file

A hashformat file (`.hf`) is a specification file that includes metadata about an API, the operations it allows to perform, descriptions, and instructions to perform operations over a SPARQL endpoint. The `.hf` file is parsed by RAMOSE to perform requested operations and generate the documentation of the API.

The syntax is based on a simplified version of markdown and it includes one or more sections, separated by a empty line.

```
#<field_name_1> <field_value_1>
#<field_name_1> <field_value_2>
#<field_name_3> <field_value_3>

#<field_name_n> <field_value_n>
...
```

The first section of the specification includes mandatory information about the API, namely:

```
#url <api_base>                     _partial URL of the API_
#type api                           _the type of section_
#base <base_url>                    _URL base_
#method <get|post>                  
#title <api_title>                  
#description <api_description>
#version <version_number>
#license <license>
#contacts <contact_url>             _in the form [text](url)_
#endpoint <sparql_endpoint_url>     
#addon <addon_file_name>            _optional additional python module_
```

The field `#url` includes the partial URL of the API, while the field `#base` includes the URL base that can be shared with other services or APIs.

[N.B. Several APIs may coexist and be handled by RAMOSE, hence the path specified in the field `#url` corresponds to the unique identifier of the API.]

For example:

```
#url /api/v1
#type api
#base https://w3id.org/oc/wikidata
#method post
#title Wikidata REST API
#description A RAMOSE API implementation for Wikidata
#version 0.0.2
#license This document is licensed with a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode), while the REST API itself has been created using [RAMOSE](https://github.com/opencitations/ramose), the *Restful API Manager Over SPARQL Endpoints* created by [Silvio Peroni](https://orcid.org/0000-0003-0530-4305), which is licensed with an [ISC license](https://opensource.org/licenses/ISC). All the data returned by this API are made freely available under a [Creative Commons public domain dedication (CC0)](https://creativecommons.org/publicdomain/zero/1.0/).
#contacts [contact@opencitations.net](mailto:contact@opencitations.net)
#endpoint https://query.wikidata.org/sparql
#addon test_addon
```



In the other section(s) of the specification file is detailed the behaviour of the API for each operation allowed. Each operation corresponds to a section.

```
#url <operation_url>{var}                   _partial URL of operation and variable name_
#type operation                             _the type of section_
#<var> <var_validator>                      _optional validator of input variable_
#preprocess <preprocess_operations>         _methods for preprocessing defined in addon file_
#postprocess <postprocess_operations>       _methods for postprocessing defined in addon file_
#method <get|post>
#description <operation_description>        
#call <example_request_call>
#field_type <var_type_list>                 _list of (SPARQL query) variables and their type_
#output_json <example_json_response>
#sparql <sparql_query>                      _SPARQL query to be performed over the endpoint_
```

For example:

```
#url /metadata/{dois}
#type operation
#dois str(\"?10\..+[^_\"]((__|\" \")10\..+[^_])*\"?)
#preprocess upper(dois) --> split_dois(dois)
#postprocess distinct()
#method get
#description This operation retrieves the metadata for all the articles identified by the input DOIs.
#call /metadata/10.1108/jd-12-2013-0166__10.1038/nature12373
#field_type str(qid) str(author) datetime(year) str(title) str(source_title) str(source_id) str(volume) str(issue) str(page) str(doi) str(reference) int(citation_count)
#output_json [
    {
        "source_title": "Journal of Documentation",
        "page": "253-277",
        ...
    },
    {
        "source_title": "Nature",
        "page": "54-58",
        ...
    }
]
#sparql PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT ?author ?year ?title ?source_title ?volume ?issue ?page ?doi ?reference ?citation_count ?qid {
  VALUES ?doi { [[dois]] }
  ?article wdt:P356 ?doi .

  BIND(STRAFTER(str(?article), "http://www.wikidata.org/entity/") as ?qid) .

  {
    SELECT DISTINCT ?article (GROUP_CONCAT(?cited_doi; separator="; ") as ?reference) {
      VALUES ?doi { [[dois]] }
      ?article wdt:P356 ?doi .
      OPTIONAL {
        ?article wdt:P2860 ?cited .
        OPTIONAL {
          ?cited wdt:P356 ?cited_doi .
        }
      }
    } GROUP BY ?article
  }
  {
    SELECT ?article ?doi (count(?doi) as ?citation_count) {
      VALUES ?doi { [[dois]] }
      ?article wdt:P356 ?doi .
      OPTIONAL { ?article ^wdt:P2860 ?other }
    } GROUP BY ?article ?doi
  }
  OPTIONAL { ?article wdt:P1476 ?title }
  OPTIONAL {
    ?article wdt:P577 ?date
    BIND(SUBSTR(str(?date), 0, 5) as ?year)
  }
  OPTIONAL { ?article wdt:P1433/wdt:P1476 ?source_title }
  OPTIONAL { ?article wdt:P478 ?volume }
  OPTIONAL { ?article wdt:P433 ?issue }
  OPTIONAL { ?article wdt:P304 ?page }
  {
    SELECT ?article ?doi (GROUP_CONCAT(?a; separator="; ") as ?author) {
      VALUES ?doi { [[dois]] }

      {
        SELECT ?article ?doi ?a {
          VALUES ?doi { [[dois]] }

          ?article wdt:P356 ?doi .

          OPTIONAL {
            ?article wdt:P50 ?author_res .
            ?author_res wdt:P735/wdt:P1705 ?g_name ;
                        wdt:P734/wdt:P1705 ?f_name .
            BIND(CONCAT(?f_name, ", ",?g_name) as ?a)
          }
        } GROUP BY ?article ?doi ?a ORDER BY DESC(?a)}
    } GROUP BY ?article ?doi
  }
} LIMIT 1000
```


### Addon python files

Additional python modules can be added for preprocessing variables in the API URL call, and for postprocessing responses. In the specification file, addons are specified in the `#addon` field by recording the name of the python file.

**Preprocessing**

RAMOSE preprocesses the URL of the API call according to the functions specified in the `#preprocess` field (e.g. `"#preprocess lower(doi)"`), which is applied to the specified parameters of the URL specified as input of the function in consideration (e.g. "/api/v1/citations/10.1108/jd-12-2013-0166", converting the DOI in lowercase).

It is possible to run multiple functions sequentially by concatenating them with `-->` in the API specification document. In this case the output of the function `f_i` will becomes the input operation URL of the function `f_i+1`.

Finally, it is worth mentioning that all the functions specified in the `#preprocess` field must return a tuple of strings defining how the particular value indicated by the URL parameter must be changed.

**Postprocessing**

RAMOSE takes the result table returned by the SPARQL query performed against the triplestore (as specified in an API operation as input) and change some of such results according to the functions specified in the `#postprocess` field (e.g. `"#postprocess remove_date("2018")"`).

These functions can take parameters as input, while the first unspecified parameters will be always the result table. It is worth mentioning that this result table (i.e. a list of tuples) actually contains, in each cell, a tuple defining the plain value as well as the typed value for enabling better comparisons and operations if needed. An example of this table of result is shown as follows:

```
    [
        ("id", "date"),
        ("my_id_1", "my_id_1"), (datetime(2018, 3, 2), "2018-03-02"),
        ...
    ]
```

In addition, it is possible to run multiple functions sequentially by concatenating them with `"-->"` in the API specification document. In this case the output of the function `f_i` will becomes the input result table of the function `f_i+1`.
 
The postprocess function should output a tuple containing the result and whether the function needs to return the type of values in the result.

## Run RAMOSE

### Run locally

RAMOSE can be run via CLI by specifying configuration file and URL of the desired operation (including parameters). For example, run in the root directory:

```
python -m ramose -s <conf_name>.hf -c '<api_base><api_operation_url>?<parameters>'
```

Results are streamed in the shell in the following format:

```
# Response HTTP code: <status_code>
# Body: <response_content>
# Content-type: <format>
```

**Output formats.** RAMOSE returns responses in two formats, namely: `text/csv` and `application/json`. Formats can be specified as values of the argument `-f` or, alternatively, as parameters of the call. For example:

```
python -m ramose -f <csv|json> -s <conf_name>.hf -c '<api_base><api_operation_url>|<api_base><api_operation_url>?<parameters>'

python -m ramose -s <conf_name>.hf -c '<api_base><api_operation_url>|<api_operation_url>?format=<csv|json>'
```

If no format is specified, a JSON response is returned.

**Ouput.** To store responses in a local file, use the argument `-o` to specify the output file:

```
python -m ramose -s <conf_name>.hf -c '<api_base><api_operation_url>?<parameters>' -o '<file_name>.<format>'
```

**API Documentation.** To produce an HTML document including the automatically generated documentation of the API, use the arguments `-d` and `-o` to specify the output file:

```
python -m ramose -s <conf_name>.hf -d -o <doc_name>.html
```

### Run with webserver

Additionally, a Flask webserver is available for testing and debugging purposes by specifying as value of the argument `-w` the desired `<host>:<port>`. For example, to run your API in localhost:

```
python -m ramose -s <conf_name>.hf -w 127.0.0.1:8080
```

The web application includes:

 * a basic dashboard for tracking API calls (available at `<host>:<port>/`)
 * the documentation of the API (available at `<host>:<port>/<api_base>`)

The local API can be tested via browser or via curl:

```
 curl -X GET --header "Accept: <format>" "http://<host>:<port>/<api_base><operation_url>?<parameters>"
```

**Custom CSS** Both when running via CLI and with webserver, the path to a custom .css file can be specified in the `-css` argument to style dashboard and documentation pages.

```
python -m ramose -s <conf_name>.hf -w 127.0.0.1:8080 -css <path/to/file.css>
```

## RAMOSE `APIManager`

RAMOSE allows developers to handle several APIs by instantiating the main class `APIManager` and initialising it with a specification file.

The method `get_op(op_complete_url)` takes in input the url of the call (i.e. the API base URL plus the operation URL) and returns an object of type `Operation`. The instance of an `Operation` can be used to run the method `exec(method="get", content_type="application/json")`, which takes in input the url the HTTP method to use for the call and and the content type to return, and executes the operation as indicated in the specification file, by running (in the following order):

  1. the methods to preprocess the query (as defined in the specification file at `#{var}` and `#preprocess`);
  2. the SPARQL query related to the operation called, by using the parameters indicated in the URL (`#sparql`);
  3. the specification of all the types of the various rows returned (`#field_type`);
  4. the methods to postprocess the result (`#postprocess`);
  5. the application of the filter to remove, filter, sort the result (parameters);
  6. the removal of the types added at the step 3, so as to have a data structure ready to be returned;
  7. the conversion in the format requested by the user (`content_type`).

For example:

```
api_manager = APIManager([ "1_v1.hf", "2_v1.hf" ])

api_base_1 = "..."
api_base_2 = "..."
operation_url_1 = "..."
operation_url_2 = "..."
request = "..."
call_1 = "%s/%s/%s" % (api_base_1, operation_url_1, request)
call_2 = "%s/%s/%s" % (api_base_2, operation_url_2, request)

op1 = api_manager.get_op(call_1)
status1, result1, result_format1  = op1.exec()

op2 = api_manager.get_op(call_2)
status2, result2, result_format2 = op2.exec()
```

## Other functionalities and examples

### Parameters and filters

Parameters can be used to filter and control the results returned by the API. They are passed as normal HTTP parameters in the URL of the call. They are:

 * `require=<field_name>`: all the rows that have an empty value in the `<field_name>` specified are removed from the result set - e.g. `require=given_name` removes all the rows that do not have any string specified in the `given_name` field.

 * `filter=<field_name>:<operator><value>`: only the rows compliant with <value> are kept in the result set. The parameter `<operation>` is not mandatory. If `<operation>` is not specified, `<value>` is interpreted as a regular expression, otherwise it is compared by means of the specified operation. Possible operators are "=", "<", and ">". For instance, `filter=title:semantics?` returns all the rows that contain the string "semantic" or "semantics" in the field title, while `filter=date:>2016-05` returns all the rows that have a date greater than May 2016.

 * `sort=<order>(<field_name>)`: sort in ascending (`<order>` set to `"asc"`) or `descending` (`<order>` set to `"desc"`) order the rows in the result set according to the values in `<field_name>`. For instance, `sort=desc(date)` sorts all the rows according to the value specified in the field date in descending order.

 * `format=<format_type>`: the final table is returned in the format specified in `<format_type>` that can be either `"csv"` or `"json"` - e.g. `format=csv` returns the final table in CSV format. This parameter has higher priority of the type specified through the "Accept" header of the request. Thus, if the header of a request to the API specifies `Accept: text/csv` and the URL of such request includes `format=json`, the final table is returned in JSON.

 * `json=<operation_type>("<separator>",<field>,<new_field_1>,<new_field_2>,...)`: in case a JSON format is requested in return, transform each row of the final JSON table according to the rule specified. If `<operation_type>` is set to `"array"`, the string value associated to the field name `<field>` is converted into an array by splitting the various textual parts by means of `<separator>`. For instance, considering the JSON table `[ { "names": "Doe, John; Doe, Jane" }, ... ]`, the execution of `array("; ",names)` returns `[ { "names": [ "Doe, John", "Doe, Jane" ], ... ]`. Instead, if `<operation_type`> is set to `"dict"`, the string value associated to the field name <field> is converted into a dictionary by splitting the various textual parts by means of <separator> and by associating the new fields `<new_field_1>`, `<new_field_2>`, etc., to these new parts. For instance, considering the JSON table `[ { "name": "Doe, John" }, ... ]`, the execution of `dict(", ",name,fname,gname)` returns `[ { "name": { "fname": "Doe", "gname": "John" }, ... ]`.

It is possible to specify one or more filtering operation of the same kind (e.g. `require=given_name&require=family_name`). In addition, these filtering operations are applied in the order presented above - first all the `require` operation, then all the `filter` operations followed by all the `sort` operation, and finally the `format` and the `json` operation (if applicable). It is worth mentioning that each of the aforementioned rules is applied in order, and it works on the structure returned after the execution of the previous rule.

Example:

```
 <api_operation_url>?require=doi&filter=date:>2015&sort=desc(date).
```

### Examples

#### Query wikidata endpoint from CLI

Use the following files to test the application.

 * `test/ramose.py`
 * `test/test.hf`
 * `test/test_addon.hf`

**Q1** Retrieve bibliographic metadata related to the work identified by the doi `10.1080/14756366.2019.1680659`:

```
python -m ramose -s test.hf -c '/api/v1/metadata/10.1107/S0567740872003322'
```

Returns:

```
# Response HTTP code: 200
# Body:
[
    {
        "author": "",
        "year": "1972",
        "title": "The crystal structure of tin(II) sulphate",
        "source_title": "Acta crystallographica. Section B",
        "volume": "28",
        "issue": "3",
        "page": "864-867",
        "doi": "10.1107/S0567740872003322",
        "reference": "",
        "citation_count": "1",
        "qid": "Q29013687"
    }
]
# Content-type: application/json
```

**Q2** Retrieve bibliographic metadata of a list of works identified by their dois -- separated by `__` as specified in the field `#dois` of `test.hf` -- , and return data in `csv` format.

```
python -m ramose -s test.hf -c '/api/v1/metadata/10.1107/S0567740872003322__10.1007/BF02020444?format=csv'
```

Returns:

```
# Response HTTP code: 200
# Body:
author,year,title,source_title,volume,issue,page,doi,reference,citation_count,qid
,1972,The crystal structure of tin(II) sulphate,Acta crystallographica. Section B,28,3,864-867,10.1107/S0567740872003322,,1,Q29013687
"Erdős, Paul; Hajnal, András",1966,On chromatic number of graphs and set-systems,Acta Mathematica Hungarica,17,1-2,61-99,10.1007/BF02020444,10.4153/CJM-1959-003-9,1,Q57259020
# Content-type: text/csv
```

**Q3** Perform **Q2** and sort results by year in ascending order:

```
python -m ramose -s test.hf -c '/api/v1/metadata/10.1107/S0567740872003322__10.1007/BF02020444?format=csv&sort=asc(year)'
```

**Q4** Perform **Q3** but return in JSON format, and split authors' names by the separator `; `

```
python -m ramose -s test.hf -c '/api/v1/metadata/10.1107/S0567740872003322__10.1007/BF02020444?format=json&sort=asc(year)&json=array("; ", author)'
```

Returns

```
# Response HTTP code: 200
# Body:
[
    {
        "author": [
            "Erdős, Paul",
            "Hajnal, András"
        ],
        "year": "1966",
        "title": "On chromatic number of graphs and set-systems",
        "source_title": "Acta Mathematica Hungarica",
        "volume": "17",
        "issue": "1-2",
        "page": "61-99",
        "doi": "10.1007/BF02020444",
        "reference": "10.4153/CJM-1959-003-9",
        "citation_count": "1",
        "qid": "Q57259020"
    },
    {
        "author": [],
        "year": "1972",
        "title": "The crystal structure of tin(II) sulphate",
        "source_title": "Acta crystallographica. Section B",
        "volume": "28",
        "issue": "3",
        "page": "864-867",
        "doi": "10.1107/S0567740872003322",
        "reference": "",
        "citation_count": "1",
        "qid": "Q29013687"
    }
]
# Content-type: application/json
```

#### Query wikidata endpoint from webserver

Perform **Q2** from the local webserver

```
python -m ramose -s <conf_name>.hf -w 127.0.0.1:8080
curl -X GET --header "Accept: text/csv" "http://localhost:8080/api/v1/metadata/10.1107/S0567740872003322__10.1007/BF02020444?format=csv"
```

The same query can be directly performed on the browser at `http://localhost:8080/api/v1/metadata/10.1107/S0567740872003322__10.1007/BF02020444?format=csv`
