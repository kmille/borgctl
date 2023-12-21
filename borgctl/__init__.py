from pathlib import Path
import argparse
import subprocess
import sys
import datetime
from getpass import getpass

from borgctl.utils import write_state_file, get_conf_directory, \
    load_config, BORG_COMMANDS, fail, write_logging_config

from borgctl.tools import show_version, handle_ssh_key, generate_authorized_keys, generate_default_config


#logger = None
#file_logger = None


#def init_logging(config_file: str):
#    global logger, file_logger
#    logger = logging.getLogger("console")
#    logger.setLevel(logging.INFO)
#    logger.addHandler(logging.StreamHandler(sys.stderr))
#
#    config_prefix = Path(config_file).stem
#    # TODO: rotate files
#    file_logger = logging.getLogger("file")
#    file_logger.setLevel(logging.INFO)
#    file_handler = logging.FileHandler(get_log_directory() / (config_prefix + "_borg.log"))
#    logger.addHandler(file_handler)
#    #file_logger.addHandler(file_handler)
#
#    #logger.info("hi")
#    #logger.warning("hi")


def execute_borg(cmd: list[str], env: dict) -> int:
    #debug_out = " ".join([f"{key}={value}" for key, value in env.items() if key != "BORG_PASSPHRASE"])
    debug_out = " ".join([f"{key}=\"{value}\"" for key, value in env.items()])
    debug_out += " " + " ".join(cmd)
    print(f"Executing: {debug_out}")

    #try:
    #p = subprocess.run(cmd, capture_output=True, env=env, check=True)
    # # info prints to stdout else stderr?
    #if p.stderr.decode() != "":
    #    print(p.stderr.decode())
    #if p.stdout.decode() != "":
    #    print(p.stdout.decode())

    #cmd = "while true; do echo hi >&2; sleep 1; done"
    #cmd = "while true; do echo hi; sleep 1; done"
    # was hier geht: stderr=sys.stdout
    # heißt der ganze shizzle geht mit stdout, aber nicht mit stderr
    # https://stackoverflow.com/questions/4417546/constantly-print-subprocess-output-while-process-is-running
    #with subprocess.Popen(cmd, env=env, bufsize=1,
    #stdout=sys.stdout, universal_newlines=True,
    with subprocess.Popen(cmd, env=env, bufsize=1,
                          stdout=sys.stdout, stderr=sys.stdout) as p:
        #for line in p.stdout:
        #    print(line, end="")
        #for line in p.stderr:
        #    print(line, end="")
        p.wait()
        if p.returncode != 0:
            print(f"borg failed with exit code: {p.returncode}")
        return p.returncode

    #except subprocess.CalledProcessError as e:
    #    print(f"borg failed with exit code: {e.returncode}: {e.stderr}")
    #    print(e)
    #    print(f"Check out the docs: https://borgbackup.readthedocs.io/en/stable/usage/{cmd[2]}.html")
    #    sys.exit(e.returncode)


def run_borg_command(command: str, env: dict[str, str], config: dict, args: list[str]):
    cmd = [config["borg_binary"], "--verbose", command]
    if command == "create":
        args = prepare_borg_create(config, args)

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

    if "mount" in command:
        cmd.append(config["mount_point"])
        if len(args) == 0 and command == "mount":
            cmd.append("::")
    elif command == "init":
        cmd.append(config["repository"])

    return execute_borg(cmd, env)


def prepare_borg_create(config: dict, cli_arguments: list[str]) -> list[str]:
    arguments = []

    for exclude in config["borg_create_excludes"]:
        p = Path(exclude).expanduser()
        arguments.append(f"--exclude={p.as_posix()}")

    now = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    archive = "::" + config["prefix"] + "_" + now
    arguments.append(archive)

    for backup_dir in config["borg_create_backup_dirs"]:
        p = Path(backup_dir).expanduser()
        arguments.append(p.as_posix())
        if not p.exists():
            print(f"Warning: backup directory {p} does not exist")

    arguments.extend(cli_arguments)

    return arguments


def run_cron_commands(config: dict, env: dict, config_file: str):
    return_code = 0
    for command in config["cron_commands"]:
        print(f"Running borg {command} in --cron mode")
        ret = run_borg_command(command, env, config, [])
        if ret == 0:
            write_state_file(config, config_file, command)
        if ret > return_code:
            return_code = ret
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

    if args.generate_default_config:
        generate_default_config()
    elif args.version:
        show_version()

    #init_logging(args.config)
    write_logging_config()
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
                run_borg_command(args.command, env, config, ["--help", ])
                print(f"Check out the docs: https://borgbackup.readthedocs.io/en/stable/usage/{args.command}.html")
                sys.exit(0)
            elif args.command:
                ret = run_borg_command(args.command, env, config, borg_cli_arguments)
                if ret == 0:
                    write_state_file(config, config_file, args.command)
                if ret > return_code:
                    return_code = ret
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
