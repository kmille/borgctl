import os
from pathlib import Path
import datetime
import sys
from ruamel.yaml import YAML, YAMLError  # type: ignore
import logging
from getpass import getpass
from typing import Tuple, NoReturn, Any


BORG_COMMANDS = [
    'break-lock', 'check', 'compact', 'config', 'create',
    'delete', 'diff', 'export-tar', 'import-tar', 'info',
    'init', 'list', 'mount', 'prune', 'umount', 'upgrade'
]

remembered_password = ""


def fail(msg: str, code: int = 1) -> NoReturn:
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


def write_state_file(config: dict[str, Any], config_file: str, command: str) -> None:
    if command not in config["state_commands"]:
        return
    log_dir = get_log_directory()
    config_prefix = Path(config_file).stem
    state_file = log_dir / f"borg_state_{config_prefix}_{command}.txt"
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    state_file.write_text(now)
    logging.info(f"Updated state file {state_file}")


def check_config(config: dict[str, Any]) -> None:
    config_keys = ['repository', 'ssh_key', 'prefix', 'passphrase', 'mount_point', 'borg_create_backup_dirs', 'borg_create_excludes',
                   'borg_create_arguments', 'borg_prune_arguments', 'envs', 'borg_binary', 'cron_commands', 'state_commands']
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

    binary = Path(config["borg_binary"])
    if not binary.exists():
        fail(f"borg executable not found (specified in config file): {binary}")

    if type(config["envs"]) is not dict:
        fail("'envs' in config file is not a dictionary")


def load_config(config_file: Path) -> Tuple[dict[str, Any], dict[str, Any]]:
    logging.info(f"Using config file {config_file}")
    if not config_file.exists():
        fail(f"Could not load config file {config_file}\nPlease use --generate-default-config to create a default config")

    yaml = YAML(typ="safe")
    try:
        config = yaml.load(config_file)
    except YAMLError as e:
        fail(f"Could not parse yaml in {config_file}: {e}")

    check_config(config)

    repository = config["repository"]
    if repository.count(":") == 0:
        config["repository"] = Path(repository).expanduser().as_posix()
    env = {
        "BORG_PASSPHRASE": config["passphrase"],
        "BORG_REPO": config["repository"],
        "BORG_LOGGING_CONF": (get_conf_directory() / "logging.conf").as_posix(),
    }

    if config["ssh_key"] != "":
        env.update({
            "BORG_RSH": f"ssh -i {config['ssh_key']}",
        })
        if "BORG_RSH" in config["envs"] and "-i" not in config["envs"]["BORG_RSH"]:
            logging.warning("Could not set ssh key via BORG_RSH. You have to specify it manually it via RSH")
    env.update(config["envs"])

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

    logging_file_location = get_conf_directory() / "logging.conf"

    if not logging_file_location.exists():
        logging_file_location.write_text(logging_config)


def get_new_archive_name(config: dict[str, str]) -> str:
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


def handle_manual_passphrase(config: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
    """check if we need to ask the user for the passphrase"""

    if config["passphrase"] not in ("ask", "ask-always"):
        return env

    global remembered_password

    if config["passphrase"] == "ask" and remembered_password != "":
        passphrase = remembered_password
        logging.info("Using previously entered password")
    else:
        passphrase = getpass(f"\aPlease enter the borg passphrase for {config['repository']}: ")
        remembered_password = passphrase

    env.update({"BORG_PASSPHRASE": passphrase})
    return env
