import sys
from pathlib import Path
import subprocess
import logging
from ruamel.yaml import YAML
import socket
import os


from typing import NoReturn, Tuple, Any
from borgctl.utils import fail, get_conf_directory, update_config_sshkey
from borgctl.wordlist import get_passphrase


def show_version() -> NoReturn:
    from importlib.metadata import version
    package = "borgctl"
    print(f"Running {package} {version(package)}")
    sys.exit(0)


def show_config_files() -> NoReturn:
    config_dir = get_conf_directory()
    for file in config_dir.glob("*.yml"):
        print(file.name)
    sys.exit(0)


def generate_ssh_key(out_file: Path) -> None:
    hostname = socket.gethostname()
    user = os.getlogin()
    key = out_file.name
    comment = f"{user}_{key}@{hostname}"
    cmd = ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", out_file.as_posix(), "-C", comment]
    logging.info(f"Running {cmd}")
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        fail(f"Could not create ssh-key: {e.stderr.decode()}", e.returncode)
    logging.info(f"Successfully created ssh key {out_file}")


def handle_ssh_key(config: dict[str, Any], config_file: Path) -> NoReturn:
    if config["ssh_key"] == "":
        ssh_key_location = Path(f"~/.ssh/borg_{config_file.stem}").expanduser()
    else:
        ssh_key_location = Path(config["ssh_key"]).expanduser()

    if not ssh_key_location.exists():
        generate_ssh_key(ssh_key_location)
    else:
        logging.warning(f"ssh key {ssh_key_location} already exists. Not overwriting")
    update_config_sshkey(ssh_key_location.as_posix(), config_file)
    sys.exit(0)


def parse_borg_repository(repository: str) -> Tuple[str, str | None, str | None]:
    host = repo_dir = None
    user = os.getlogin()
    if repository.strip().startswith("ssh://"):
        repository = repository.replace("ssh://", "")
    if repository.count(":") != 1:
        logging.warning(f"The repository '{repository}' specified in the config file does not use ssh")
    else:
        host, repo_dir = repository.split(":")
        if "@" in host:
            user, host = host.split("@")
    return user, host, repo_dir


def generate_authorized_keys(config: dict[str, Any]) -> NoReturn:
    ssh_key = config["ssh_key"]
    if ssh_key == "":
        fail("No ssh key was specified in the config file. Use --generate-ssh-key to generate one")

    ssh_pub_key = Path(f"{ssh_key}.pub").expanduser()
    if not ssh_pub_key.exists():
        fail(f"The ssh_key ('{ssh_pub_key}') specified in the config file does not exist")

    user, host, repo_dir = parse_borg_repository(config["repository"])

    logging.info(f"Using ssh key {ssh_pub_key} from config file")
    pub_key = ssh_pub_key.read_text().strip()
    logging.info(f"Add this line to authorized_keys:\n{pub_key}\n")

    if repo_dir:
        restricted = f"""command="borg serve --restrict-to-path {repo_dir}",restrict {pub_key}"""
        logging.info(f"Use this line for restricted access:\n{restricted}\n")
        logging.warning("Please note that you have to initalize a repository with 'borg init --append-only'. "
                        "Using 'borg serve --append-only' is not enough. Use 'borg config' to check.")
        try:
            user_home_dir = Path(f"~{user}").expanduser().as_posix()
        except RuntimeError:
            user_home_dir = f"/home/{user}"

        remote_authorized_keys = user_home_dir + "/.ssh/authorized_keys"
        remote_command = f"""echo -e '{restricted}\\n' | ssh {host} 'cat >> {remote_authorized_keys}'"""
        logging.info(f"You can try this all-in-one command:\n{remote_command}")
    sys.exit(0)


def generate_default_config() -> None:
    config_template = Path(__file__).parent / "default.yml.template"
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    y = yaml.load(config_template)
    y["prefix"] = socket.gethostname()
    y["passphrase"] = get_passphrase()
    y["borg_prune_arguments"].append(f"--prefix {y['prefix']}")

    default_config = get_conf_directory() / "default.yml"
    logging.warning("IMPORTANT! Make a backup of the passphrase!")
    if default_config.exists():
        logging.warning(f"{default_config} already exists. Not overwriting. "
                        "Please create a new config file by redirecting this output to"
                        f"{get_conf_directory()}/something.yml (this line is printed to stderr)")
        yaml.dump(y, sys.stdout)
    else:
        yaml.dump(y, default_config)
        default_config.chmod(0o600)
        logging.info(f"Successfully wrote config file to {default_config}")
    sys.exit(0)
