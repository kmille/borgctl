import os
from pathlib import Path
import datetime
import sys
from ruamel.yaml import YAML, YAMLError  # type: ignore
import logging
from getpass import getpass
from typing import Tuple, NoReturn, Any


BORG_COMMANDS = [
    'break-lock', 'check', 'compact', 'config', 'create', 'delete',
    'diff', 'extract', 'export-tar', 'import-tar', 'info', 'init',
    'key', 'list', 'mount', 'prune', 'rename', 'umount', 'upgrade', 'with-lock'
]

remembered_passphrase = ""


def fail(msg: str | Exception, code: int = 1) -> NoReturn:
    logging.error(msg)
    sys.exit(code)


def get_log_directory() -> Path:
    # https://specifications.freedesktop.org/basedir-spec/latest/ar01s03.html
    if os.getuid() == 0:
        log_dir = Path("/var/log/borgctl/")
    else:
        if "XDG_STATE_HOME" in os.environ:
            log_dir = Path(os.environ["XDG_STATE_HOME"]).expanduser() / "borgctl"
        else:
            log_dir = Path("~/.local/state/borgctl").expanduser()
    if not log_dir.exists():
        log_dir.mkdir(parents=True)
    return log_dir


def init_logging() -> None:
    config_file = get_conf_directory() / "logging.conf"
    if not config_file.exists():
        write_logging_config()
    logging.config.fileConfig(config_file)


def get_conf_directory() -> Path:
    # https://specifications.freedesktop.org/basedir-spec/latest/ar01s03.html
    if os.getuid() == 0:
        conf_dir = Path("/etc/borgctl/")
    else:
        if "XDG_CONFIG_HOME" in os.environ:
            conf_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "borgctl"
        else:
            conf_dir = Path("~/.config/borgctl").expanduser()
    if not conf_dir.exists():
        conf_dir.mkdir(parents=True)
    return conf_dir


def write_state_file(config: dict[str, Any], config_file: Path, command: str) -> None:
    if command not in config["state_commands"]:
        return
    log_dir = get_log_directory()
    config_prefix = config_file.stem
    state_file = log_dir / f"borg_state_{config_prefix}_{command}.txt"
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    state_file.write_text(now)
    logging.info(f"Updated state file {state_file}")


def check_config(config: dict[str, Any]) -> None:
    config_keys = ['repository', 'ssh_key', 'prefix', 'passphrase', 'mount_point', 'borg_create_backup_dirs',
                   'borg_create_excludes', 'envs', 'borg_binary', 'cron_commands', 'state_commands']
    for config_key in config_keys:
        if config_key not in config:
            fail(f"'{config_key}' not specified in config file")

    if type(config["borg_create_backup_dirs"]) is not list:
        fail("'borg_create_backup_dirs' in config file is not a list")
    if type(config["borg_create_excludes"]) is not list:
        fail("'borg_create_excludes' in config file is not a list")
    if type(config["cron_commands"]) is not list:
        fail("'cron_commands' in config file is not a list")
    if type(config["state_commands"]) is not list:
        fail("'state_commands' in config file is not a list")
    for key in ["cron_commands", "state_commands"]:
        for command in config[key]:
            if command not in BORG_COMMANDS:
                fail(f"'{command}' in '{key}' is not a valid borg command")

    for command in BORG_COMMANDS:
        config_key = f"borg_{command}_arguments"
        if config_key in config:
            if type(config[config_key]) is not list:
                fail(f"'{config_key}' in config file is not a list")

    if config["prefix"].strip() == "":
        fail("The prefix is empty. Must be set.")

    if config["repository"].strip() == "":
        fail("The repository is empty. Must be set.")

    binary = Path(config["borg_binary"])
    if not binary.exists():
        fail(f"borg executable not found (specified in config file): {binary}")

    if type(config["envs"]) is not dict:
        fail("'envs' in config file is not a dictionary")


def load_config(config_file: Path) -> Tuple[dict[str, str], dict[str, Any]]:
    def setup_env():
        env = {
            "BORG_PASSPHRASE": config["passphrase"],
            "BORG_REPO": config["repository"],
            "BORG_LOGGING_CONF": (get_conf_directory() / "logging.conf").as_posix(),
        }
        if config["ssh_key"] != "":
            env.update({
                "BORG_RSH": f"ssh -i {config['ssh_key']}",
            })
            if "BORG_RSH" in config["envs"]:
                fail("Specifying ssh_key and BORG_RSH clashes. Not supported. Could not apply your BORG_RSH. "
                     "Please clear ssh_key in the config and specify the ssh key via BORG_RSH (add -i <path ssh key>)")
        env.update(config["envs"])
        return env

    logging.info(f"\aUsing config file {config_file}")
    if not config_file.exists():
        fail(f"Could not load config. File {config_file} does not exist. Please use --list to list "
             "all config files or --generate-default-config to create a default config")

    yaml = YAML(typ="safe")
    try:
        config = yaml.load(config_file)
        if not config:
            raise YAMLError("File is empty")
    except YAMLError as e:
        fail(f"Could not parse yaml in '{config_file}': {e}")

    check_config(config)
    env = setup_env()
    return env, config


