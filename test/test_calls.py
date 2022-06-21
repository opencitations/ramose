#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2022
# Silvio Peroni <essepuntato@gmail.com>
# Marilena Daquino <marilena.daquino2@unibo.it>
# Davide Brembilla <davide.brembilla@studio.unibo.it>
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
from requests import JSONDecodeError
import ramose
import unittest
import os
import json
import csv
import time
from flask import Flask

class TestCalls(unittest.TestCase):
    '''This test looks at the calls to the API'''
    def setUp(self) -> None:
        self.maxDiff = None
        self.simple_get_test_result = ''
        with open('test%stest_data%stest_result.json' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.simple_get_test_result = json.load(f)
        self.get_params_format = []
        with open('test%stest_data%stest_csv.csv' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            reader = csv.reader(f)
            for row in reader:
                self.get_params_format.append(row)
        self.get_params_require = dict()
        with open('test%stest_data%stest_require.json' % (os.sep,os.sep), 'r', encoding='utf8')as r:
            self.get_params_require = json.load(r)
        self.get_params_filter = dict()
        with open('test%stest_data%stest_filter.json' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.get_params_filter = json.load(f)
        self.get_params_json = dict()
        with open('test%stest_data%stest_json.json' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.get_params_json = json.load(f)
        self.test_doc = ''
        with open('test%stest_data%stest_doc.html' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.test_doc = f.read()
        self.test_index = ''
        with open('test%stest_data%stest_index.html' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.test_index = f.read()
        self.test_log = ''
        with open('test%stest_data%stest_log.log' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.test_log = f.read()
            self.test_log = self.test_log.split('\n')
        with open('test%stest_data%scfr_log.txt' % (os.sep,os.sep), 'r', encoding='utf8') as f:
            self.cfr_log = f.read()
            self.cfr_log = self.cfr_log.split('\n')

        return super().setUp()
    
    def test_simple_get_call(self, test_path = 'test%stest_data%stest.hf'  % (os.sep,os.sep)):
        '''This test checks a GET call to the API'''
        api = ramose.APIManager([test_path])
        op = api.get_op('http://127.0.0.1:8080/api/v1/metadata/10.1108/jd-12-2013-0166__10.1038/nature12373')
        if type(op) is ramose.Operation:  # Operation found
            res = op.exec('GET', 'json')
            self.assertEqual(res[1], self.simple_get_test_result)
        else:  # HTTP error
            raise ConnectionError
    def test_get_params1(self, test_path = 'test%stest_data%stest_m1.hf'  % (os.sep,os.sep)): #TODO format = json
        '''This test checks a GET call to the API with parameters format and sort, as well as the conversion from and to csv'''
        api = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(api)
        res = ''
        op = api.get_op("http://localhost:8080/api/coci/references/10.1007/s11192-019-03217-6?format=csv^&sort=desc(timespan)")
        if type(op) is ramose.Operation:  # Operation found
            res = op.exec('GET', 'json')
            res = op.conv(res, 'text/csv')
            
            res = res[1].split('\r\n')[:-1]
            for i in range(len(res)): # remove newlines
                with self.subTest(i=i):
                    self.assertEqual(res[i].split(','), self.get_params_format[i]) # remove separators
        else:  # HTTP error
            raise ConnectionError

    def test_get_params2(self, test_path = 'test%stest_data%stest_m1.hf'  % (os.sep,os.sep)): # TODO: json = dict
        '''This test checks a GET call to the API with parameters filter and json'''
        api = ramose.APIManager([test_path])
        query = 'http://127.0.0.1:8080/api/coci/citations/10.1002/adfm.201505328?filter=creation:<2020&json=array("-",oci,oci1,oci2)&sort=asc(citing)'
        op = api.get_op(query)
        if type(op) is ramose.Operation:  # Operation found
            tentative = 0
            res = ''
            while tentative < 3 and type(res) is not list:
                res = op.exec('GET', 'json')
                try:
                    res = json.loads(res[1])
                except JSONDecodeError:
                    time.sleep(2)
                    tentative += 1
            for el in range(len(res)):
                with self.subTest(el=el):
                    self.assertEqual(res[el], self.get_params_filter[el])
        else:  # HTTP error
            raise ConnectionError
        


    def test_get_params3(self, test_path = 'test%stest_data%stest_m1.hf'  % (os.sep,os.sep)):
        '''This test checks a GET call to the API with parameter require'''
        api = ramose.APIManager([test_path])
        op = api.get_op('http://localhost:8080/api/coci/metadata/10.1002/adfm.201505328__10.1108/jd-12-2013-0166__10.1016/j.websem.2012.08.001?require=issue')
        if type(op) is ramose.Operation:  # Operation found
            tentative = 0
            res = ''
            while tentative < 3 and type(res) is not list:
                res = op.exec('GET','application/json')
                try:
                    res = json.loads(res[1])
                except JSONDecodeError:
                    time.sleep(2)
                    tentative +=1 
            for i in range(len(res)):
                with self.subTest(i=i):
                    for el in ['citation', 'reference', 'citation_count']:
                        res[i].pop(el)
                        self.get_params_require[i].pop(el)
                    self.assertEqual(res[i], self.get_params_require[i])
                
        else:  # HTTP error
            raise ConnectionError

    def test_get_params4(self, test_path = 'test%stest_data%stest_m1.hf'  % (os.sep,os.sep)):
        '''This test checks a GET call to the API with parameter json'''
        api = ramose.APIManager([test_path])
        tentative = 0
        query = 'http://localhost:8080/api/coci/citation/02001000007362801000805036300010863020804016335-0200100030836231029271431221029283702000106370908?json=dict("/",citing,prefix,suffix)'
        op = api.get_op(query)
        if type(op) is ramose.Operation:  # Operation found
            res = ''
            while tentative < 3 and type(res) is not list:
                res = op.exec('GET', 'json')
                try:
                    res = json.loads(res[1])
                except JSONDecodeError:
                    time.sleep(2)
                    tentative +=1 
            self.assertEqual(res, self.get_params_json)
        else:  # HTTP error
            raise ConnectionError





    def test_documentation(self, test_path = 'test%stest_data%stest.hf' % (os.sep,os.sep), css_path = 'test/style_test.css'):
        '''This test checks the creation of the documentation'''
        api = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(api)
        dh.store_documentation('documentation_cfr.html', css_path = css_path)
        with open('documentation_cfr.html', 'r', encoding='utf8') as f:
            self.assertEqual(f.read(), self.test_doc)       
        os.remove('documentation_cfr.html')
        
    def test_home(self, test_path = 'test%stest_data%stest.hf' % (os.sep,os.sep), css_path = 'test_data/style_test.css'):
        '''This test checks the creation of the index.'''
        am = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(am)
        app = Flask(__name__)
        dh.logger_ramose()
        @app.route('/')
        def home():
            index = dh.get_index(css_path)
            return index
        with open('home_cfr.html', 'w+', encoding='utf8') as f:
            f.write(home())
        with open('home_cfr.html', 'r', encoding='utf8') as f:
            self.assertEqual(self.test_index, f.read())
        os.remove('home_cfr.html')

    def test_log_creation(self, test_path = 'test%stest_data%stest.hf' % (os.sep,os.sep)):
        '''This test checks the creation of the log.'''
        api = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(api)
        dh.logger_ramose()
        self.assertTrue(os.path.isfile('ramose.log'))
        

    def test_clean_log(self, test_path = 'test%stest_data%stest.hf' % (os.sep,os.sep)):
        '''This test checks the parsing of the log.'''
        api = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(api)
        test = list()
        for el in self.test_log:
            test.append(dh.clean_log(el, 'localhost:8080'))
        for i in range(len(test)):
            with self.subTest(i=i):
                if test[i] != '':
                    self.assertIn(test[i], self.cfr_log)
            
if __name__ =='__main__':
    unittest.main()
    os.remove('ramose.log')