#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2020
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
import ramose
import unittest
import os
import json

class TestCalls(unittest.TestCase):
    '''This test looks at the calls to the API'''
    def setUp(self) -> None:
        return super().setUp()
    
    def test_get_calls(self, test_path:str = 'test.hf'):
        '''This test checks the calls to the API'''
        api = ramose.APIManager([test_path])
        dh = ramose.HTMLDocumentationHandler(api)
        op = api.get_op('http://127.0.0.1:8080/api/v1/metadata/10.1108/jd-12-2013-0166__10.1038/nature12373')
        print(op)

if __name__ =='__main__':
    unittest.main()