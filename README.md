## borgctl - borgbackup without bash scripts

[borgbackup](https://www.borgbackup.org/) is cool and easy to use. But we all end up writing bash scripts for creating/listing/pruning/checking/... backups. borgctl is a borg wrapper that uses yaml configuration files to make life a bit easier.

## Features
- Support for yaml configuration files. Specify what to backup and where to backup
- Just call `borgctl create`, `borgctl list`, `borgctl prune`, ...
- Run borgctl with multiple configuration files to be flexible (e. g. if you want to backup to multiple remote backends or to run `borg create` in append-only-mode and `borg prune/compact` with a Yubikey)
- Ask the user for the borg passphrase (if you don't want to store it on disk). Re-use the entered password for other remote storage backends (you don't have to re-enter it again)
- Some helpers to auto-generate ssh keys and print the authorized_keys entry (with restricted access)
- Run multiple borg commands by running  `borgctl --cron` (like `create` + `prune` + `compact`, commands can be specified in the config file)
- Monitoring: Write a state file (text file with current timestamp in) after successfully executing borg commands
- Logging: Write everything in a log file
- Easy to install, deploy and use

There is also [borgmagic](https://torsion.org/borgmatic/), but it can not handle all my use cases.

## Quickstart

- TODO: ascinema

## Usage

```bash
kmille@linbox:~ sudo borgctl --version
Running borgctl 0.4.2

kmille@linbox:~ sudo borgctl --help   
usage: borgctl [-h] [-d] [-s] [-a] [-c CONFIG] [--cron] [--version]
               {break-lock,check,compact,config,create,delete,diff,export-tar,import-tar,info,init,list,mount,prune,umount,upgrade} ...

borgctl is a simple wrapper around borgbackup. The working directory is /etc/borgctl for root or XDG_CONFIG_HOME/borgctl or ~/.config/borgctl for non-root users. The
log directory is /var/log/borgctl/ for root or $XDG_STATE_HOME or ~/.local/state/borgctl for non-root users.

positional arguments:
  {list,create,check,compact,prune,mount,umount,init,break-lock,info,diff,delete,upgrade,import-tar,export-tar,config}

options:
  -h, --help            show this help message and exit
  -d, --generate-default-config
                        writes default config to $config_dir/default.yml or prints it to stdout if the file already exists
  -s, --generate-ssh-key
                        writes a new ed25519 ssh key to ~/.ssh/borg_$config and updates the config file
  -a, --generate-authorized_keys
                        prints the authorized_keys entry to stdout. You have to add it to the remote host (if you backup over ssh)
  -c CONFIG, --config CONFIG
                        specify the config file to you use. Defaults to default.yml. You can specify multiple config files with -c default.yml -c lokal-disk.yml. If
                        the config file contains a / then a relative/absolute path is asumed. If not, $working_dir/$config will be used
  --cron                run multiple borg commands in a row. The commands to run are specified in the config file (cron_commands)
  --version             show version and exit
kmille@linbox:~ 
```

## Installation

You can find the latest release on the [Github Release](https://github.com/kmille/borgctl/releases) page. There are different ways to get borgctl up and running.

#### Use the [PyPi](https://pypi.org/project/borgctl/) package with

```bash
pip install borgctl
```

The source and binary package can also be found on the Release page (*.whl and *.tar.gz)

#### Use the Debian package

Install the latest package with:

```bash
export LATEST_RELEASE=$(curl -s https://api.github.com/repos/kmille/borgctl/tags | jq -r '.[0].name')
wget "https://github.com/kmille/borgctl/releases/download/$LATEST_RELEASE/borgctl_$LATEST_RELEASE-1_amd64.deb"
apt install ./borgctl*.deb
```

The deb package should work on all Debian based distros. It is created by [create-deb-package.sh](https://github.com/kmille/borgctl/blob/main/contrib/create-deb-package.sh). It requires `borgbackup` and `python3-ruamel.yaml` as dependencies.

#### Use the Arch Linux/Manjaro package with

```bash
yay borgctl
```

You can also download borgctl-*any.pkg.tar.zst and install it with `pacman -U`.

## Default location for config files and logging

borgctl uses config files. If you run `borgctl`, it expects a default.yml in the config directory. You can specify one or more config files with `-c`/`--config`. If the config file contains a /, the config file is interpreted as relative/absolute path. There is also a logging configuration (logging.conf) stored, which is used by borg and borgctl itself.

- Default config location for root user: `/etc/borgctl`

- Default config location for non-root users: `$XDG_CONFIG_HOME/borgctl` or `~/.config/borgctl`

The output of borg and borgctl will be written to borg.log. The file gets logrotated automatically.

- Default log directory for root user: `/var/log/borgctl/`
- Default log directory for non-root users: `$XDG_STATE_HOME/borgctl` or `~/.local/state/borgctl`

The state files are also written to the log directory.

## Walkthrough/How borgctl behaves

borgctl needs a configuration file. If you run it without specifying one, a default.yml in the default config location is expected to exist. If you run it and there is no default.yml, you can use `--generate-default-config` to create one:

```bash
root@linbox:~ borgctl list              
2023-12-26 10:58:31,564  INFO Using config file /etc/borgctl/default.yml
2023-12-26 10:58:31,564 ERROR Could not load config file /etc/borgctl/default.yml
Please use --generate-default-config to create a default config

root@linbox:~ borgctl --generate-default-config
2023-12-26 10:59:28,107  INFO Please make a backup of the passphrase!
2023-12-26 10:59:28,112  INFO Successfully wrote config file to /etc/borgctl/default.yml
```

`/etc/borgctl/default.yml`is just a copy of the [default config file](https://github.com/kmille/borgctl/blob/main/borgctl/default.yml.template). A new diceware password for the borg passphrase is generated. The hostname is used as borg prefix. borgctl can generate a ssh key for you:

```bash
root@linbox:~ borgctl --generate-ssh-key
2023-12-26 11:06:12,784  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:06:12,785  INFO Running ['ssh-keygen', '-t', 'ed25519', '-N', '', '-q', '-f', '/root/.ssh/borg_default', '-C', 'kmille_borg_default@linbox']
2023-12-26 11:06:12,794  INFO Successfully created ssh key /root/.ssh/borg_default
2023-12-26 11:06:12,805  INFO Updated ssh_key in /etc/borgctl/default.yml
root@linbox:~ cat /root/.ssh/borg_default.pub 
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINpVZZjIAzeyGq0oLKVeLzEECoe7RXg6YpAcPIsakboF kmille_borg_default@linbox
```

If you specify a ssh key in the config file, it will be used as output file (if it does not exist). If not, the default name for the ssh key is `$current_username_borg_$config_prefix`.

borgctl can also generate your authorized_keys entry:

```bash
root@linbox:~ borgctl --generate-authorized_keys
2023-12-26 11:07:47,549  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:07:47,551  INFO Using ssh key /root/.ssh/borg_default.pub from config file
2023-12-26 11:07:47,551  INFO Add this line to authorized_keys:
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINpVZZjIAzeyGq0oLKVeLzEECoe7RXg6YpAcPIsakboF kmille_borg_default@linbox

2023-12-26 11:07:47,551  INFO Use this line for restricted access:
command="borg serve --restrict-to-path /opt/test-backup",restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINpVZZjIAzeyGq0oLKVeLzEECoe7RXg6YpAcPIsakboF kmille_borg_default@linbox

2023-12-26 11:07:47,553  INFO Or this all-in-one command:
echo -e 'command="borg serve --restrict-to-path /opt/test-backup",restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINpVZZjIAzeyGq0oLKVeLzEECoe7RXg6YpAcPIsakboF kmille_borg_default@linbox\n' | ssh backup-host1 'cat >> /home/backuper/.ssh/authorized_keys'

```

#### Running borg commands with borgctl

Please update the config file (what to backup (`borg_create_backup_dirs` and `borg_create_excludes` and where to backup (`repository`)). Then you can create your first backup:

```bash
root@linbox:~ borgctl create
2023-12-26 11:11:35,197  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:11:35,199  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose create --progress --stats --one-file-system --compression=lz4 --exclude=.cache ::linbox_2023-12-26_11:11:35 /usr/bin
2023-12-26 11:11:35,718  INFO Creating archive at "/root/borg-repo::linbox_2023-12-26_11:11:35"
2023-12-26 11:12:07,934  INFO ------------------------------------------------------------------------------                                                             
2023-12-26 11:12:07,935  INFO Repository: /root/borg-repo
2023-12-26 11:12:07,936  INFO Archive name: linbox_2023-12-26_11:11:35
2023-12-26 11:12:07,937  INFO Archive fingerprint: 079e9c226455ff1b816be986bf49029c3cdf28ec04e9f6bf2d387ea9a4f24d87
2023-12-26 11:12:07,937  INFO Time (start): Tue, 2023-12-26 11:11:35
2023-12-26 11:12:07,938  INFO Time (end):   Tue, 2023-12-26 11:12:06
2023-12-26 11:12:07,938  INFO Duration: 31.04 seconds
2023-12-26 11:12:07,939  INFO Number of files: 3869
2023-12-26 11:12:07,940  INFO Utilization of max. archive size: 0%
2023-12-26 11:12:07,940  INFO ------------------------------------------------------------------------------
2023-12-26 11:12:07,941  INFO                        Original size      Compressed size    Deduplicated size
2023-12-26 11:12:07,942  INFO This archive:                1.55 GB            777.29 MB            777.13 MB
2023-12-26 11:12:07,942  INFO All archives:                1.55 GB            777.29 MB            777.43 MB
2023-12-26 11:12:07,943  INFO 
2023-12-26 11:12:07,943  INFO                        Unique chunks         Total chunks
2023-12-26 11:12:07,944  INFO Chunk index:                    4310                 4322
2023-12-26 11:12:07,945  INFO ------------------------------------------------------------------------------
2023-12-26 11:12:08,101  INFO Updated state file /var/log/borgctl/borg_state_default_create.txt
root@linbox:~ 
root@linbox:~ cat /var/log/borgctl/borg_state_default_create.txt
2023-12-26_11:12:08#                                                                                                                                                     
root@linbox:~ 
root@linbox:~ ls /var/log/borgctl/borg.log 
-rw-r--r-- 1 root root 11K Dec 26 11:12 /var/log/borgctl/borg.log
```

The executed borg command is also printed to stderr. You can adjust the parameters borgctl uses. For example you can add `--json /usr/local/bin/`, which will be added to borg:

```bash
root@linbox:~ borgctl create --json /usr/local/bin 
2023-12-26 11:15:42,954  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:15:42,956  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCAT
ED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose create --progress --stats --one-file-system --compression=lz4 --exclude=.cache --json ::linbox_2023-12-26_11:15:42 /us
r/bin /usr/local/bin                                                                
2023-12-26 11:15:43,518  INFO Creating archive at "/root/borg-repo::linbox_2023-12-26_11:15:42"
{                                         
    "archive": {
        "command_line": [
            "/usr/bin/borg",
...
```

#### Adjusting default arguments for single borg commands

For every borg command, you can add command line parameter/arguments in the config file by specifying `borg_$borgcommand_arguments`. They are used automatically. For example, here are default arguments for the create command:

```yaml
borg_create_arguments:
- "--progress"
- "--stats"
- "--one-file-system"
- "--compression=lz4"
```

#### Specifying an archive

If you want to specify an archive, you have to prepend ::

```bash
root@linbox:~ borgctl list                             
2023-12-26 11:18:38,323  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:18:38,325  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose list
linbox_2023-12-26_11:11:35           Tue, 2023-12-26 11:11:35 [079e9c226455ff1b816be986bf49029c3cdf28ec04e9f6bf2d387ea9a4f24d87]
linbox_2023-12-26_11:15:42           Tue, 2023-12-26 11:15:43 [4599ac310b99703407600bc8bfa58ddb80da7be3d613b49fdf75691b99d293e0]
root@linbox:~ 

root@linbox:~ borgctl list linbox_2023-12-26_11:11:35
2023-12-26 11:19:06,975  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:19:06,977  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose list linbox_2023-12-26_11:11:35
Remote: ssh: Could not resolve hostname linbox_2023-12-26_11: Name or service not known
2023-12-26 11:19:07,436 ERROR Connection closed by remote host. Is borg working on the server?
2023-12-26 11:19:07,518 ERROR borg failed with exit code: 2
root@linbox:~ 

root@linbox:~ borgctl list ::linbox_2023-12-26_11:11:35
2023-12-26 11:18:33,787  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:18:33,789  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCAT
ED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose list ::linbox_2023-12-26_11:11:35
drwxr-xr-x root   root          0 Tue, 2023-12-26 10:56:58 usr/bin      
-rwxr-xr-x root   root      21905 Fri, 2023-12-22 20:59:55 usr/bin/tzselect
-rwxr-xr-x root   root      51216 Fri, 2023-12-22 20:59:55 usr/bin/zdump
-rwxr-xr-x root   root      59448 Fri, 2023-12-22 20:59:55 usr/bin/zic  
-rwxr-xr-x root   root      27176 Sat, 2023-03-18 17:07:07 usr/bin/gdbm_dump
...
```

#### Your daily helper: --cron

If you ssh into a server and you know that it uses borgctl, but you don't if there is a special configuration:

Use `--list` to check if there are multiple config files or just the default one.

```bash
root@linbox:~ borgctl --cron
default.yml
```

ThenIn your daily use, you often want to create a backup, prune old backups and then compact the disk space. You can use borgctl --cron for that:

```bash
root@linbox:~ borgctl --cron
2023-12-26 11:22:06,988  INFO Using config file /etc/borgctl/default.yml
2023-12-26 11:22:06,990  INFO Running 'borg create' in --cron mode
2023-12-26 11:22:06,990  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose create --progress --stats --one-file-system --compression=lz4 --exclude=.cache ::linbox_2023-12-26_11:22:06 /usr/bin
2023-12-26 11:22:07,532  INFO Creating archive at "/root/borg-repo::linbox_2023-12-26_11:22:06"
2023-12-26 11:22:08,246  INFO ------------------------------------------------------------------------------                                                             
2023-12-26 11:22:08,246  INFO Repository: /root/borg-repo
2023-12-26 11:22:08,246  INFO Archive name: linbox_2023-12-26_11:22:06
2023-12-26 11:22:08,247  INFO Archive fingerprint: 9be95c7822b2e195fbcdfa63787d20ceb13ba04a7d560d627f2f92941e1dc23e
2023-12-26 11:22:08,247  INFO Time (start): Tue, 2023-12-26 11:22:07
2023-12-26 11:22:08,247  INFO Time (end):   Tue, 2023-12-26 11:22:08
2023-12-26 11:22:08,247  INFO Duration: 0.57 seconds
2023-12-26 11:22:08,248  INFO Number of files: 3869
2023-12-26 11:22:08,248  INFO Utilization of max. archive size: 0%
2023-12-26 11:22:08,248  INFO ------------------------------------------------------------------------------
2023-12-26 11:22:08,249  INFO                        Original size      Compressed size    Deduplicated size
2023-12-26 11:22:08,249  INFO This archive:                1.55 GB            777.29 MB                696 B
2023-12-26 11:22:08,249  INFO All archives:                6.20 GB              3.12 GB            784.13 MB
2023-12-26 11:22:08,250  INFO 
2023-12-26 11:22:08,250  INFO                        Unique chunks         Total chunks
2023-12-26 11:22:08,250  INFO Chunk index:                    4338                17312
2023-12-26 11:22:08,250  INFO ------------------------------------------------------------------------------
2023-12-26 11:22:08,338  INFO Updated state file /var/log/borgctl/borg_state_default_create.txt


2023-12-26 11:22:08,338  INFO Running 'borg prune' in --cron mode
2023-12-26 11:22:08,338  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose prune --list --keep-last 10
2023-12-26 11:22:08,898  INFO Keeping archive (rule: secondly #1):     linbox_2023-12-26_11:22:06           Tue, 2023-12-26 11:22:07 [9be95c7822b2e195fbcdfa63787d20ceb13ba04a7d560d627f2f92941e1dc23e]
2023-12-26 11:22:08,898  INFO Keeping archive (rule: secondly #2):     linbox_2023-12-26_11:21:35           Tue, 2023-12-26 11:21:35 [f8ee55d4340fa76d72d876cc43d92012f199692802a473d766881c45ae1b46bf]
2023-12-26 11:22:08,898  INFO Keeping archive (rule: secondly #3):     linbox_2023-12-26_11:15:42           Tue, 2023-12-26 11:15:43 [4599ac310b99703407600bc8bfa58ddb80da7be3d613b49fdf75691b99d293e0]
2023-12-26 11:22:08,898  INFO Keeping archive (rule: secondly #4):     linbox_2023-12-26_11:11:35           Tue, 2023-12-26 11:11:35 [079e9c226455ff1b816be986bf49029c3cdf28ec04e9f6bf2d387ea9a4f24d87]
2023-12-26 11:22:08,969  INFO Updated state file /var/log/borgctl/borg_state_default_prune.txt


2023-12-26 11:22:08,970  INFO Running 'borg compact' in --cron mode
2023-12-26 11:22:08,970  INFO Executing: BORG_REPO="/root/borg-repo" BORG_LOGGING_CONF="/etc/borgctl/logging.conf" BORG_RSH="ssh -i /root/.ssh/borg_default" BORG_RELOCATED_REPO_ACCESS_IS_OK="yes" /usr/bin/borg --verbose compact
2023-12-26 11:22:09,459  INFO compaction freed about 1.48 kB repository space.
root@linbox:~ 
```

In the config file, you can specify which borg commands should be run if --cron is supplied:

```yaml
cron_commands:
- "create"
- "prune"
- "compact"
```

#### Monitoring borg: state files

bortctl also writes state files, if a borg command runs successfully. It contains the current date. You can use it for monitoring. State files are written to the log directory. The format is`borg_state__$config_file_prefix_$borg_command.txt`. In the config file you can specify a list of commands for which a state file should be created.

```yaml
state_commands:
- "create"
- "prune"
```

```bash
root@linbox:~ cat /var/log/borgctl/borg_state_default_create.txt 
2023-12-26_11:22:08
```

### borg passphrase: ask vs ask-always
If you don't want to keep your borg passphrase on your disk, you can use `ask` or `ask-always`. If you specify `ask` in your config file as passphrase, you will be ask during runtime for the passphrase. The difference between `ask` and `ask-always`: That's interesting if you run borgctl with multiple config files and different configurations. You get always asked for the password if you specify `ask-always`. If you run borgctl with three config files and every config file has `ask` specified, it only asks you for the first run. Then, it uses the previously entered password.

### Misc

In config file, you can specify the borg binary (borg_binary) used for invocation. You can also add environment variables. If you need help for a borg command, you can just add `help` (like `borgctl list help`). You can change default arguments for specific borg commands by adding/modifying `borg_$command_arguments` in the config file (like `borg_create_arguments`).
