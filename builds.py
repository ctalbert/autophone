# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import datetime
import ftplib
import logging
import os
import pytz
import re
import shutil
import tempfile
import urllib
import urlparse


class NightlyBranch(object):

    nightly_dirnames = [re.compile('(.*)-mozilla-central-android$')]

    def nightly_ftpdir(self, year, month):
        return 'ftp://ftp.mozilla.org/pub/mobile/nightly/%d/%02d/' % (year,
                                                                      month)

    def ftpdirs(self, start_time, end_time):
        dirs = []
        y = start_time.year
        m = start_time.month
        while y < end_time.year or m <= end_time.month:
            dirs.append(self.nightly_ftpdir(y, m))
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
        return dirs

    def build_info_from_ftp(self, ftpline):
        srcdir = ftpline.split(' ')[-1].strip()
        build_time = None
        dirnamematch = None
        logging.debug('matching dir names')
        for r in self.nightly_dirnames:
            dirnamematch = r.match(srcdir)
            if dirnamematch:
                break
        if dirnamematch:
            logging.debug('build time')
            build_time = datetime.datetime.strptime(dirnamematch.group(1),
                                                    '%Y-%m-%d-%H-%M-%S')
            build_time = build_time.replace(tzinfo=pytz.timezone('US/Pacific'))
            logging.debug('got build time')
        logging.debug('got info')
        return (srcdir, build_time)

    def build_date_from_url(self, url):
        # nightly urls are of the form
        #  ftp://ftp.mozilla.org/pub/mobile/nightly/<year>/<month>/<year>-
        #    <month>-<day>-<hour>-<minute>-<second>-<branch>-android/
        #    <buildfile>
        m = re.search('nightly\/[\d]{4}\/[\d]{2}\/([\d]{4}-[\d]{2}-[\d]{2}-[\d]{2}-[\d]{2}-[\d]{2})-', url)
        if not m:
            return None
        return datetime.datetime.strptime(m.group(1), '%Y-%m-%d-%H-%M-%S')


class TinderboxBranch(object):

    main_ftp_url = 'ftp://ftp.mozilla.org/pub/mozilla.org/mobile/tinderbox-builds/'

    def ftpdirs(self, start_time, end_time):
        # FIXME: Can we be certain that there's only one buildID (unique
        # timestamp) regardless of branch (at least m-i vs m-c)?
        return [self.main_ftp_url + 'mozilla-inbound-android/',
                self.main_ftp_url + 'mozilla-central-android/']

    def build_info_from_ftp(self, ftpline):
        srcdir = ftpline.split()[8].strip()
        build_time = datetime.datetime.fromtimestamp(int(srcdir), pytz.timezone('US/Pacific'))
        return (srcdir, build_time)

    def build_date_from_url(self, url):
        # tinderbox urls are of the form
        #   ftp://ftp.mozilla.org/pub/mozilla.org/mobile/tinderbox-builds/
        #     <branch>-android/<build timestamp>/<buildfile>
        m = re.search('tinderbox-builds\/.*-android\/[\d]+\/', url)
        if not m:
            return None
        return datetime.datetime.fromtimestamp(int(m.group(1)),
                                               pytz.timezone('US/Pacific'))


class BuildCache(object):

    MAX_NUM_BUILDS = 20
    EXPIRE_AFTER_SECONDS = 60*60*24

    class FtpLineCache(object):
        def __init__(self):
            self.lines = []
        def __call__(self, line):
            self.lines.append(line)

    def __init__(self, cache_dir='builds'):
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)

    @classmethod
    def branch(cls, s):
        if 'nightly' in s:
            return NightlyBranch()
        if 'tinderbox' in s:
            return TinderboxBranch()
        return None

    def find_latest_build(self, branch_name='nightly'):
        # This assumes at least one build has been created in the last 24
        # hours.
        now = datetime.datetime.now()
        builds = self.find_builds(now - datetime.timedelta(days=1), now,
                                  branch_name)
        builds.sort()
        return builds[-1]

    def find_builds(self, start_time, end_time, branch_name='nightly'):
        branch = self.branch(branch_name)
        if not branch:
            logging.error('unsupport branch "%s"' % branch_name)
            return []

        if not start_time.tzinfo:
            start_time = start_time.replace(tzinfo=pytz.timezone('US/Pacific'))
        if not end_time.tzinfo:
            end_time = end_time.replace(tzinfo=pytz.timezone('US/Pacific'))

        builds = []
        fennecregex = re.compile("fennec.*\.android-arm\.apk")

        for d in branch.ftpdirs(start_time, end_time):
            url = urlparse.urlparse(d)
            logging.debug('logging into %s...' % url.netloc)
            f = ftplib.FTP(url.netloc)
            f.login()
            logging.debug('looking for builds in %s...' % url.path)
            lines = self.FtpLineCache()
            f.dir(url.path, lines)
            file('lines.out', 'w').write('\n'.join(lines.lines))
            for line in lines.lines:
                srcdir, build_time = branch.build_info_from_ftp(line)

                if not build_time:
                    continue

                if build_time and (build_time < start_time or
                                   build_time > end_time):
                    continue

                newpath = url.path + srcdir
                lines2 = self.FtpLineCache()
                f.dir(newpath, lines2)
                for l2 in lines2.lines:
                    filename = l2.split(' ')[-1].strip()
                    if fennecregex.match(filename):
                        fileurl = url.scheme + '://' + url.netloc + newpath + "/" + filename
                        builds.append(fileurl)
        return builds

    def build_date(self, url):
        branch = self.branch(url)
        builddate = None
        if branch:
            builddate = branch.build_date_from_url(url)
        if not builddate:
            logging.error('bad URL "%s"' % url)
        return builddate

    def get(self, url, force=False):
        build_dir = base64.b64encode(url)
        self.clean_cache([build_dir])
        dir = os.path.join(self.cache_dir, build_dir)
        f = os.path.join(dir, 'build.apk')
        if not os.path.exists(dir):
            os.makedirs(dir)
        if force or not os.path.exists(f):
            # retrieve to temporary file then move over, so we don't end
            # up with half a file if it aborts
            tmpf = tempfile.NamedTemporaryFile(delete=False)
            tmpf.close()
            urllib.urlretrieve(url, tmpf.name)
            os.rename(tmpf.name, f)
        file(os.path.join(dir, 'lastused'), 'w')
        return f

    def clean_cache(self, preserve=[]):
        def lastused_path(d):
            return os.path.join(self.cache_dir, d, 'lastused')
        def keep_build(d):
            if preserve and d in preserve:
                # specifically keep this build
                return True
            if not os.path.exists(lastused_path(d)):
                # probably not a build dir
                return True
            if ((datetime.datetime.now() -
                 datetime.datetime.fromtimestamp(os.stat(lastused_path(d)).st_mtime) <=
                 datetime.timedelta(microseconds=1000*1000*self.EXPIRE_AFTER_SECONDS))):
                # too new
                return True
            return False
            
        builds = [(x, os.stat(lastused_path(x)).st_mtime) for x in
                  os.listdir(self.cache_dir) if not keep_build(x)]
        builds.sort(key=lambda x: x[1])
        while len(builds) > self.MAX_NUM_BUILDS:
            b = builds.pop(0)[0]
            logging.info('Expiring %s' % b)
            shutil.rmtree(os.path.join(self.cache_dir, b))
