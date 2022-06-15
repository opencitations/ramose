Launching RAMOSE
================
.. note:: 

    In order to launch ramose, remember to install it via pip and create a .hf configuration file as in :ref:`config`. We also suggest you to use a virtual environment to do so. See `venv <https://docs.python.org/3/library/venv.html>`_

You can launch ramose from the command line simply by using:

.. code-block:: bash

    py -m ramose [arguments]

or

.. code-block:: bash

    python3 -m ramose [arguments]

Arguments 
---------

Here is the list of possible arguments:

- **-h, --help**: shows the help message
- **-s SPEC, --spec SPEC**:  The file in hashformat containing the specification of the API. Include the path to the file and the file format e.g. **config.hf**. This argument is required for any operation.
- **-m METHOD, --method METHOD**: The method to use to make a request to the API. To be used in combination with **'-c'**
- **-c CALL, --call CALL**:  The URL to call for querying the API. To be used in the format `/api/**`. To be used in combination with **'-m'**. 
- **-f FORMAT, --format FORMAT**: The format in which to get the response. Default is **application/json**
- **-d, --doc**: Specify this argument to generate the HTML documentation of the API (if it is specified, all the arguments **'-m'**, **'-c'**, and **'-f'** won't be considered).
- **-o OUTPUT, --output OUTPUT**: A file where to store the response or the documentation. If not specified, the output will be printed in the terminal.
- **-w WEBSERVER, --webserver WEBSERVER** The host:port where to deploy a Flask webserver for testing the API (if this argument is used, **-d** won't be considered).
- **-css CSS, --css CSS**   The path of a .css file for styling the API documentation (to be specified either with **'-w'** or with **'-d'** and **'-o'**  arguments). The css will be inserted as a `<link rel="stylesheet" type="text/css" href='your_css'>` element in the `<head>` of the HTML file, after the base css styling, so remember to use the relative path to the css file from where the app is stored.

Command examples
----------------

Here are some examples for launching RAMOSE:

.. code-block:: bash

    py -m ramose --help


This command displays the help message.

.. code-block:: bash

    py -m ramose -s test.hf -w 127.0.0.1:8090

This command launches RAMOSE with the specifications in test.hf and on a local server. You can access said api from the browser or by using the `curl` command from the terminal. Use `Ctrl+C` to stop the server.

.. code-block:: bash

    py -m ramose -s test.hf -d -css style.css -o test_ramose.html

This command creates and stores the documentation html file of a RAMOSE app in the `test_ramose.html` file. The documentation will have a link to the `style.css` file.


.. code-block:: bash

    py -m ramose -s test_data/test.hf -m get -c /api/v1/metadata/10.1108/JD-12-2013-0166 -f csv
    
    Output: 
    author,year,title,source_title,volume,issue,page,doi,reference,citation_count,qid
    "Dutton, Alexander; Peroni, Silvio; Shotton, David",2015,Setting our bibliographic references free: towards open citation data,Journal of Documentation,71,2,253-277,10.1108/JD-12-2013-0166,10.1108/EUM0000000007123;[...],10,Q24260641

This command calls the API with the method `get` and the URL `/api/v1/metadata/10.1136/BMJ.B2680` and returns the response in a `csv` format.
