from pathlib import Path
import argparse
import subprocess
import sys
import logging
import logging.config
from typing import Any, Tuple, NoReturn

from borgctl.utils import write_state_file, get_conf_directory, \
    load_config, BORG_COMMANDS, fail, get_new_archive_name, \
    print_docs_url, ask_for_passphrase, ask_for_new_passphrase, \
    init_logging, prepare_config_files

from borgctl.helper import get_version, show_config_files, \
    generate_ssh_key, generate_authorized_keys, generate_default_config, \
    generate_new_passphrase


def execute_borg(cmd: list[str], env: dict[str, str]) -> int:
    debug_out = " ".join([f"{key}=\"{value}\"" for key, value in env.items() if key not in ("BORG_PASSPHRASE", "BORG_NEW_PASSPHRASE")])
    debug_out += " " + " ".join(cmd)
    logging.info(f"Executing: {debug_out}")

    with subprocess.Popen(cmd, env=env, bufsize=1,
                          stdout=sys.stdout, stderr=sys.stdout) as p:
        p.wait()
        if p.returncode == 1:
            logging.warning(f"borg exited with warnings (exit code {p.returncode})")
        elif p.returncode > 1:
            logging.error(f"borg failed with exit code {p.returncode}")
        return p.returncode


def run_borg_command(command: str, env: dict[str, str], config: dict[str, Any], config_file: Path, args: list[str]) -> int:

    env = ask_for_passphrase(config, env, command, config_file, args)
    cmd = [config["borg_binary"], "--verbose", command]

    if command in ("check", "create", "compact"):
        cmd.append("--progress")
    if command in ("create"):
        cmd.append("--stats")
    if command in ("prune", ):
        cmd.append("--list")

    if command == "import-tar":
        cmd.append(get_new_archive_name(config))
    elif command in ("config", "init", "with-lock"):
        cmd.append(config["repository"])
    elif command == "key" and "change-passphrase" in args:
        env = ask_for_new_passphrase(config, env, config_file)
    elif command == "create":
        args = prepare_borg_create(config, args)
    elif command == "umount":
        if len(args) == 0:
            mount_point = Path(config["mount_point"]).expanduser().as_posix()
            cmd.append(mount_point)
    elif command == "mount" and len(args) == 0:
        # no argument: add :: and mount point to mount all archives
        if len(args) == 0:
            cmd.append("::")
            mount_point = Path(config["mount_point"]).expanduser().as_posix()
            cmd.append(mount_point)
    elif command == "export-tar" and "--help" not in args:
        if len(args) < 2:
            fail("The export-tar command needs two arguments (plus optional parameters like --tar-filter): ::archive <outputfile>")
        if len(args) == 1:
            cmd.append("::")

    key_config_file = f"borg_{command}_arguments"
    if key_config_file in config:
        for argument in config[key_config_file]:
            # handle --keep-last 10 (vs --keep-last=10)
            for word in argument.split():
                cmd.append(word)

    for arg in args:
        cmd.append(arg)

    if command == "mount" and len(args) > 1:
        # we need mount after the user supplied options
        mount_point = Path(config["mount_point"]).expanduser().as_posix()
        cmd.append(mount_point)

    return_code = execute_borg(cmd, env)
    dry_run_or_help = "--dry-run" in cmd or "-s" in cmd or "--help" in cmd
    if return_code == 0 and not dry_run_or_help:
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


def run_cron_commands(config: dict[str, Any], env: dict[str, str], config_file: Path) -> int:
    return_code = 0
    for command in config["cron_commands"]:
        logging.info(f"Running 'borg {command}' in --cron mode")
        ret = run_borg_command(command, env, config, config_file, [])
        return_code = ret if ret > return_code else return_code
    logging.info(f"Returning with exit code {return_code} for 'borg --cron' with {config_file}")
    return return_code


def parse_arguments() -> Tuple[argparse.ArgumentParser, argparse.Namespace, list[str]]:

    description = (f"borgctl is a simple borgbackup wrapper. Running version {get_version()}.\n\n"
                   "The working directory is /etc/borgctl/ "
                   "for root or $XDG_CONFIG_HOME/borgctl or ~/.config/borgctl for non-root users.\n"
                   "The log directory is /var/log/borgctl/ for root or $XDG_STATE_HOME/borgctl or "
                   "~/.local/state/borgctl for non-root users.")
    parser = argparse.ArgumentParser(description=description,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-l", "--list",
                        nargs='?',
                        const="*.yml",
                        help=f"list existing borgctl config files in {get_conf_directory()}")
    parser.add_argument("-d", "--generate-default-config",
                        action="store_true",
                        help=f"write default config to {get_conf_directory()}/default.yml or "
                              "prints it to stdout if the file already exists")
    parser.add_argument("-s", "--generate-ssh-key",
                        action="store_true",
                        help="write a new ed25519 ssh key to ~/.ssh/borg_$config and update the config file")
    parser.add_argument("-a", "--generate-authorized-keys",
                        action="store_true",
                        help="print the authorized_keys entry. It also shows the retricted entry")
    parser.add_argument("-c", "--config",
                        action="append",
                        help="specify the config file to use. Defaults to default.yml. "
                             "You can specify multiple config files with -c default.yml -c "
                             "local-disk.yml. If the config file contains a /, then a relative/absolute "
                             f"path is asumed. If not, {get_conf_directory()}/$config will be used")
    parser.add_argument("--cron",
                        action="store_true",
                        help="run multiple borg commands in a row. The commands to run are specified in the config file (cron_commands)")
    parser.add_argument("-p", "--generate-passphrase",
                        action="store_true",
                        help="generate a diceware like passphrase")
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
    return parser, args, borg_cli_arguments


def main() -> NoReturn:
    parser, args, borg_cli_arguments = parse_arguments()
    init_logging()
    if args.generate_default_config:
        generate_default_config()
    elif args.list:
        show_config_files(args.list)
    elif args.generate_passphrase:
        generate_new_passphrase()
    elif args.version:
        print(f"borgctl v{get_version()}")
        sys.exit(0)

    return_code = 0

    try:
        config_files = prepare_config_files(args.config)
        for config_file in config_files:
            env, config = load_config(config_file)

            if args.generate_ssh_key:
                generate_ssh_key(config, config_file)
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
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        logging.error("Oh no an exception occured")
        logging.error("Please report it: https://github.com/kmille/borgctl/issues")
        logging.error(traceback.format_exc())
        fail(e)
    finally:
        sys.exit(return_code)


if __name__ == '__main__':
    main()
