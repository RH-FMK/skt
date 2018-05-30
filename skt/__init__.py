# Copyright (c) 2017 Red Hat, Inc. All rights reserved. This copyrighted
# material is made available to anyone wishing to use, modify, copy, or
# redistribute it subject to the terms and conditions of the GNU General
# Public License v.2 or later.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

from email.errors import HeaderParseError
import email.header
import email.parser
import logging
import os
import re
import shutil
import subprocess
import requests


def get_patch_mbox(url):
    """
    Retrieve a string representing mbox of the patch.

    Args:
        url: Patchwork URL of the patch to retrieve

    Returns:
        String representing body of the patch mbox

    Raises:
        Exception in case the URL is currently unavailable or invalid
    """
    # Use os.path for manipulation with URL because urlparse can't deal
    # with URLs ending both with and without slash.
    mbox_url = os.path.join(url, 'mbox')

    try:
        response = requests.get(mbox_url)
    except requests.exceptions.RequestException as exc:
        raise(exc)

    if response.status_code != requests.codes.ok:
        raise Exception('Failed to retrieve patch from %s, returned %d' %
                        (url, response.status_code))

    return response.content


def get_patch_name(content):
    """
    Retrieve patch name from 'Subject' header from the mbox string
    representing a patch.

    Args:
        content: String representing patch mbox

    Returns:
        Name of the patch. <SUBJECT MISSING> is returned if no subject is
        found, and <SUBJECT ENCODING INVALID> if header decoding fails.
    """
    headers = email.parser.Parser().parsestr(content, True)
    subject = headers['Subject']
    if not subject:
        # Emails return None if the header is not found so use a stub subject
        # instead of it
        return '<SUBJECT MISSING>'

    # skt's custom CSV parsing doesn't understand multiline values, until we
    # switch to a proper parser we need a temporary fix. Use separate
    # replacements to handle Windows / *nix endlines and mboxes which contain
    # '\n' and a space instead of '\n\t' as well.
    # Tracking issue: https://github.com/RH-FMK/skt/issues/119
    subject = subject.replace('\n', ' ').replace('\t', '').replace('\r', '')

    try:
        # decode_header() returns a list of tuples (value, charset)
        decoded = [value for value, _ in email.header.decode_header(subject)]
    except HeaderParseError:
        # We can't parse the original subject so use a stub one instead
        return '<SUBJECT ENCODING INVALID>'

    return ''.join(decoded)