def write_logging_config() -> None:

    log_file = get_log_directory() / "borg.log"
    logging_config = f"""[loggers]
keys=root

[handlers]
keys=console,logfile

[formatters]
keys=simple

[logger_root]
level=NOTSET
handlers=console,logfile

[handler_logfile]
class=handlers.RotatingFileHandler
level=INFO
formatter=simple
args=('{log_file}', 'a',  1024**3, 1)

[handler_console]
class=StreamHandler
formatter=simple
level=INFO
args=(sys.stderr,)

[formatter_simple]
format=%(asctime)s %(levelname)s %(message)s
datefmt=
class=logging.Formatter"""

    log_conf_file = get_conf_directory() / "logging.conf"
    log_conf_file.write_text(logging_config)
    print(f"Wrote logging configuration to {log_conf_file}")


def get_new_archive_name(config: dict[str, Any]) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    archive = "::" + config["prefix"] + "_" + now
    return archive


def print_docs_url(command: str) -> None:
    if command == "import-tar":
        url = "https://borgbackup.readthedocs.io/en/stable/usage/tar.html#borg-import-tar"
    elif command == "export-tar":
        url = "https://borgbackup.readthedocs.io/en/stable/usage/tar.html#borg-export-tar"
    elif command == "break-lock":
        url = "https://borgbackup.readthedocs.io/en/stable/usage/lock.html#borg-break-lock"
    else:
        url = f"https://borgbackup.readthedocs.io/en/stable/usage/{command}.html"
    print(f"Check out the docs: {url}")


def ask_for_passphrase(config: dict[str, Any], env: dict[str, str], command: str, config_file: Path, args: list[str]) -> dict[str, str]:
    is_help = "--help" in args
    if is_help or config["passphrase"] not in ("ask", "ask-always"):
        return env

    is_repo_check = command == "check" and "--repository-only" in args
    if command in ["compact", "umount"] or is_repo_check:
        # no password needed, see https://github.com/borgbackup/borg/discussions/8015
        return env

    global remembered_passphrase

    if config["passphrase"] == "ask" and remembered_passphrase != "":
        passphrase = remembered_passphrase
        logging.info("Using previously entered password")
    else:
        if command == "init":
            return ask_for_new_passphrase(config, env, config_file)
        else:
            passphrase = getpass(f"Please enter the borg passphrase for {config['repository']}: ")
            remembered_passphrase = passphrase

    env.update({"BORG_PASSPHRASE": passphrase})
    return env


def update_config_passphrase(passphrase: str, config_file: Path) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    try:
        config = yaml.load(config_file)
    except YAMLError as e:
        fail(f"Could not parse yaml in {config_file}: {e}")

    if config["passphrase"] in ("ask", "ask-always"):
        logging.warning("Not updating passphrase in config file: (ask/ask-always) is used")
        return

    config["passphrase"] = passphrase
    try:
        yaml.dump(config, config_file)
    except YAMLError as e:
        fail(f"Could not parse yaml in {config_file}: {e}")
    logging.info(f"Updated passphrase in {config_file}")


def ask_for_new_passphrase(config: dict[str, Any], env: dict[str, str], config_file: Path) -> dict[str, str] | NoReturn:
    passphrase1 = getpass(f"Please enter the new borg passphrase for repository {config['repository']}:")
    passphrase2 = getpass(f"Please re-enter the new borg passphrase for repository {config['repository']}:")
    if passphrase1 != passphrase2:
        fail("Passphrase missmatch")

    env.update({"BORG_NEW_PASSPHRASE": passphrase1})
    update_config_passphrase(passphrase1, config_file)
    return env


def update_config_sshkey(ssh_key_location: str, config_file: Path) -> None:
    try:
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.preserve_quotes = True
        config = yaml.load(config_file)
        if config["ssh_key"] != ssh_key_location:
            config["ssh_key"] = ssh_key_location
            yaml.dump(config, config_file)
            logging.info(f"Updated ssh_key in {config_file}")
    except YAMLError as e:
        fail(f"Could not parse yaml in {config_file}: {e}")


def prepare_config_files(cli_config: list | None) -> list[Path]:
    cli_config_files = ["default.yml", ] if not cli_config else cli_config
    existing_config_files = []

    for config_file in cli_config_files:
        if "/" in config_file:
            config_file = Path(config_file).expanduser()
        else:
            config_file = (get_conf_directory() / config_file).expanduser()
        if not config_file.exists():
            fail(f"Could not load config '{config_file}'. File does not exist.")
        existing_config_files.append(config_file)
    return existing_config_files
