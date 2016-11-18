import os
import configparser
import smtplib

import myutils
from mailutils import assemble_mail

from .run_cmd import run_cmd

class BuildSession:
  def __init__(self, config_file):
    self.config = config = configparser.ConfigParser()
    config.optionxform = lambda option: option
    if not config.read(config_file):
      raise Exception('failed to read config file', config_file)

    self.env = os.environ.copy()
    self.env.update(config.items('enviroment variables'))

    if 'MAKEFLAGS' not in self.env:
      cores = os.cpu_count()
      if cores is not None:
        self.env['MAKEFLAGS'] = '-j{0} -l{0}'.format(cores)

    self.repodir = os.path.expanduser(config.get('repository', 'repodir'))
    self.destdir = os.path.expanduser(config.get('repository', 'destdir'))
    self.cwd = self.repodir

    self.repomail = config.get('repository', 'email')
    self.mymaster = config.get('lilac', 'master')

    self.myname = config.get('lilac', 'name')
    myaddress = config.get('lilac', 'email')
    self.myemail = '%s <%s>' % (self.myname, myaddress)

    self.mydir = os.path.expanduser('~/.%s' % self.myname)
    myutils.lock_file(os.path.join(self.mydir, '.lock'))

    self.send_email = config.getboolean('lilac', 'send_email')

  def send_repo_mail(self, subject, msg):
    self.sendmail(self.repomail, subject, msg)

  def send_master_mail(self, subject, msg):
    self.sendmail(self.mymaster, subject, msg)

  def sendmail(self, recipients, subject, msg):
    if self.send_email:
      subject = '[%s] %s' % (self.myname, subject)
      self._sendmail(recipients, self.myemail, subject, msg)

  def _sendmail(self, to, from_, subject, msg):
    if len(msg) > 5 * 1024 ** 2:
      msg = msg[:1024 ** 2] + '\n\n日志过长，省略ing……\n\n' + msg[-1024 ** 2:]
    msg = assemble_mail(subject, to, from_, text=msg)
    s = self._smtp_connect()
    s.send_message(msg)
    s.quit()

  def _smtp_connect(self):
    config = self.config

    host = config.get('smtp', 'host', fallback='')
    port = config.getint('smtp', 'port', fallback=0)
    username = config.get('smtp', 'username', fallback='')
    password = config.get('smtp', 'password', fallback='')
    if config.getboolean('smtp', 'use_ssl', fallback=False):
      smtp_cls = smtplib.SMTP_SSL
    else:
      smtp_cls = smtplib.SMTP
    connection = smtp_cls(host, port)
    if not host:
      # __init__ doesn't connect; let's do it
      connection.connect()
    if username != '' and password != '':
      connection.login(username, password)
    return connection

  def set_packager(self, name, email):
    self.env['PACKAGER'] = '%s (on behalf of %s) <%s>' % (
      self.myname, name, email)

  def sign_and_copy(self, name):
    self.cwd = os.path.join(self.repodir, name)
    pkgs = [x for x in os.listdir(self.cwd) if x.endswith('.pkg.tar.xz')]
    for pkg in pkgs:
      self.run_cmd(['gpg', '--pinentry-mode', 'loopback', '--passphrase', '',
                    '--detach-sign', '--', pkg])
    for f in os.listdir(self.cwd):
      if not f.endswith(('.pkg.tar.xz', '.pkg.tar.xz.sig', '.src.tar.gz')):
        continue
      try:
        os.link(f, os.path.join(self.destdir, f))
      except FileExistsError:
        pass

  def run_cmd(self, *args, **kwargs):
    run_cmd(*args, env=self.env, cwd=self.cwd, **kwargs)