class KernelTree(object):
    """
    KernelTree - a kernel git repository "checkout", i.e. a clone with a
    working directory
    """
    def __init__(self, uri, ref=None, workdir=None, source_dir=None,
                 fetch_depth=None):
        """
        Initialize a KernelTree.

        Args:
            uri:    The Git URI of the repository's origin remote.
            ref:    The remote reference to checkout. Assumed to be "master",
                    if not specified.
            workdir:
                    The work directory is where skt stores various parts of
                    the build, including the kernel source and logs.
            source_dir:
                    The directory that holds the kernel source. By default,
                    it is set to 'source' within the work directory.
            fetch_depth:
                    The amount of git history to include with the clone.
                    Smaller depths lead to faster repo clones.
        """
        self.workdir = workdir
        if not source_dir:
            self.source_dir = "{}/source".format(self.workdir)
        self.gdir = "%s/.git" % self.source_dir
        # The origin remote's URL
        self.uri = uri
        # The remote reference to checkout
        self.ref = ref if ref is not None else "master"
        self.info = []
        self.mergelog = "%s/merge.log" % self.workdir

        try:
            os.mkdir(self.workdir)
        except OSError:
            pass

        try:
            os.unlink(self.mergelog)
        except OSError:
            pass

        # Create a directory to hold the kernel source
        if not os.path.isdir(self.source_dir):
            os.mkdir(self.source_dir)

        self.git_cmd("init")

        try:
            self.git_cmd("remote", "set-url", "origin", self.uri)
        except subprocess.CalledProcessError:
            self.git_cmd("remote", "add", "origin", self.uri)

        self.fetch_depth = fetch_depth

        logging.info("base repo url: %s", self.uri)
        logging.info("base ref: %s", self.ref)
        logging.info("work dir: %s", self.workdir)
        logging.info("source_dir: %s", self.source_dir)

    def git_cmd(self, *args, **kwargs):
        args = list(
            [
                "git",
                "--work-tree",
                self.source_dir,
                "--git-dir",
                self.gdir
            ]
        ) + list(args)
        logging.debug("executing: %s", " ".join(args))
        subprocess.check_call(args,
                              env=dict(os.environ, **{'LC_ALL': 'C'}),
                              **kwargs)

    def getpath(self):
        return self.workdir

    def dumpinfo(self, fname='buildinfo.csv'):
        """
        Write build information to the specified file in ad-hoc CSV format.
        The order of the "columns" in the file depends on the order various
        member functions were called in.

        Args:
            fname:  Name of the output file, relative to the workdir.
                    Default is "buildinfo.csv".

        Returns:
            Full path to the written file.
        """
        fpath = '/'.join([self.workdir, fname])
        with open(fpath, 'w') as f:
            for iitem in self.info:
                f.write(','.join(iitem) + "\n")
        return fpath

    def get_commit_date(self, ref=None):
        """
        Get the committer date of the commit pointed at by the specified
        reference, or of the currently checked-out commit, if not specified.

        Args:
            ref:    The reference to commit to get the committer date of,
                    or None, if the currently checked-out commit should be
                    used instead.
        Returns:
            The epoch timestamp string of the commit's committer date.
        """
        args = [
            "git",
            "--work-tree", self.source_dir,
            "--git-dir", self.gdir,
            "show",
            "--format=%ct",
            "-s"
        ]

        if ref is not None:
            args.append(ref)

        logging.debug("git_commit_date: %s", args)
        grs = subprocess.Popen(args, stdout=subprocess.PIPE)
        (stdout, _) = grs.communicate()

        return int(stdout.rstrip())

    def get_commit_hash(self, ref=None):
        """
        Get the full hash of the commit pointed at by the specified reference,
        or of the currently checked-out commit, if not specified.

        Args:
            ref:    The reference to commit to get the hash of, or None, if
                    the currently checked-out commit should be used instead.
        Returns:
            The commit's full hash string.
        """
        args = [
            "git",
            "--work-tree", self.source_dir,
            "--git-dir", self.gdir,
            "show",
            "--format=%H",
            "-s"
        ]

        if ref is not None:
            args.append(ref)

        logging.debug("git_commit: %s", args)
        grs = subprocess.Popen(args, stdout=subprocess.PIPE)
        (stdout, _) = grs.communicate()

        return stdout.rstrip()

    def checkout(self):
        """
        Clone and checkout the specified reference from the specified repo URL
        to the specified working directory. Requires "ref" (reference) to be
        specified upon creation.

        Returns:
            Full hash of the last commit.
        """
        dstref = "refs/remotes/origin/%s" % (self.ref.split('/')[-1])
        logging.info("fetching base repo")
        git_fetch_args = [
            "fetch", "-n", "origin",
            "+%s:%s" % (self.ref, dstref)
        ]
        # If the user provided extra arguments for the git fetch step, append
        # them to the existing set of arguments.
        if self.fetch_depth:
            git_fetch_args.extend(['--depth', self.fetch_depth])

        # The git_cmd() method expects a list of args, not a list of strings,
        # so we need to expand our list into args with *.
        self.git_cmd(*git_fetch_args)

        logging.info("checking out %s", self.ref)
        self.git_cmd("checkout", "-q", "--detach", dstref)
        self.git_cmd("reset", "--hard", dstref)

        head = self.get_commit_hash()
        self.info.append(("base", self.uri, head))
        logging.info("baserepo %s: %s", self.ref, head)
        return str(head).rstrip()

    def cleanup(self):
        logging.info("cleaning up %s", self.workdir)
        shutil.rmtree(self.workdir)

    def get_remote_url(self, remote):
        rurl = None
        try:
            grs = subprocess.Popen(
                [
                    "git",
                    "--work-tree", self.source_dir,
                    "--git-dir", self.gdir,
                    "remote", "show", remote
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            (stdout, _) = grs.communicate()
            for line in stdout.split("\n"):
                m = re.match('Fetch URL: (.*)', line)
                if m:
                    rurl = m.group(1)
                    break
        except subprocess.CalledProcessError:
            pass

        return rurl

    def getrname(self, uri):
        rname = (uri.split('/')[-1].replace('.git', '')
                 if not uri.endswith('/')
                 else uri.split('/')[-2].replace('.git', ''))
        while self.get_remote_url(rname) == uri:
            logging.warning(
                "remote '%s' already exists with a different uri, adding '_'",
                rname
            )
            rname += '_'

        return rname

    def merge_git_ref(self, uri, ref="master"):
        rname = self.getrname(uri)
        head = None

        try:
            self.git_cmd("remote", "add", rname, uri, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            pass

        dstref = "refs/remotes/%s/%s" % (rname, ref.split('/')[-1])
        logging.info("fetching %s", dstref)
        self.git_cmd("fetch", "-n", rname,
                     "+%s:%s" % (ref, dstref))

        logging.info("merging %s: %s", rname, ref)
        try:
            grargs = {'stdout': subprocess.PIPE} if \
                logging.getLogger().level > logging.DEBUG else {}

            self.git_cmd("merge", "--no-edit", dstref, **grargs)
            head = self.get_commit_hash(dstref)
            self.info.append(("git", uri, head))
            logging.info("%s %s: %s", rname, ref, head)
        except subprocess.CalledProcessError:
            logging.warning("failed to merge '%s' from %s, skipping", ref,
                            rname)
            self.git_cmd("reset", "--hard")
            return (1, None)

        return (0, head)

    def merge_patchwork_patch(self, uri):
        patch_content = get_patch_mbox(uri)

        logging.info("Applying %s", uri)

        gam = subprocess.Popen(
            ["git", "am", "-"],
            cwd=self.source_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, **{'LC_ALL': 'C'})
        )

        (stdout, _) = gam.communicate(patch_content)
        retcode = gam.wait()

        if retcode != 0:
            self.git_cmd("am", "--abort")

            with open(self.mergelog, "w") as fileh:
                fileh.write(stdout)

            raise Exception("Failed to apply patch %s" %
                            os.path.basename(os.path.normpath(uri)))

        patchname = get_patch_name(patch_content)
        # FIXME Do proper CSV escaping, or switch data format instead of
        #       maiming subjects (ha-ha). See issue #119.
        # Replace commas with semicolons to avoid clashes with CSV separator
        self.info.append(("patchwork", uri, patchname.replace(',', ';')))

    def merge_patch_file(self, path):
        if not os.path.exists(path):
            raise Exception("Patch %s not found" % path)
        args = ["git", "am", path]
        try:
            subprocess.check_output(
                args,
                cwd=self.source_dir,
                env=dict(os.environ, **{'LC_ALL': 'C'})
            )
        except subprocess.CalledProcessError as exc:
            self.git_cmd("am", "--abort")

            with open(self.mergelog, "w") as fileh:
                fileh.write(exc.output)

            raise Exception("Failed to apply patch %s" % path)

        self.info.append(("patch", path))

    def bisect_start(self, good):
        os.chdir(self.workdir)
        binfo = None
        gbs = subprocess.Popen(
            [
                "git",
                "--work-tree", self.source_dir,
                "--git-dir", self.gdir,
                "bisect", "start", "HEAD", good
            ],
            stdout=subprocess.PIPE
        )
        (stdout, _) = gbs.communicate()

        for line in stdout.split("\n"):
            m = re.match('^Bisecting: (.*)$', line)
            if m:
                binfo = m.group(1)
                logging.info(binfo)
            else:
                logging.info(line)

        return binfo

    def bisect_iter(self, bad):
        os.chdir(self.workdir)
        ret = 0
        binfo = None
        status = "good"

        if bad == 1:
            status = "bad"

        logging.info("git bisect %s", status)
        gbs = subprocess.Popen(
            [
                "git",
                "--work-tree", self.source_dir,
                "--git-dir", self.gdir,
                "bisect", status
            ],
            stdout=subprocess.PIPE
        )
        (stdout, _) = gbs.communicate()

        for line in stdout.split("\n"):
            m = re.match('^Bisecting: (.*)$', line)
            if m:
                binfo = m.group(1)
                logging.info(binfo)
            else:
                m = re.match('^(.*) is the first bad commit$', line)
                if m:
                    binfo = m.group(1)
                    ret = 1
                    logging.warning("Bisected, bad commit: %s", binfo)
                    break
                else:
                    logging.info(line)

        return (ret, binfo)
