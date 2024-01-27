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


def get_version() -> str:
    from importlib.metadata import version
    return version("borgctl")


def show_config_files(config_filter: str) -> NoReturn:
    config_filter = f"*{config_filter}*" if config_filter != "*.yml" else config_filter
    config_dir = get_conf_directory()
    for file in sorted(config_dir.glob(config_filter)):
        print(file.name)
    sys.exit(0)


def run_ssh_key_gen(out_file: Path) -> None:
    user = os.getlogin()
    conf = out_file.name
    hostname = socket.gethostname()
    comment = f"{user}_{conf}@{hostname}"
    cmd = ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", out_file.as_posix(), "-C", comment]
    logging.info(f"Running {cmd}")
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        fail(f"Could not create ssh-key: {e.stderr.decode()}", e.returncode)
    logging.info(f"Successfully created ssh key {out_file}")


def generate_ssh_key(config: dict[str, Any], config_file: Path) -> NoReturn:
    if config["ssh_key"] == "":
        ssh_key_location = Path(f"~/.ssh/borg_{config_file.stem}").expanduser()
    else:
        ssh_key_location = Path(config["ssh_key"]).expanduser()

    if not ssh_key_location.exists():
        run_ssh_key_gen(ssh_key_location)
        if config["ssh_key"] == "":
            update_config_sshkey(ssh_key_location.as_posix(), config_file)
    else:
        logging.warning(f"ssh key {ssh_key_location} already exists. Not overwriting")

    sys.exit(0)


def parse_borg_repository(repository: str) -> Tuple[str, str | None, str | None]:
    user = os.getlogin()
    host = repo_dir = None
    if repository.strip().startswith("ssh://"):
        repository = repository.replace("ssh://", "")
    if repository.count(":") != 1:
        logging.warning(f"The repository '{repository}' does not use ssh")
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
        fail(f"The ssh_key ('{ssh_pub_key}') does not exist")

    user, host, repo_dir = parse_borg_repository(config["repository"])

    logging.info(f"Using ssh key {ssh_pub_key} from config file")
    pub_key = ssh_pub_key.read_text().strip()
    logging.info(f"Add this line to authorized_keys:\n{pub_key}")

    if repo_dir:
        restricted = f"""command="borg serve --restrict-to-path {repo_dir}",restrict {pub_key}"""
        print("", file=sys.stderr)
        logging.info(f"Use this line for restricted access:\n{restricted}\n")
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

    default_conf_file = get_conf_directory() / "default.yml"
    logging.warning("Plase make a backup of the passphrase. No passphrase, no restore!")
    if default_conf_file.exists():
        logging.warning(f"Config {default_conf_file} already exists. Not overwriting. "
                        "Please create a new config file by redirecting this output to"
                        f"{get_conf_directory()}/something.yml (this line is printed to stderr)")
        yaml.dump(y, sys.stdout)
    else:
        yaml.dump(y, default_conf_file)
        default_conf_file.chmod(0o600)
        logging.info(f"Successfully wrote config file to {default_conf_file}")
    sys.exit(0)


def generate_new_passphrase() -> None:
    print(get_passphrase())
    sys.exit(0)
