from pathlib import Path
import argparse
import subprocess
import sys
from getpass import getpass
import logging
import logging.config

from borgctl.utils import write_state_file, get_conf_directory, \
    load_config, BORG_COMMANDS, fail, write_logging_config, get_new_archive_name

from borgctl.tools import show_version, handle_ssh_key, generate_authorized_keys, generate_default_config


def init_logging():
    config_file = get_conf_directory() / "logging.conf"
    if not config_file.exists():
        write_logging_config()
    logging.config.fileConfig(config_file)


def execute_borg(cmd: list[str], env: dict) -> int:
    debug_out = " ".join([f"{key}=\"{value}\"" for key, value in env.items() if key != "BORG_PASSPHRASE"])
    debug_out += " " + " ".join(cmd)
    logging.info(f"Executing: {debug_out}")

    with subprocess.Popen(cmd, env=env, bufsize=1,
                          stdout=sys.stdout, stderr=sys.stdout) as p:
        p.wait()
        if p.returncode != 0:
            logging.error(f"borg failed with exit code: {p.returncode}")
        return p.returncode


def run_borg_command(command: str, env: dict[str, str], config: dict, config_file: str, args: list[str]):
    cmd = [config["borg_binary"], "--verbose", command]
    if command == "create":
        args = prepare_borg_create(config, args)
    elif command == "import-tar":
        cmd.append(get_new_archive_name(config))
    elif command == "config":
        cmd.append(config["repository"])

    key_config_file = f"borg_{command}_arguments"
    if key_config_file in config:
        for argument in config[key_config_file]:
            # handle --keep-last 10 (vs --keep-last=10)
            for word in argument.split():
                cmd.append(word)

    if config["passphrase"] == "ask":
        passphrase = getpass(f"\aPlease enter the borg passphrase for {config['repository']}: ")
        env.update({"BORG_PASSPHRASE": passphrase})

    for arg in args:
        if arg.startswith("-"):
            cmd.append(arg)
    for arg in args:
        if not arg.startswith("-"):
            cmd.append(arg)

    if command == "umount":
        if len(args) == 0:
            mount_point = Path(config["mount_point"]).expanduser().as_posix()
            cmd.append(mount_point)
    elif command == "mount":
        if len(args) == 0:
            # just mount: add :: (latest archive) and mount point
            cmd.append("::")
            mount_point = Path(config["mount_point"]).expanduser().as_posix()
            cmd.append(mount_point)
        elif len(args) == 1:
            # mount ::archive: only add mount point
            mount_point = Path(config["mount_point"]).expanduser().as_posix()
            cmd.append(mount_point)
    elif command == "init":
        cmd.append(config["repository"])
    elif command == "export-tar":
        if len(args) < 2:
            fail("The export-tar command needs two arguments (plus optional parameters like --tar-filter): ::archive <outputfile>")
        if len(args) == 1:
            cmd.append("::")

    return_code = execute_borg(cmd, env)
    if return_code == 0 and not ("--dry-run" in cmd or "-s" in cmd or "--help" in cmd):
        write_state_file(config, config_file, command)
    return return_code


def prepare_borg_create(config: dict, cli_arguments: list[str]) -> list[str]:
    arguments = []

    for exclude in config["borg_create_excludes"]:
        p = Path(exclude).expanduser()
        arguments.append(f"--exclude={p.as_posix()}")
    arguments.append(get_new_archive_name(config))

    for backup_dir in config["borg_create_backup_dirs"]:
        p = Path(backup_dir).expanduser()
        arguments.append(p.as_posix())
        if not p.exists():
            logging.warning(f"Backup directory {p} does not exist")

    arguments.extend(cli_arguments)

    return arguments


def run_cron_commands(config: dict, env: dict, config_file: str):
    return_code = 0
    for command in config["cron_commands"]:
        logging.info(f"Running 'borg {command}' in --cron mode")
        ret = run_borg_command(command, env, config, config_file, [])
        if ret > return_code:
            return_code = ret
    if return_code != 0:
        logging.info(f"Returning with exit code {return_code}")
    sys.exit(return_code)


def main():
    description = """borgctl is a simple wrapper around borgbackup. The working directory is /etc/borgctl for root or XDG_CONFIG_HOME/borgctl or ~/.config/borgctl for non-root users.
The log directory is /var/log/borgctl/ for root or $XDG_STATE_HOME or ~/.local/state/borgctl for non-root users."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-d", "--generate-default-config",
                        action="store_true",
                        help="writes default config to $config_dir/default.yml or prints it to stdout if the file already exists")
    parser.add_argument("-s", "--generate-ssh-key",
                        action="store_true",
                        help="writes a new ed25519 ssh key to ~/.ssh/borg_$config and updates the config file")
    parser.add_argument("-a", "--generate-authorized_keys",
                        action="store_true",
                        help="prints the authorized_keys entry to stdout. You have to add it to the remote host (if you backup over ssh)")
    parser.add_argument("-c", "--config",
                        action="append",
                        help="specify the config file to you use. Defaults to default.yml. You can specify multiple config files with -c default.yml -c lokal-disk.yml. If the config file contains a / then a relative/absolute path is asumed. If not, $working_dir/$config will be used")
    parser.add_argument("--cron",
                        action="store_true",
                        help="run multiple borg commands in a row. The commands to run are specified in the config file (cron_commands)")
    parser.add_argument("--version",
                        action="store_true",
                        help="show version and exit")

    subparsers = parser.add_subparsers(dest='command')
    for command in BORG_COMMANDS:
        subparsers.add_parser(command)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args, borg_cli_arguments = parser.parse_known_args()

    init_logging()
    if args.generate_default_config:
        generate_default_config()
    elif args.version:
        show_version()

    args.config = ["default.yml", ] if not args.config else args.config

    return_code = 0
    try:
        for config_file in args.config:
            if "/" in args.config:
                config_file = Path(config_file).expanduser()
            else:
                config_file = (get_conf_directory() / config_file).expanduser()

            env, config = load_config(config_file)

            if args.generate_ssh_key:
                handle_ssh_key(config, config_file)
            elif args.generate_authorized_keys:
                generate_authorized_keys(config)
            elif args.cron:
                run_cron_commands(config, env, config_file)
            elif "help" in borg_cli_arguments:
                run_borg_command(args.command, env, config, config_file, ["--help", ])
                print(f"Check out the docs: https://borgbackup.readthedocs.io/en/stable/usage/{args.command}.html")
                sys.exit(0)
            elif args.command:
                ret = run_borg_command(args.command, env, config, config_file, borg_cli_arguments)
                if ret > return_code:
                    return_code = ret
            else:
                parser.print_help()
        sys.exit(return_code)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        fail(e)


if __name__ == '__main__':
    main()
