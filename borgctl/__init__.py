from pathlib import Path
import argparse
import subprocess
import sys
import logging
import logging.config
from typing import Any

from borgctl.utils import write_state_file, get_conf_directory, \
    load_config, BORG_COMMANDS, fail, write_logging_config, get_new_archive_name, \
    print_docs_url, handle_manual_passphrase

from borgctl.tools import show_version, show_config_files, \
    handle_ssh_key, generate_authorized_keys, generate_default_config


def init_logging() -> None:
    config_file = get_conf_directory() / "logging.conf"
    if not config_file.exists():
        write_logging_config()
    logging.config.fileConfig(config_file)


def execute_borg(cmd: list[str], env: dict[str, str]) -> int:
    debug_out = " ".join([f"{key}=\"{value}\"" for key, value in env.items() if key != "BORG_PASSPHRASE"])
    debug_out += " " + " ".join(cmd)
    logging.info(f"Executing: {debug_out}")

    with subprocess.Popen(cmd, env=env, bufsize=1,
                          stdout=sys.stdout, stderr=sys.stdout) as p:
        p.wait()
        if p.returncode != 0:
            logging.error(f"borg failed with exit code: {p.returncode}")
        return p.returncode


def run_borg_command(command: str, env: dict[str, str], config: dict[str, Any], config_file: str, args: list[str]) -> int:

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

    env = handle_manual_passphrase(config, env)

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
    elif command == "export-tar" and "--help" not in args:
        if len(args) < 2:
            fail("The export-tar command needs two arguments (plus optional parameters like --tar-filter): ::archive <outputfile>")
        if len(args) == 1:
            cmd.append("::")

    return_code = execute_borg(cmd, env)
    if return_code == 0 and not ("--dry-run" in cmd or "-s" in cmd or "--help" in cmd):
        write_state_file(config, config_file, command)
    return return_code


def prepare_borg_create(config: dict[str, Any], cli_arguments: list[str]) -> list[str]:
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


def run_cron_commands(config: dict[str, Any], env: dict[str, str], config_file: str) -> int:
    return_code = 0
    for command in config["cron_commands"]:
        logging.info(f"Running 'borg {command}' in --cron mode")
        ret = run_borg_command(command, env, config, config_file, [])
        if ret > return_code:
            return_code = ret
    if return_code != 0:
        logging.info(f"Returning with exit code {return_code}")
    return return_code


def main() -> None:
    description = """borgctl is a simple borgbackup wrapper. The working directory is /etc/borgctl for root or XDG_CONFIG_HOME/borgctl or ~/.config/borgctl for non-root users.
The log directory is /var/log/borgctl/ for root or $XDG_STATE_HOME/borgctl or ~/.local/state/borgctl for non-root users."""
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
    parser.add_argument("-l", "--list",
                        action="store_true",
                        help="list borgctl config files in $config_dir")
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
    elif args.list:
        show_config_files()
    elif args.version:
        show_version()

    args.config = ["default.yml", ] if not args.config else args.config

    return_code = 0
    try:
        for config_file in args.config:
            if "/" in config_file:
                config_file = Path(config_file).expanduser()
            else:
                config_file = (get_conf_directory() / config_file).expanduser()
            env, config = load_config(config_file)

            if args.generate_ssh_key:
                handle_ssh_key(config, config_file)
            elif args.generate_authorized_keys:
                generate_authorized_keys(config)
            elif args.cron:
                ret = run_cron_commands(config, env, config_file)
                return_code = ret if ret > return_code else return_code
            elif "help" in borg_cli_arguments:
                run_borg_command(args.command, env, config, config_file, ["--help", ])
                print_docs_url(args.command)
                sys.exit(0)
            elif args.command:
                ret = run_borg_command(args.command, env, config, config_file, borg_cli_arguments)
                return_code = ret if ret > return_code else return_code
            else:
                parser.print_help()
        sys.exit(return_code)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise
        fail(e)


if __name__ == '__main__':
    main()
