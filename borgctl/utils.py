import os
from pathlib import Path
import datetime
import sys
from ruamel.yaml import YAML, YAMLError

BORG_COMMANDS = [
    "list", "create", "check", "compact", "prune", "mount", "umount", "init", "break-lock", "info",
]


def fail(msg: str, code: int = 1):
    print(f"Error: {msg}")
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


def write_state_file(config: dict, config_file: str, command: str):
    if command not in config["state_commands"]:
        return
    log_dir = get_log_directory()
    config_prefix = Path(config_file).stem
    state_file = log_dir / f"borg_state_{config_prefix}_{command}.txt"
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    state_file.write_text(now)
    print(f"Updated state file {state_file}")


def check_config(config: dict):
    config_keys = ['repository', 'ssh_key', 'prefix', 'passphrase', 'mount_point', 'borg_create_backup_dirs', 'borg_create_excludes', 'borg_create_arguments', 'borg_prune_arguments', 'borg_init_arguments', 'envs', 'borg_binary', 'cron_commands', 'state_commands']
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
        fail(f"Warning: borg executable not found (specified in config file): {binary}")

    if type(config["envs"]) is not dict:
        fail("'envs' in config file is not a dictionary")
    # TODO: check envs


def load_config(config_file: Path):
    print(f"Using config file {config_file}")
    if not config_file.exists():
        fail(f"Could not load config file {config_file}\nPlease use --generate-default-config to create a default config")

    yaml = YAML(typ="safe")
    # TODO: do we need this?
    #yaml.preserve_quotes = True
    #yaml.default_flow_style = False
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

    # TODO: only if ssh_key is not empty
    if config["envs"]:
        env.update(config["envs"])

    if "BORG_RSH" in env:
        fail("Could not set ssh key... you have to manually set it vai RSH")

    if config["ssh_key"] != "":
        env.update({
            "BORG_RSH": f"ssh -i {config['ssh_key']}",
        })
    #for e in y["envs"]:
    #e.update(

    return env, config


def write_logging_config():

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
args=(sys.stdout,)

[formatter_simple]
format=%(asctime)s %(levelname)s %(message)s
datefmt=
class=logging.Formatter"""

    logging_file_location = get_conf_directory() / "logging.conf"

    if not logging_file_location.exists():
        logging_file_location.write_text(logging_config)
