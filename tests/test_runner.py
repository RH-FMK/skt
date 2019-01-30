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
"""Test cases for runner module."""
import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import unittest

from defusedxml.ElementTree import fromstring
from defusedxml.ElementTree import tostring
import mock

from skt import runner
from skt.misc import SKT_FAIL, SKT_SUCCESS, SKT_ERROR

from tests import misc

SCRIPT_PATH = os.path.dirname(__file__)

DEFAULT_ARGS = {
    'jobtemplate': '{}/assets/test.xml'.format(SCRIPT_PATH)
}


def trigger_signal():
    """ Send SIGTERM to self after 2 seconds."""
    time.sleep(2)
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM)


class TestRunner(unittest.TestCase):
    """Test cases for runner module."""
    # (Too many public methods) pylint: disable=too-many-public-methods

    def setUp(self):
        """Set up test fixtures"""
        self.myrunner = runner.BeakerRunner(**DEFAULT_ARGS)

        with open('{}/assets/test.xml'.format(SCRIPT_PATH), 'r') as fileh:
            self.test_xml = fileh.read()

        self.max_aborted = 3

    def test_get_kpkginstall_task(self):
        """ Ensure get_kpkginstall_task works."""
        recipe_xml = """<recipe><task name="Boot test">
        <fetch url="kpkginstall"/></task>
        <task><fetch url="kpkginstall"/></task></recipe>"""
        recipe_node = fromstring(recipe_xml)

        ret_node = self.myrunner.get_kpkginstall_task(recipe_node)
        self.assertEqual(ret_node.attrib['name'], 'Boot test')
        self.assertEqual(ret_node.find('fetch').attrib['url'], 'kpkginstall')

    def test_get_recipe_test_list_1st(self):
        """ Ensure get_recipe_test_list works. First task is skipped."""
        recipe_xml = """<recipe><task result="Skip" /><task name="good2" />
        </recipe>"""

        recipe_node = fromstring(recipe_xml)

        ret_list = self.myrunner.get_recipe_test_list(recipe_node)
        self.assertEqual(ret_list, ['good2'])

    def test_get_recipe_test_list_2nd(self):
        """ Ensure get_recipe_test_list works. Second task is skipped."""
        recipe_xml = """<recipe><task name="good1" /><task result="Skip" />
        </recipe>"""

        recipe_node = fromstring(recipe_xml)

        ret_list = self.myrunner.get_recipe_test_list(recipe_node)
        self.assertEqual(ret_list, ['good1'])

    def test_get_recipe_test_list(self):
        """ Ensure get_recipe_test_list works. No task skipped."""
        recipe_xml = """<recipe><task name="good1" /><task name="good2" />
           </recipe>"""

        recipe_node = fromstring(recipe_xml)

        ret_list = self.myrunner.get_recipe_test_list(recipe_node)
        self.assertEqual(ret_list, ['good1', 'good2'])

    @mock.patch('subprocess.Popen')
    def test_jobsubmit(self, mock_popen):
        """ Ensure __jobsubmit works."""
        self.myrunner.jobowner = 'beaker-gods'

        args = ["bkr", "job-submit", "--job-owner=beaker-gods", "-"]

        mock_popen.return_value.returncode = 0
        mock_popen.return_value.communicate.return_value = \
            ("Submitted: ['123']", '')

        # pylint: disable=W0212,E1101
        self.myrunner._BeakerRunner__jobsubmit('<xml />')

        mock_popen.assert_called_once_with(args, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_jobsubmit_exc(self, mock_popen):
        """ Ensure __jobsubmit doesn't parse invalid bkr output."""
        # pylint: disable=W0212,E1101
        self.myrunner.jobowner = 'beaker-gods'

        args = ["bkr", "job-submit", "--job-owner=beaker-gods", "-"]

        mock_popen.return_value.returncode = 0
        mock_popen.return_value.communicate.return_value = \
            ("Submitted: a horse", '')

        with self.assertRaises(Exception) as exc:
            self.myrunner._BeakerRunner__jobsubmit('<xml />')
            self.assertEqual(exc.message, 'Unable to submit the job!')
            mock_popen.assert_called_once_with(args, stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE)

    @mock.patch('subprocess.Popen')
    def test_cancel_pending_jobs(self, mock_popen):
        """ Ensure cancel_pending_jobs works."""
        # pylint: disable=W0212,E1101
        j_jobid = 'J:123'
        setid = '456'
        test_xml = """<xml><whiteboard>yeah-that-whiteboard</whiteboard>
        <recipeSet id="{}" /></xml>""".format(setid)

        mock_popen.return_value.returncode = 0
        mock_popen.return_value.communicate.return_value = (test_xml, '')

        self.myrunner._BeakerRunner__add_to_watchlist(j_jobid)

        mock_popen.assert_called()

        binary = 'bkr'
        args = ['job-cancel', j_jobid]

        attrs = {'communicate.return_value': ('output', 'error'),
                 'returncode': 0}
        mock_popen.configure_mock(**attrs)

        self.myrunner.cancel_pending_jobs()

        mock_popen.assert_called_with([binary] + args)

    def test_getrunner(self):
        """Ensure getrunner() can create a runner subclass."""
        result = runner.getrunner('beaker', {'jobtemplate': 'test'})
        self.assertIsInstance(result, runner.BeakerRunner)

    @mock.patch('logging.error')
    def test_load_blacklist_fail(self, mock_logging_err):
        """Ensure BeakerRunner.__load_blacklist() works"""
        # pylint: disable=W0212,E1101,W0613
        r_nr = self.myrunner
        inv = 'blah-such-files-dont-usually-exist'
        with self.assertRaises(Exception) as exc:
            r_nr.blacklisted = self.myrunner._BeakerRunner__load_blacklist(inv)

            self.assertEqual(exc.message, ('Can\'t access %s!', inv))

    def test_load_blacklist(self):
        """Ensure BeakerRunner.__load_blacklist() works"""
        # pylint: disable=W0212,E1101
        hostnames = ['host1', 'host2']
        with tempfile.NamedTemporaryFile() as temp:
            temp.write('\n'.join(hostnames) + '\n')
            temp.seek(0)

            myrunner = self.myrunner

            myrunner.blacklisted = self.myrunner._BeakerRunner__load_blacklist(
                temp.name)

        self.assertEqual(hostnames, self.myrunner.blacklisted)

    def test_blacklist_hreq_noand(self):
        """ Ensure blacklist_hreq works without <and> element."""
        # pylint: disable=W0212,E1101
        initial = """<hostRequires></hostRequires>"""

        exp_result = """<hostRequires><and>
        <hostname op="!=" value="host1"/>
        <hostname op="!=" value="host2"/></and></hostRequires>"""

        hreq_node = fromstring(initial)

        # load blacklist ['host1', 'host2']
        self.test_load_blacklist()

        etree_result = self.myrunner._BeakerRunner__blacklist_hreq(hreq_node)
        result = tostring(etree_result)
        self.assertEqual(re.sub(r'[\s]+', '', exp_result),
                         re.sub(r'[\s]+', '', result))

    def test_blacklist_hreq_nohostnames(self):
        """ Ensure blacklist_hreq works without hostnames."""
        # pylint: disable=W0212,E1101
        initial = """<hostRequires><system_type value="Machine"/><and>
        <hypervisor op="=" value=""/></and></hostRequires>"""

        exp_result = """<hostRequires><system_type value="Machine"/><and>
        <hypervisor op="=" value=""/></and></hostRequires>"""

        hreq_node = fromstring(initial)

        self.myrunner.blacklisted = []
        etree_result = self.myrunner._BeakerRunner__blacklist_hreq(hreq_node)
        result = tostring(etree_result)
        self.assertEqual(re.sub(r'[\s]+', '', exp_result),
                         re.sub(r'[\s]+', '', result))

    def test_blacklist_hreq_whnames(self):
        """ Ensure blacklist_hreq works with hostnames."""
        # pylint: disable=W0212,E1101
        initial = """<hostRequires><system_type value="Machine"/><and>
        <hypervisor op="=" value=""/></and></hostRequires>"""

        exp_result = """<hostRequires><system_type value="Machine"/><and>
        <hypervisor op="=" value=""/><hostname op="!=" value="host1"/>
        <hostname op="!=" value="host2"/></and></hostRequires>"""

        hreq_node = fromstring(initial)

        # load blacklist ['host1', 'host2']
        self.test_load_blacklist()

        etree_result = self.myrunner._BeakerRunner__blacklist_hreq(hreq_node)
        result = tostring(etree_result)
        self.assertEqual(re.sub(r'[\s]+', '', exp_result),
                         re.sub(r'[\s]+', '', result))

    def test_invalid_getrunner(self):
        """Ensure getrunner() throws an exception for an invalid runner."""
        bad_runner = 'pizza'
        with self.assertRaises(Exception) as context:
            runner.getrunner(bad_runner, {'jobtemplate': 'test'})

        self.assertIn(
            "Unknown runner type: {}".format(bad_runner),
            context.exception
        )

    def test_getxml(self):
        """Ensure BeakerRunner.__getxml() returns xml."""
        # pylint: disable=W0212,E1101
        result = self.myrunner._BeakerRunner__getxml({})
        self.assertEqual(result, self.test_xml)

    def test_getxml_invalid_replace(self):
        """
        Ensure BeakerRunner.__getxml() raises ValueError if the replacement is
        not a string.
        """
        # pylint: disable=W0212,E1101
        with self.assertRaises(ValueError):
            self.myrunner._BeakerRunner__getxml({"KVER": None})

    def test_getxml_replace(self):
        """Ensure BeakerRunner.__getxml() returns xml with replacements."""
        # pylint: disable=W0212,E1101
        result = self.myrunner._BeakerRunner__getxml({'KVER': 'kernel-4.16'})
        expected_xml = self.test_xml.replace("##KVER##", "kernel-4.16")
        self.assertEqual(result, expected_xml)

    def test_getxml_multi_replace(self):
        """
        Ensure BeakerRunner.__getxml() returns xml with multi-instance
        replacements.
        """
        # pylint: disable=W0212,E1101
        result = self.myrunner._BeakerRunner__getxml({'ARCH': 's390x'})
        expected_xml = self.test_xml.replace("##ARCH##", "s390x")
        self.assertEqual(result, expected_xml)

    @mock.patch('logging.error')
    @mock.patch('subprocess.call')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_cleanup_called(self, mock_jobsubmit, mock_call, mock_log_err):
        """Ensure BeakerRunner.signal_handler works."""
        # pylint: disable=W0613
        url = "http://machine1.example.com/builds/1234567890.tar.gz"
        release = "4.17.0-rc1"
        wait = True
        mock_jobsubmit.return_value = "J:0001"

        mock_call.return_value = 0

        signal.signal(signal.SIGINT, self.myrunner.signal_handler)
        signal.signal(signal.SIGTERM, self.myrunner.signal_handler)

        thread = threading.Thread(target=trigger_signal)

        try:
            thread.start()

            self.myrunner.run(url, self.max_aborted, release, wait)
            thread.join()
        except (KeyboardInterrupt, SystemExit):
            logging.info('Thread cancelling...')

        self.assertTrue(self.myrunner.cleanup_done)

    @mock.patch('logging.error')
    @mock.patch('subprocess.call')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_cleanup_called2(self, mock_jobsubmit, mock_call, mock_log_err):
        """Ensure BeakerRunner cleanup isn't called twice."""
        # pylint: disable=W0613

        url = "http://machine1.example.com/builds/1234567890.tar.gz"
        release = "4.17.0-rc1"
        wait = True
        mock_jobsubmit.return_value = "J:0001"

        mock_call.return_value = 0

        signal.signal(signal.SIGINT, self.myrunner.signal_handler)
        signal.signal(signal.SIGTERM, self.myrunner.signal_handler)

        thread = threading.Thread(target=trigger_signal)

        self.myrunner.cleanup_done = True

        try:
            thread.start()

            self.myrunner.run(url, self.max_aborted, release, wait)
            thread.join()
        except (KeyboardInterrupt, SystemExit):
            logging.info('Thread cancelling...')

        self.assertFalse(mock_call.called)

    @mock.patch('subprocess.Popen')
    def test_add_to_watchlist(self, mock_popen):
        """Ensure __add_to_watchlist() works."""
        # pylint: disable=W0212,E1101
        j_jobid = 'J:123'
        setid = '456'
        s_setid = 'RS:{}'.format(setid)
        test_xml = """<xml><whiteboard>yeah-that-whiteboard</whiteboard>
        <recipeSet id="{}" /></xml>""".format(setid)

        mock_popen.return_value.returncode = 0
        mock_popen.return_value.communicate.return_value = (test_xml, '')

        self.myrunner._BeakerRunner__add_to_watchlist(j_jobid)
        mock_popen.assert_called_once_with(["bkr", "job-results", j_jobid],
                                           stdout=subprocess.PIPE)

        # test that whiteboard was parsed OK
        self.assertEqual(self.myrunner.whiteboard, 'yeah-that-whiteboard')

        # test that job_to_recipe mapping was updated
        self.assertEqual(self.myrunner.job_to_recipe_set_map[j_jobid],
                         {s_setid})

        # test that watchlist contains RS
        self.assertIn(s_setid, self.myrunner.watchlist)

        # test that no recipes completed
        self.assertEqual(self.myrunner.completed_recipes[s_setid], set())

    @mock.patch('subprocess.Popen')
    def test_getresultstree(self, mock_popen):
        """Ensure getresultstree() works."""
        test_xml = "<xml><test>TEST</test></xml>"
        mock_popen.return_value.returncode = 0
        mock_popen.return_value.communicate.return_value = (test_xml, '')
        result = self.myrunner.getresultstree('RS:123')
        self.assertEqual(next(x.text for x in result.iter('test')), 'TEST')

    def test_forget_taskspec_withj(self):
        """Ensure __forget_taskspec() works with jobs."""
        # pylint: disable=protected-access,E1101
        self.myrunner.job_to_recipe_set_map = {"J:00001": ["RS:00001"]}
        result = self.myrunner._BeakerRunner__forget_taskspec("J:00001")
        self.assertIsNone(result)
        self.assertEqual(self.myrunner.job_to_recipe_set_map, {})

    def test_forget_taskspec_withr(self):
        """Ensure __forget_taskspec() works with recipe sets."""
        # pylint: disable=protected-access,E1101
        self.myrunner.job_to_recipe_set_map = {"J:00001": ["RS:00001"]}
        result = self.myrunner._BeakerRunner__forget_taskspec("RS:00001")
        self.assertIsNone(result)
        self.assertEqual(self.myrunner.job_to_recipe_set_map, {})

    def test_forget_taskspec_bad_job(self):
        """Ensure __forget_taskspec() fails with an invalid taskspec."""
        # pylint: disable=protected-access,E1101
        with self.assertRaises(Exception) as context:
            self.myrunner._BeakerRunner__forget_taskspec("OHCOMEON:00001")

        self.assertIn(
            "Unknown taskspec type: OHCOMEON:00001",
            context.exception
        )

    @mock.patch('logging.info')
    def test_getresults_pass(self, mock_logging):
        """Ensure __getresults() works."""
        # pylint: disable=W0212,E1101
        self.myrunner.job_to_recipe_set_map = {'jobid': set(['recipeset'])}
        self.myrunner.recipe_set_results['recipeset'] = fromstring(
            misc.get_asset_content('beaker_recipe_set_results.xml')
        )

        result = self.myrunner._BeakerRunner__getresults(False)
        self.assertEqual(result, 0)
        mock_logging.assert_called()

    @mock.patch('logging.error')
    def test_getresults_aborted(self, mock_logging):
        """Ensure __getresults() handles all aborted / cancelled jobs."""
        # pylint: disable=W0212,E1101
        result = self.myrunner._BeakerRunner__getresults(False)
        self.assertEqual(result, 2)
        mock_logging.assert_called()

    @mock.patch('logging.info')
    def test_getresults_failure(self, mock_logging):
        """Ensure __getresults() handles a job failure."""
        # pylint: disable=W0212,E1101
        self.myrunner.job_to_recipe_set_map = {'jobid': set(['recipeset'])}
        self.myrunner.recipe_set_results['recipeset'] = fromstring(
            misc.get_asset_content('beaker_fail_results.xml')
        )

        result = self.myrunner._BeakerRunner__getresults(False)
        self.assertEqual(result, 1)
        mock_logging.assert_called()

    def test_recipe_set_to_job(self):
        """Ensure __recipe_set_to_job() works."""
        # pylint: disable=W0212,E1101
        beaker_xml = misc.get_asset_content('beaker_recipe_set_results.xml')
        xml_parsed = fromstring(beaker_xml)

        result = self.myrunner._BeakerRunner__recipe_set_to_job(xml_parsed)
        self.assertEqual(result.tag, 'job')

        result = self.myrunner._BeakerRunner__recipe_set_to_job(xml_parsed,
                                                                samehost=True)
        self.assertEqual(result.tag, 'job')

    def test_recipe_set_to_job_whst(self):
        """Ensure __recipe_set_to_job() works with hostname."""
        # pylint: disable=W0212,E1101
        beaker_xml = """<recipeSet><recipe><hostRequires>
        <hostname op="!=" value="hst1"/></hostRequires></recipe></recipeSet>"""
        xml_parsed = fromstring(beaker_xml)

        result = self.myrunner._BeakerRunner__recipe_set_to_job(xml_parsed)

        # check that <hostname op="!=" value="hst1"/> was removed
        self.assertEqual(result.findall('.//hostname'), [])

    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run(self, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        url = "http://machine1.example.com/builds/1234567890.tar.gz"
        release = "4.17.0-rc1"
        wait = False

        mock_jobsubmit.return_value = "J:0001"

        result = self.myrunner.run(url, self.max_aborted, release, wait)
        self.assertEqual(result, 0)

    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__getxml')
    def test_run_fail(self, mock_logging_err, mock_getxml):
        """Ensure BeakerRunner.run errors on invalid xml."""
        # pylint: disable=W0613
        url = "http://machine1.example.com/builds/1234567890.tar.gz"
        release = "4.17.0-rc1"
        wait = True

        mock_getxml.return_value = '<xml >'

        result = self.myrunner.run(url, self.max_aborted, release, wait)
        self.assertEqual(result, 2)

    @mock.patch('skt.runner.BeakerRunner.getresultstree')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait(self, mock_jobsubmit, mock_getresultstree):
        """Ensure BeakerRunner.run works."""
        url = "http://machine1.example.com/builds/1234567890.tar.gz"
        release = "4.17.0-rc1"
        wait = True
        self.myrunner.whiteboard = 'test'

        beaker_xml = misc.get_asset_content('beaker_pass_results.xml')
        mock_getresultstree.return_value = fromstring(beaker_xml)
        mock_jobsubmit.return_value = "J:0001"

        # no need to wait 60 seconds
        # though beaker_pass_results.xml only needs one iteration
        self.myrunner.watchdelay = 0.1
        result = self.myrunner.run(url, self.max_aborted, release, wait)

        self.assertEqual(result, 0)

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait2(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_results.xml', 1,
                     'Completed')

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait3(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_results2.xml', 1,
                     'Completed')

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait4(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_results3.xml', 1,
                     'Completed')

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait5(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_results3.xml', 2,
                     'Completed')

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait6(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613
        # disable soak for this test!
        self.myrunner.soak = False
        # abort right-away ( 0 allowed)
        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_aborted_some.xml',
                     0)

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait7(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        # abort later on, change last recipe to Aborted
        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_aborted_some.xml',
                     2, 'Aborted')

    @mock.patch('logging.warning')
    @mock.patch('logging.error')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_run_wait8(self, mock_logging, mock_logging_err, mock_jobsubmit):
        """Ensure BeakerRunner.run works."""
        # pylint: disable=W0613

        misc.exec_on(self.myrunner, mock_jobsubmit, 'beaker_aborted_some.xml',
                     5, 'Cancelled')

    @mock.patch('skt.runner.BeakerRunner.getresultstree')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_soak_hidden(self, mock_jobsubmit, mock_getresultstree):
        """ Ensure that soaking tests don't affect overall test result."""

        beaker_xml = misc.get_asset_content('beaker_results.xml')
        mock_getresultstree.return_value = fromstring(beaker_xml)
        mock_jobsubmit.return_value = "J:0001"

        # no need to wait 60 seconds
        # though beaker_pass_results.xml only needs one iteration
        self.myrunner.watchdelay = 0.1

        result = misc.exec_on(self.myrunner, mock_jobsubmit,
                              'beaker_results.xml', 5, 'Completed',
                              soak=True)
        self.assertEqual(SKT_SUCCESS, result)

    @mock.patch('skt.runner.BeakerRunner.getresultstree')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_soak_fails(self, mock_jobsubmit, mock_getresultstree):
        """ Ensure that soaking tests don't affect overall
            test result. This tests test failure."""

        beaker_xml = misc.get_asset_content('beaker_results.xml')
        mock_getresultstree.return_value = fromstring(beaker_xml)
        mock_jobsubmit.return_value = "J:0001"

        # no need to wait 60 seconds
        # though beaker_pass_results.xml only needs one iteration
        self.myrunner.watchdelay = 0.1

        # soak=False : failure must show
        result = misc.exec_on(self.myrunner, mock_jobsubmit,
                              'beaker_results.xml', 5, 'Completed',
                              soak=False)

        self.assertEqual(result, SKT_FAIL)

    @mock.patch('logging.error')
    @mock.patch('logging.warning')
    @mock.patch('skt.runner.BeakerRunner.getresultstree')
    @mock.patch('skt.runner.BeakerRunner._BeakerRunner__jobsubmit')
    def test_soak_fails2(self, mock_jobsubmit, mock_getresultstree,
                         mock_warning, mock_error):
        """ Ensure that soaking tests don't affect overall
            test result. This tests test abort."""
        # pylint: disable=unused-argument

        beaker_xml = misc.get_asset_content('beaker_aborted_some.xml')
        mock_getresultstree.return_value = fromstring(beaker_xml)
        mock_jobsubmit.return_value = "J:0001"

        # no need to wait 60 seconds
        # though beaker_pass_results.xml only needs one iteration
        self.myrunner.watchdelay = 0.1

        # soak=False : failure must show
        result = misc.exec_on(self.myrunner, mock_jobsubmit,
                              'beaker_aborted_some.xml', 5,
                              'Completed', soak=False)

        self.assertEqual(result, SKT_ERROR)
