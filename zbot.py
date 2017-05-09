#!/usr/bin/env python3

__author__ = 'mcrane'

from pwd import getpwnam
import subprocess
import time
import irc
from irc import bot
import threading
from queue import Queue, Empty

import click
import daemonocle

import configparser
from os import linesep

try:
    import pydevd

    pydevd.settrace('192.168.3.7', port=32333, stdoutToServer=True, stderrToServer=True)
    DEBUGGING = True
except ImportError:
    DEBUGGING = False


class ReadThread(threading.Thread):
    def __init__(self, proc, queue, name='ReadThread'):
        """ constructor, setting initial variables """
        self._stopevent = threading.Event()
        self._sleepperiod = 1.0
        self.proc = proc
        self.queue = queue
        threading.Thread.__init__(self, name=name)

    def run(self):
        while not self._stopevent.isSet() and self.proc is not None and self.proc.poll() is None:
            c = self.proc.stdout.read(1)
            self.queue.put(c)

    def join(self, timeout=None):
        """ Stop the thread and wait for it to end. """
        self._stopevent.set()
        threading.Thread.join(self, timeout)


class FrotzBot(irc.bot.SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667, username=None, password=None, ipv6=False, cmd_trigger='!'):
        self.nickname = nickname
        self.channel = channel
        self.max_nick_len = 9
        self.trigger = cmd_trigger
        self.read_thread = None
        self.q = None
        self.proc = None
        factory = irc.connection.Factory(ipv6=ipv6)
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port, password)],
                                            username, username, connect_factory=factory)

    def shutdown(self):
        for chan in self.channels.keys():
            self.connection.part(chan)
        self.connection.quit()
        self.die()

    def start_game(self, c):
        self.proc = subprocess.Popen(['./dfrotz', '-h', '200', '-w', '120', 'HITCHHIK.DAT'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False,
                                     universal_newlines=True, bufsize=0)
        self.q = Queue()
        time.sleep(0.5)
        self.read_thread = ReadThread(self.proc, self.q)
        self.read_thread.daemon = True
        self.read_thread.start()

    def on_featurelist(self, c, e):
        for f in e.arguments:
            # get the max nick length
            if f.startswith('NICKLEN='):
                self.max_nick_len = int(f[len('NICKLEN='):])

    # change nick if need be by adding '_' and truncating if necessary
    def on_nicknameinuse(self, c, e):
        c.nick((c.get_nickname() + '_')[-self.max_nick_len:])

    def on_nickcollision(self, c, e):
        c.nick((c.get_nickname() + '_')[-self.max_nick_len:])

    def on_unavailresource(self, c, e):
        c.nick((c.get_nickname() + '_')[-self.max_nick_len:])

    def on_welcome(self, c, e):
        self.connection.buffer.errors = 'replace'  # fix decoding errors
        c.join(self.channel)

    def on_privmsg(self, c, e):
        if e.arguments[0] == 'die':
            for chan in self.channels.keys():
                c.part(chan)
            c.quit()
            self.die()

    def on_pubmsg(self, c, e):
        if e.arguments[0].startswith(self.trigger):
            cmd = e.arguments[0][1:].strip().lower()
            if cmd == 'start':
                if self.proc is None or self.proc.poll() is not None:
                    self.start_game(c)
                    self.output_to_channel(c, e.target)
                else:
                    c.privmsg(e.target, 'The game is running.')
            elif cmd == 'stop':
                if self.proc is not None and self.proc.poll() is None:
                    try:
                        self.proc.terminate()
                        c.privmsg(e.target, 'The game is offline.')
                    except ProcessLookupError:
                        pass
                else:
                    c.privmsg(e.target, 'The game is not running.')
        if e.arguments[0].lower().startswith('z:'):
            if self.proc is None or self.proc.poll() is not None:
                c.privmsg(e.target, 'The game is offline.')
                return
            self.proc.stdin.write(e.arguments[0][2:].strip())
            self.proc.stdin.write('\n')
            self.output_to_channel(c, e.target)
            if self.proc is None or self.proc.poll() is not None:
                c.privmsg(e.target, 'The game is offline.')


    def output_to_channel(self, conn, chan):
        lines = ''
        while True:
            try:
                lines += self.q.get(timeout=.5)  # or q.get(timeout=.5)
            except Empty:
                break
        for line in lines.split('\n'):
            conn.privmsg(chan, line)
            time.sleep(0.25)


# def on_join(self, c, e):
# print(e.source)


class App():
    def __init__(self, channel, nick, server, port, ipv6, username, password):
        self.bot = FrotzBot(channel, nick, server, port, username, password, ipv6)

    def run(self):
        self.bot.start()

    def shutdown(self, message, code):
        if self.bot.connection.is_connected():
            self.bot.shutdown()


def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo('Frotzbot Version 1.0')
    ctx.exit()


def print_format(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(
        "{0}[ServerName]{0}Channel = #botchannel{0}Nick = mybotnick{0}Address = irc.example.net{0}Port = 6660{0}IPv4 = True{0}Username = Ircname{0}Password = secret{0}".format(
            linesep))
    click.echo('The server name is case sensitive. Option names are not. Any option can be left out and/or supplanted by command line options.')
    click.echo()
    ctx.exit()


@click.group()
@click.option('--version', is_flag=True, callback=print_version, expose_value=False, is_eager=True,
              help='Print the Frotzbot version.')
@click.option('--format', is_flag=True, callback=print_format, expose_value=False, is_eager=True,
              help='Print an example config file.')
def cli():
    pass


@cli.command()
@click.option('--workdir', '-k', default='/', type=click.Path(exists=True), help='Working directory for the bot.')
@click.option('--pidfile', '-i', type=click.Path(exists=False),
              help='PID file for the bot. (Required if the start and stop commands are to be used.)')
@click.option('--user', type=str, help='User to run the bot under.')
@click.option('--group', type=str, help='Group to run the bot under.')
@click.option('--detach/--no-detach', default=True, help='Detach the bot ot run in the foreground.')
@click.option('--file', '-f', type=click.Path(exists=True), help='A file to read the settings from.')
@click.option('--channel', '-c', help='The channel to join.')
@click.option('--nick', '-n', help="The bot's nickname.")
@click.option('--server', '-s', default='localhost',
              help=' Address of the server to join or the server from the config file.')
@click.option('--port', '-p', default=6667, help="The server's port.")
@click.option('--ipv6', '-6', is_flag=True, help="Use if the server's address is IPv6.")
@click.option('--username', '-u', help="The bot's IRC username.")
@click.option('--password', '-w', help="The bot's IRC server password.")
def start(workdir, pidfile, user, group, detach, file, channel, nick, server, port, ipv6, username, password):
    if file is not None:
        cf = configparser.ConfigParser()
        cf.read(file)
        if server is None: server = 'default'
        if server not in cf:
            click.echo('Server %s not found in %s.' % (server, file))
            exit(-1)

        section = cf[server]
        channel = channel or section.get('Channel', None)
        nick = nick or section.get('Nick', None)
        server = server or section.get('Address', None)
        port = port or section.getint("Port", port)
        ipv6 = ipv6 or section.getboolean('IPv6', False)
        username = username or section.get('Username', None)
        password = password or section.get('Password', None)

    if user is not None:
        user = getpwnam(user).pw_uid
    if group is not None:
        group = getpwnam(group).pw_gid
    daemon = daemonocle.Daemon(
        workdir=workdir,
        pidfile=pidfile,
        detach=detach,
        close_open_files=True,
        uid=user,
        gid=group,
    )

    click.echo('Connecting to server %s (%s) as %s...' % (server, port, nick))
    app = App(channel, nick, server, port, ipv6, username, password)
    daemon.worker = app.run
    daemon.shutdown_callback = app.shutdown
    try:
        daemon.do_action('start')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError, PermissionError) as err:
        print(err)


@cli.command()
@click.option('--pidfile', '-i', type=click.Path(exists=False), help='PID file for the bot.', required=True)
def stop(pidfile):
    daemon = daemonocle.Daemon(
        pidfile=pidfile,
    )

    try:
        daemon.do_action('stop')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError, PermissionError) as err:
        print(err)


@cli.command()
@click.option('--pidfile', '-i', type=click.Path(exists=False), help='PID file for the bot.', required=True)
def status(pidfile):
    daemon = daemonocle.Daemon(
        pidfile=pidfile,
    )

    try:
        daemon.do_action('status')
    except (daemonocle.exceptions.DaemonError, FileNotFoundError) as err:
        print(err)


if __name__ == '__main__':
    cli()
