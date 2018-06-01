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
"""Test cases for KernelTree class."""

from __future__ import division
import unittest
import tempfile
import shutil
import os
import subprocess
import mock
from mock import Mock

from skt.kerneltree import KernelTree


def make_process_exception(*args, **kwargs):
    # pylint: disable=W0613
    """Throw a CalledProcessError exception."""
    raise subprocess.CalledProcessError(1, 'That failed', "output")


class KernelTreeTest(unittest.TestCase):
    # (Too many public methods) pylint: disable=too-many-public-methods
    """Test cases for KernelBuilder class."""

    def setUp(self):
        """Fixtures for testing KernelTree."""
        self.tmpdir = tempfile.mkdtemp()

        # Mock a successful subprocess.Popen
        self.m_popen_good = Mock()
        self.m_popen_good.returncode = 0
        self.m_popen_good.communicate = Mock(
            return_value=('stdout', 'stderr')
        )
        self.popen_good = mock.patch(
            'subprocess.Popen',
            Mock(return_value=self.m_popen_good)
        )

        # Mock an unsuccessful subprocess.Popen
        self.m_popen_bad = Mock()
        self.m_popen_bad.returncode = 1
        self.m_popen_bad.communicate = Mock(return_value=('stdout', 'stderr'))
        self.popen_bad = mock.patch(
            'subprocess.Popen',
            Mock(return_value=self.m_popen_bad)
        )

        self.kerneltree = KernelTree(
            uri=(
                'git://git.kernel.org/pub/scm/linux/kernel/git/'
                'stable/linux-stable.git'
            ),
            ref='master',
            wdir=self.tmpdir,
            fetch_depth='1'
        )

    def tearDown(self):
        """Teardown steps when testing is complete."""
        # Some tests remove the work directory, so we should check for it
        # before deleting it.
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_bisect_start(self):
        """Ensure bisect_start() starts a git bisect."""
        self.m_popen_good.communicate = Mock(
            return_value=('Bisecting: foo', None)
        )
        mock_chdir = mock.patch('os.chdir')

        with self.popen_good, mock_chdir:
            result = self.kerneltree.bisect_start('abcdef')

        self.assertEqual('foo', result)

    def test_bisect_start_failure(self):
        """Ensure bisect_start() handles a failure properly."""
        self.m_popen_good.communicate = Mock(return_value=('error', None))
        mock_chdir = mock.patch('os.chdir')

        with self.popen_good, mock_chdir:
            result = self.kerneltree.bisect_start('abcdef')

        self.assertIsNone(result)

    def test_bisect_iter(self):
        """Ensure bisect_iter() continues the bisect."""
        self.m_popen_good.communicate = Mock(
            return_value=('Bisecting: foo', None)
        )
        mock_chdir = mock.patch('os.chdir')

        with self.popen_good, mock_chdir:
            result = self.kerneltree.bisect_iter(1)

        self.assertTupleEqual((0, 'foo'), result)

    def test_bisect_iter_completed(self):
        """Ensure bisect_iter() handles the completion of the bisection."""
        stdout = 'abcdef is the first bad commit'
        self.m_popen_good.communicate = Mock(return_value=(stdout, None))
        mock_chdir = mock.patch('os.chdir')

        with self.popen_good, mock_chdir:
            result = self.kerneltree.bisect_iter(1)

        self.assertTupleEqual((1, 'abcdef'), result)

    def test_bisect_iter_error(self):
        """Ensure bisect_iter() handles an error message."""
        self.m_popen_good.communicate = Mock(return_value=('error', None))
        mock_chdir = mock.patch('os.chdir')

        with self.popen_good, mock_chdir:
            result = self.kerneltree.bisect_iter(1)

        self.assertTupleEqual((0, None), result)

    def test_cleanup(self):
        """Ensure cleanup() removes the workdir."""
        ktree = self.kerneltree
        ktree.cleanup()

    def test_checkout(self):
        """Ensure checkout() runs git commands to check out a ref."""
        self.m_popen_good.communicate = Mock(return_value=('stdout', None))

        mock_git_cmd = mock.patch('skt.kerneltree.KernelTree.git_cmd')

        with self.popen_good, mock_git_cmd:
            result = self.kerneltree.checkout()

        self.assertEqual("stdout", result)

    def test_dumpinfo(self):
        """Ensure dumpinfo() can dump data in a CSV format."""
        self.kerneltree.info = [('test1', 'test2', 'test3')]
        result = self.kerneltree.dumpinfo()
        expected_filename = "{}/buildinfo.csv".format(self.tmpdir)

        # Ensure a file was made and its path was returned
        self.assertTrue(os.path.isfile(expected_filename))
        self.assertEqual(result, expected_filename)

        with open(expected_filename, 'r') as fileh:
            file_contents = fileh.read()

        # Ensure the csv file has the correct data.
        self.assertEqual("test1,test2,test3\n", file_contents)

    def test_getpath(self):
        """Ensure that getpath() returns the workdir path."""
        result = self.kerneltree.getpath()
        self.assertEqual(result, self.tmpdir)

    def test_get_commit_date(self):
        """Ensure that get_commit_date() returns an integer date."""
        # Mock up an integer response that would normally come from the
        # 'git show' command
        self.m_popen_good.communicate = Mock(return_value=('100', None))

        with self.popen_good:
            result = self.kerneltree.get_commit_date(ref='master')

        self.assertEqual(result, 100)

    def test_get_commit_hash(self):
        """Ensure get_commit_hash() returns a git commit hash."""
        self.m_popen_good.communicate = Mock(return_value=('abcdef', None))

        with self.popen_good:
            result = self.kerneltree.get_commit_hash(ref='master')

        self.assertEqual(result, 'abcdef')

    def test_get_remote_url(self):
        """Ensure get_remote_url() returns a fetch url."""
        expected_stdout = "Fetch URL: http://example.com/"
        self.m_popen_good.communicate = Mock(
            return_value=(expected_stdout, None)
        )

        with self.popen_good:
            result = self.kerneltree.get_remote_url('origin')

        self.assertEqual(result, 'http://example.com/')

    def test_getrname(self):
        """Ensure getrname() handles remote names from get_remote_url()."""
        # If get_remote_url keeps returning the same value, then getrname()
        # will keep adding underscores forever and this test would never pass.
        mocked_get_remote_url = mock.patch(
            'skt.kerneltree.KernelTree.get_remote_url',
            side_effect=['http://example.com/', "http://example2.com"]
        )

        with mocked_get_remote_url:
            result = self.kerneltree.getrname("http://example.com/")

        self.assertEqual('example.com_', result)

    def test_merge_git_ref(self):
        """Ensure merge_git_ref() returns a proper tuple."""
        mock_git_cmd = mock.patch('skt.kerneltree.KernelTree.git_cmd')
        mock_get_commit_hash = mock.patch(
            'skt.kerneltree.KernelTree.get_commit_hash',
            return_value="abcdef"
        )

        with mock_git_cmd, mock_get_commit_hash:
            result = self.kerneltree.merge_git_ref('http://example.com')

        self.assertTupleEqual((0, 'abcdef'), result)

    def test_merge_git_ref_failure(self):
        """Ensure merge_git_ref() fails properly when remote add fails."""
        mock_git_cmd = mock.patch(
            'skt.kerneltree.KernelTree.git_cmd',
            side_effect=make_process_exception
        )
        mock_get_commit_hash = mock.patch(
            'skt.kerneltree.KernelTree.get_commit_hash',
            return_value="abcdef"
        )

        with mock_git_cmd, mock_get_commit_hash:
            with self.assertRaises(subprocess.CalledProcessError):
                self.kerneltree.merge_git_ref('http://example.com')

    def test_merge_pw_patch(self):
        """Ensure merge_patchwork_patch() handles patches properly."""
        mock_gpm = mock.patch('skt.get_patch_mbox')
        mock_git_cmd = mock.patch('skt.kerneltree.KernelTree.git_cmd')
        mock_gpn = mock.patch(
            'skt.get_patch_name',
            return_value="patch_name"
        )

        self.m_popen_good.communicate = Mock(return_value=('stdout', None))
        self.m_popen_good.wait = Mock(return_value=0)

        with mock_gpm, mock_git_cmd, mock_gpn, self.popen_good:
            result = self.kerneltree.merge_patchwork_patch('uri')

        self.assertIsNone(result)
        self.assertTupleEqual(
            ('patchwork', 'uri', 'patch_name'),
            self.kerneltree.info[0]
        )

    def test_merge_pw_patch_failure(self):
        """Ensure merge_patchwork_patch() handles patch failures properly."""
        mock_get_patch_mbox = mock.patch('skt.get_patch_mbox')
        mock_git_cmd = mock.patch('skt.kerneltree.KernelTree.git_cmd')

        self.m_popen_bad.communicate = Mock(return_value=('stdout', None))

        with mock_get_patch_mbox, mock_git_cmd, self.popen_bad:
            with self.assertRaises(Exception):
                self.kerneltree.merge_patchwork_patch('uri')

    def test_merge_patch_file(self):
        """Ensure merge_patch_file() tries to merge a patch."""
        mock_check_output = mock.patch(
            'subprocess.check_output',
            Mock(return_value='toot')
        )
        patch_file = "{}/test_patch.patch".format(self.tmpdir)
        with open(patch_file, 'w') as fileh:
            fileh.write('dummy patch data')

        with mock_check_output:
            self.kerneltree.merge_patch_file(patch_file)

        self.assertTupleEqual(
            ('patch', patch_file),
            self.kerneltree.info[0]
        )

    def test_merge_patch_file_failure(self):
        """Ensure merge_patch_file() handles a patch apply failure."""
        mock_check_output = mock.patch(
            'subprocess.check_output',
            side_effect=make_process_exception
        )
        mock_git_cmd = mock.patch('skt.kerneltree.KernelTree.git_cmd')

        patch_file = "{}/test_patch.patch".format(self.tmpdir)
        with open(patch_file, 'w') as fileh:
            fileh.write('dummy patch data')

        with mock_check_output, mock_git_cmd:
            with self.assertRaises(Exception):
                self.kerneltree.merge_patch_file(patch_file)

    def test_merge_patch_file_missing(self):
        """Ensure merge_patch_file() fails when a patch is missing."""
        with self.assertRaises(Exception):
            self.kerneltree.merge_patch_file('patch_does_not_exist')
