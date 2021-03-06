Installation Instructions
=========================

There are three separate components in a complete autophone system:

- one or more servers running the autophone app
- mobile devices with root access running the SUT agent
- a server running phonedash to collect, serve, and present the results

Since an autophone server appears to be limited to 4-6 devices (because of
power issues and problems with adb), there can be multiple autophone servers
to support more devices. Each server runs independently with no knowledge of
the others.

The phonedash server is optional, e.g. for development environments. It can
be found at https://github.com/markrcote/phonedash/. It is customized for
the s1s2 test and will be eventually deprecated in favour of DataZilla.


Setting up autophone
--------------------

Autophone doesn't yet support distuils, so some prerequisite Python packages
must be manually installed by pip, easy_install, or some other method: pytz,
pulsebuildmonitor, and mozprofile.

At the moment autophone is packaged with only one test, named s1s2. It
measures fennec load times for a couple different pages, served both remotely
and from a local file.

Put the pages to be served into autophone/configs. You will need a way to
serve them (FIXME: autophone should do this). If you're using phonedash,
it can serve the files by just dropping them into phonedash/html/.

The s1s2 test is configured in the file configs/s1s2_settings.ini:

    [htmlfiles]
    file3 = configs/Twitter_files
    file1 = configs/startup6.html
    file2 = configs/Twitter2.html
    
    [urls]
    # These must resolve, so ensure this matches what is in the code for
    # the testroot
    local-twitter = file://mnt/sdcard/s1test/Twitter2.html
    local-blank = file://mnt/sdcard/s1test/startup6.html
    remote-twitter = http://192.168.1.133:8100/Twitter2.html
    remote-blank = http://192.168.1.133:8100/startup6.html
    
    [settings]
    iterations = 20
    resulturl = http://192.168.1.133:8100/api/s1s2_add/

[htmlfiles] contains the paths of files to transfer to the phone. [urls]
lists local and remote URLs (FIXME: we could make this less redundant).
Remember that the remote links must be external IPs, since they are loaded
from the mobile devices.

The resulturl is the URL used to POST results to the database.

If you want to get notifications indicating when Autophone has disabled
a device due to errors, you can create email.ini like so:

    [report]
    from = <from address>

    [email]
    dest = <list of to addresses>
    server = <SMTP server>
    port = <SMTP server port, defaults to 465>
    ssl = <enable SMTP over SSL, defaults to true>
    username = <username for SMTP, optional>
    password = <password for SMTP, optional>

### Setting up devices ###

Each device must be rooted and have the SUT agent installed. See
https://wiki.mozilla.org/Auto-tools/Projects/SUTAgent for details
on the SUT agent.

After installing the SUT agent on all the phones, you need to configure
them. For each device, you will have to edit SUTAgent.ini appropriately to
configure how it connects to the registration server, setting "POOL" to the
phone's serial number (you can see the serial numbers of all connected devices
via "adb devices"), "IPAddr" to the external IP of the machine running
autophone (this is the SUT "registration server"), and "HARDWARE" to some short
descriptive string, e.g. "samsung_gs2" or "droid_pro".

You may also need to add a "Network Settings" section if you wish to configure
your device to connect to a specific network on startup.

An example SUTAgent.ini file might be:

    [Registration Server]
    IPAddr = 192.168.1.124
    PORT = 28001
    HARDWARE = lg_g2x
    POOL = 033c20444240b197
    
    [Network Settings]
    SSID = Mozilla Ateam
    AUTH = open
    ENCR = disabled
    KEY = auto
    ADHOC = 0

Run "python publishAgentIni.py -i <phone ip>" to push the SUTAgent.ini file
to the phone found at that IP.

### Setting up phonedash ###

Phonedash is a templeton-based app (https://github.com/markrcote/templeton).
It stores results in either a MySQL or a sqlite database.

Database configuration goes into server/settings.cfg. The file has one
section, [database], with the following options:

- SQL_TYPE: can be set to either "mysql" (default) or "sqlite".
- SQL_DB: database name (MySQL) or path (sqlite)
- SQL_SERVER: MySQL database server IP or hostname
- SQL_USER: MySQL username
- SQL_PASSWD: MySQL password

When phonedash is started, it will create the requisite table if not found.
