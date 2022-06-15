RAMOSE configuration
====================
In order to configure an API with RAMOSE, you need to crete a hashformat file (.hf) containing the specifications of the API.
Each row of the .hf file contains key-value pairs in the format:

.. code-block:: none

    #<field-name><field-value>
    e.g. #url /api/v1/

Hashformat follows the Markdown syntax. As an example, links can be indicated by using `[text](url)`

We can distinguish two main sections in the necessary configuration file:

* **API Configuration**

* **Operation Configuration**

For an example of a correctly formed hashformat file, you can refer to `this file <https://github.com/opencitations/ramose/blob/master/test/test_data/test.hf>`_. The samples below come from both the aforementioned file and other files available in the `test_data <https://github.com/opencitations/ramose/blob/master/test/test_data>`_ folder.

.. note:: 
    
    Note that while all the examples refer to queries and services focused on persistent identifiers in the study of bibliometrics and the study of the science of science, RAMOSE can be used for any kind of SPARQL service.

API Configuration
------------------

The first section of the configuration file contains information about the API. This section contains the following key-value pairs:

.. code-block:: none

    #url <api_base>: The partial URL of the API.

        #url /api/v1/
        or
        #url /api/
        etc.

    #type api: The type of section (it needs to be api here)

        #type api

    #base <base_url>: The base URL of the website where the API is stored. If you are running an API locally, use localhost rather than the IP address.

        #base http://localhost:8080/
        or
        #base https://w3id.org/oc/wikidata
        etc.

    #method <get|post>: The method of the API calls to the SPARQL endpoint. This can be important as some endpoints require POST calls for big queries. Do not confuse this with the allowed HTTP calls to the API

        #method get
        or
        #method post
        etc.

    #title <api_title>: The title of the API.

        #title REST API for the OpenCitations Corpus

    #description <api_description>: A description of the service built with this configuration file.

        #description This API provides access to the OpenCitations Corpus.

    #version <version_number>: The version of the API. 

        #version 1.0.0

    #license <license>: The license under which the document, the API and the data is published. 

        #license This document is licensed with a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode), while the REST API itself has been created using [RAMOSE](https://github.com/opencitations/ramose), the *Restful API Manager Over SPARQL Endpoints* created by [Silvio Peroni](https://orcid.org/0000-0003-0530-4305), which is licensed with an [ISC license](https://opensource.org/licenses/ISC).

    #contacts <contact_url>: The contact information of the API.

        #contacts [example](mailto:example@mail.org)

    #endpoint <sparql_endpoint_url>: The url of the SPARQL endpoint.

        #endpoint http://opencitations.net/index/sparql 
        or
        #endpoint  https://query.wikidata.org/sparql
        etc.

    #addon <addon_file_name>: Python file containng additional functions for the preprocessing or postprocessing of the data. Remember to remove the .py at the end of the file name.

        #addon preprocess

Complete example:

.. code-block:: none

    #url /api/v1
    #type api
    #base http://localhost:8080
    #title REST API for COCI, the OpenCitations Index of Crossref open DOI-to-DOI references
    #description This document describe the REST API for accessing the data stored in [COCI](https://w3id.org/oc/index/coci) hosted by [OpenCitations](http://opencitations.net). This API implements operations to retrieve the citation data for all the references to other works appearing in a particular bibliographic entity, or the citation data for all the references appearing in other works to a particular bibliographic entity, given the DOI of a bibliographic entity, or to retrieve citation data about a particular citation identified by means of its [Open Citation Identifier (OCI)](https://opencitations.wordpress.com/2018/03/12/citations-as-first-class-data-entities-open-citation-identifiers/).

    All the present operations return either a JSON document (default) or a CSV document according to the mimetype specified in the `Accept` header of the request. If you would like to suggest an additional operation to be included in this API, please use the [issue tracker](https://github.com/opencitations/api/issues) of the OpenCitations APIs available on GitHub.
    #version Version 1.3.0 (2020-03-25)
    #contacts [contact@opencitations.net](mailto:contact@opencitations.net)
    #license This document is licensed with a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/legalcode), while the REST API itself has been created using [RAMOSE](https://github.com/opencitations/ramose), the *Restful API Manager Over SPARQL Endpoints* created by [Silvio Peroni](https://orcid.org/0000-0003-0530-4305), which is licensed with an [ISC license](https://opensource.org/licenses/ISC).
    #endpoint http://opencitations.net/index/sparql
    #method post


Operation Configuration
------------------
The second section of the configuration file should contain the specifications for the behaviour of the API depending on the operations that are performed over it. This section can be repeated multiple times in order to define multiple operations.

.. code-block:: none

    #url <operation_url>{var}: Partial URL of the operation and the variables used.

        #url /oci/{dois}
        or
        #url /metadata/{doi}
        etc.

    #type operation: In this section it needs to be operation

        #type operation

    #<var> <var_validator>: an optional validator of the input variable, using regex.

        #oci str([0-9]+-[0-9]+)
        or
        #doi str(10\\..+)
        etc.

    #preprocess <preprocess_operations>: Methods for preprocessing in the addon file

        #preprocess preprocess_oci()
        or
        #preprocess preprocess_metadata(doi)

    #postprocess <postprocess_operations>: Methods for postprocessing in the addon file

        #postprocess postprocess_oci(oci) --> another_process(oci)
        or
        #postprocess postprocess_metadata(doi)

    #method <get|post>: The method used in the API call.

        #method get

    #description <operation_description>: The description of the operation.

        #description This operation returns the metadata for the given DOI.

    #call <example_request_call>: An example of the call to the API.

        #call http://opencitations.net/index/oci/10.1038/sdata.2016.18

    #field_type <var_type_list>: The type of the variables used in the SPARQL call

        #field_type str(occ_id) str(author) datetime(year) str(title) str(source_title) str(volume) ...

    #output_json <example_json_response>: An example of the JSON response.

        #output_json [
            {
                "count": "124"
            }
        ]

    #sparql <sparql_query>: The SPARQL query to be performed on the endpoint.

        #sparql PREFIX cito: <http://purl.org/spar/cito/>
        SELECT (count(?c) as ?count)
        WHERE {
            GRAPH <https://w3id.org/oc/index/coci/> {
                BIND(<http://dx.doi.org/[[doi]]> as ?cited) .
                ?cited ^cito:hasCitedEntity ?c
            }
        }

Complete example:

.. code-block:: none

    #url /citation-count/{doi}
    #type operation
    #doi str(10\..+)
    #method get
    #description This operation retrieves the number of incoming citations to the bibliographic entity identified by the input DOI (in lowercase).

    The field returned by this operation is:

    * *count*: the number of incoming citations to the input bibliographic entity.
    #call /citation-count/10.1002/adfm.201505328
    #field_type int(count)
    #output_json [
        {
            "count": "124"
        }
    ]
    #sparql PREFIX cito: <http://purl.org/spar/cito/>
    SELECT (count(?c) as ?count)
    WHERE {
        GRAPH <https://w3id.org/oc/index/coci/> {
            BIND(<http://dx.doi.org/[[doi]]> as ?cited) .
            ?cited ^cito:hasCitedEntity ?c
        }
    }