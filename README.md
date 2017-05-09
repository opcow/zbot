# zbot
A zmachine bot for IRC

#### Options:

    --version  Print the Frotzbot version.
    --format   Print an example config file.
    --help     Show this message and exit.

#### Commands:

    start
    status
    stop

#### Config Example

    [ServerName]
    Channel = #botchannel
    Nick = mybotnick
    Address = irc.example.net
    Port = 6660
    IPv4 = True
    Username = Ircname
    Password = secret
    Game = ZORK1.DAT


#### Examples

python3 ./zbot.py start --help
python3 ./zbot.py start -c \#somebotchan -n beepboop -s irc.efnet.no -p 6667 -u blark -g HITCHHIK.DAT -k /home/zbot/
python3 ./zbot.py start -f config.ini -s myserver -i ./zbot.pid  -k /home/zbot/
python3 ./zbot.py stop -i ./zbot.pid