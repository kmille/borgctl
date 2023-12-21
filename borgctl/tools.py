import sys
from pathlib import Path
import subprocess
from ruamel.yaml import YAML, YAMLError
import socket
import os


from typing import NoReturn
from borgctl.utils import fail, get_conf_directory
from borgctl.wordlist import get_passphrase


def show_version() -> NoReturn:
    from importlib.metadata import version
    package = "borgctl"
    print(f"Running {package} {version(package)}")
    sys.exit(0)


def update_config(ssh_key_location: str, config_file: Path) -> None:
    try:
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.preserve_quotes = True
        config = yaml.load(config_file)
        if config["ssh_key"] != ssh_key_location:
            config["ssh_key"] = ssh_key_location
            yaml.dump(config, config_file)
            print(f"Updated ssh_key in {config_file}")
    except YAMLError as e:
        fail(f"Could not parse yaml in {config_file}: {e}")


def generate_ssh_key(out_file: Path) -> None:
    hostname = socket.gethostname()
    user = os.getlogin()
    key = out_file.name
    comment = f"{user}_{key}@{hostname}"
    cmd = ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", out_file.as_posix(), "-C", comment]
    print(f"Running {cmd}")
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        fail(f"Could not create ssh-key: {e.stderr.decode()}", e.returncode)
    print(f"Successfully created ssh key {out_file}")


def handle_ssh_key(config: dict, config_file: Path) -> NoReturn:
    if config["ssh_key"] == "":
        ssh_key_location = Path(f"~/.ssh/borg_{config_file.stem}").expanduser()
    else:
        ssh_key_location = Path(config["ssh_key"]).expanduser()

    if not ssh_key_location.exists():
        generate_ssh_key(ssh_key_location)
        #generate_authorized_keys(config)
    else:
        print(f"Warning: ssh key {ssh_key_location} already exists. Not overwriting")
    update_config(ssh_key_location.as_posix(), config_file)
    sys.exit(0)


def parse_borg_repository(repository: str):
    host = repo_dir = None
    user = os.getlogin()
    if repository.strip().startswith("ssh://"):
        repository = repository.replace("ssh://", "")
    if repository.count(":") != 1:
        print(f"Warning: The repository '{repository}' specified in the config file does not use ssh")
    else:
        host, repo_dir = repository.split(":")
        if "@" in host:
            user, host = host.split("@")
    return user, host, repo_dir


#print(parse_borg_repository("ssh://userr@hostt:/opt/backup"))
#print(parse_borg_repository("ssh://userr@hostt:/opt/backup"))


def generate_authorized_keys(config: dict) -> NoReturn:
    ssh_key = config["ssh_key"]
    if ssh_key == "":
        fail("No ssh key was specified in the config file. Use --generate-ssh-key to generate one")

    ssh_pub_key = Path(f"{ssh_key}.pub").expanduser()
    if not ssh_pub_key.exists():
        fail(f"The ssh_key ('{ssh_pub_key}') specified in the config file does not exist")

    user, host, repo_dir = parse_borg_repository(config["repository"])

    print(f"Using ssh key {ssh_pub_key} from config file")
    pub_key = ssh_pub_key.read_text().strip()
    print(f"Add this line to authorized_keys:\n{pub_key}")

    if repo_dir:
        restricted = f"""command="borg serve --restrict-to-path {repo_dir}",restrict {pub_key}"""
        print(f"\nUse this line for restricted access:\n{restricted}")
        #print("Also useful in 'borg serve' is --append-only and --storage-quota")

        remote_authorized_keys = Path(f"~{user}").expanduser().as_posix() + "/.ssh/authorized_keys"
        remote_command = f"""echo -e '{restricted}\\n' | ssh {host} 'cat >> {remote_authorized_keys}'"""
        print(f"\nOr this one-in-all command:\n{remote_command}")
    sys.exit(0)


def generate_default_config():
    config_template = Path(__file__).parent / "default.yml.template"
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.preserve_quotes = True
    y = yaml.load(config_template)
    y["prefix"] = socket.gethostname()
    passphrase = get_passphrase()
    y["passphrase"] = passphrase

    default_config = get_conf_directory() / "default.yml"
    print(f"Please make a backup of the passphrase: {passphrase}", file=sys.stderr)
    if default_config.exists():
        print(f"Warning: {default_config} already exists. Not overwriting.", file=sys.stderr)
        print("Please create a new config file by redirecting this output to",
              f"{get_conf_directory()}/something.yml (this line printed to stderr)",
              file=sys.stderr)
        yaml.dump(y, sys.stdout)
    else:
        yaml.dump(y, default_config)
        default_config.chmod(0o600)
        print(f"Successfully wrote config file to {default_config}")
    sys.exit(0)
