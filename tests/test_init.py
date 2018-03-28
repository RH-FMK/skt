"""
Test cases for __init__.py.
"""
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
from xmlrpclib import ServerProxy
import unittest

import skt


class TestInit(unittest.TestCase):
    """Test cases for skt's __init__.py"""

    def test_stringify_with_integer(self):
        """Ensure stringify() can handle an integer"""
        myinteger = int(42)
        result = skt.stringify(myinteger)
        self.assertIsInstance(result, str)
        self.assertEqual(result, str(myinteger))

    def test_stringify_with_string(self):
        """Ensure stringify() can handle a plain string"""
        mystring = "Test text"
        result = skt.stringify(mystring)
        self.assertIsInstance(result, str)
        self.assertEqual(result, mystring)

    def test_stringify_with_unicode(self):
        """Ensure stringify() can handle a unicode byte string"""
        myunicode = unicode("Test text")
        result = skt.stringify(myunicode)
        self.assertIsInstance(result, str)
        self.assertEqual(result, myunicode.encode('utf-8'))

    def test_parse_bad_patchwork_url(self):
        """Ensure parse_patchwork_url() handles a parsing exception"""
        patchwork_url = "garbage"
        with self.assertRaises(Exception) as context:
            skt.parse_patchwork_url(patchwork_url)

        self.assertTrue(
            "Can't parse patchwork url: '{}'".format(patchwork_url)
            in context.exception
        )

    def test_parse_valid_patchwork_url(self):
        """Ensure parse_patchwork_url() can parse a valid patchwork url"""
        patch_number = "890993"
        patchwork_url = (
            "https://patchwork.ozlabs.org/patch/{}/".format(patch_number)
        )
        result = skt.parse_patchwork_url(patchwork_url)
        self.assertIsInstance(result, tuple)

        (serverobj, patch_id) = result
        self.assertIsInstance(serverobj, ServerProxy)
        self.assertEqual(patch_id, patch_number)
