# Copyright (c) 2018 Red Hat, Inc. All rights reserved. This copyrighted
# material is made available to anyone wishing to use, modify, copy, or
# redistribute it subject to the terms and conditions of the GNU General Public
# License v.2 or later.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""Test cases for __init__.py."""
from __future__ import division
from email.errors import HeaderParseError
import unittest

import mock
import requests
import responses

import skt


class TestIndependent(unittest.TestCase):
    """Test cases for independent functions in __init__.py."""

    @responses.activate
    def test_get_patch_mbox(self):
        """Ensure get_patch_mbox() succeeds with a good request."""
        responses.add(
            responses.GET,
            'http://patchwork.example.com/patch/1/mbox',
            json={'result': 'good'},
            status=200
        )

        resp = skt.get_patch_mbox('http://patchwork.example.com/patch/1')
        self.assertEqual('{"result": "good"}', resp)

    @responses.activate
    def test_get_patch_mbox_fail(self):
        """Ensure get_patch_mbox() handles an exception from requests."""
        responses.add(
            responses.GET,
            'http://patchwork.example.com/patch/1/mbox',
            body=requests.exceptions.RequestException('Fail'),
        )

        with self.assertRaises(requests.exceptions.RequestException):
            skt.get_patch_mbox('http://patchwork.example.com/patch/1')

    @responses.activate
    def test_get_patch_mbox_bad_status(self):
        """Ensure get_patch_mbox() handles a bad status code."""
        responses.add(
            responses.GET,
            'http://patchwork.example.com/patch/1/mbox',
            json={'error': 'failure'},
            status=500
        )

        with self.assertRaises(Exception):
            skt.get_patch_mbox('http://patchwork.example.com/patch/1')

    def test_nonexistent_patch_subject(self):
        """Ensure get_patch_name() handles nonexistent 'Subject' in mbox."""
        mbox_body = 'nothing useful here'
        self.assertEqual('<SUBJECT MISSING>', skt.get_patch_name(mbox_body))

    def test_ok_patch_subject(self):
        """Ensure get_patch_name() returns correct 'Subject' if present."""
        mbox_body = 'From Test Thu May 2 17:49:51 2018\nSubject: GOOD SUBJECT'
        self.assertEqual('GOOD SUBJECT', skt.get_patch_name(mbox_body))

    def test_encoded_patch_subject(self):
        """Ensure get_patch_name() correctly decodes UTF-8 'Subject'."""
        mbox_body = ('From Test Thu May 2 17:49:51 2018\n'
                     'Subject: =?utf-8?q?=5BTEST=5D?=')
        self.assertEqual('[TEST]', skt.get_patch_name(mbox_body))

    @mock.patch('email.header.decode_header')
    @mock.patch('email.parser.Parser.parsestr')
    def test_header_parse_failure(self, mock_parsestr, mock_decode_header):
        """Ensure get_patch_name() handles a parsing failure."""
        mock_parsestr.return_value = {'Subject': "Testing"}
        mock_decode_header.side_effect = HeaderParseError('Fail')
        result = skt.get_patch_name('')

        self.assertEqual('<SUBJECT ENCODING INVALID>', result)

    def test_multipart_encoded_subject(self):
        """
        Ensure get_patch_name() correctly decodes multipart encoding
        of 'Subject'.
        """
        mbox_body = ('From Test Thu May 2 17:49:51 2018\nSubject: '
                     '=?ISO-8859-1?B?SWYgeW91IGNhbiByZWFkIHRoaXMgeW8=?=\n'
                     '    =?ISO-8859-2?B?dSB1bmRlcnN0YW5kIHRoZSBleGFtcGxlLg'
                     '==?=')
        self.assertEqual('If you can read this you understand the example.',
                         skt.get_patch_name(mbox_body))
