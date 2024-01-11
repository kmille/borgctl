import pytest
from pathlib import Path
import tempfile
from shutil import rmtree
from ruamel.yaml import YAML
from json import loads


from borgctl.helper import generate_default_config
from borgctl import run_borg_command
import borgctl


BORG_PASSPHRASE = "123"
TEST_PREFIX = "borg-pytest-machine"


class TestRunBorg:

    def set_default_config(self):
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.preserve_quotes = True

        default_config = Path(borgctl.__file__).parent / "default.yml.template"
        config = yaml.load(default_config)
        self.config = config
        self.config["repository"] = self.repo.as_posix()
        self.config["borg_create_backup_dirs"] = [self.backup_files.as_posix(), ]
        self.config["prefix"] = TEST_PREFIX

        self.config_file = self.base_dir / "borg-test.yml"
        yaml.dump(config, self.config_file)

        self.env = {
            "BORG_PASSPHRASE": BORG_PASSPHRASE,
            "BORG_REPO": self.repo,
        }

    def init_directory_structure(self):
        self.base_dir = Path(tempfile.mkdtemp(prefix="borgctl_pytest"))
        self.repo = self.base_dir / "repo"
        self.backup_files = self.base_dir / "files_to_backup"
        self.repo.mkdir()
        self.backup_files.mkdir()
        (self.backup_files / "file1.txt").write_text("file1")
        print(self.base_dir)

    def setup_class(self):
        self.init_directory_structure(self)
        self.set_default_config(self)
        ret = run_borg_command("init", self.env, self.config, self.config_file, ["--encryption", "repokey"])
        ret = run_borg_command("create", self.env, self.config, self.config_file, [])
        assert ret == 0

    def teardown_class(self):
        rmtree(self.base_dir, ignore_errors=True)

    def test_borg_list_list(self, capfd):
        ret = run_borg_command("list", self.env, self.config, self.config_file, ["--json",])
        assert ret == 0
        stdout = capfd.readouterr().out
        result = loads(stdout)
        assert len(result["archives"]) == 1
        archive = result["archives"][0]
        assert archive["archive"].startswith(TEST_PREFIX)

    def test_borg_list_archive(self, capfd):
        ret = run_borg_command("list", self.env, self.config, self.config_file, ["--json",])
        assert ret == 0
        stdout = capfd.readouterr().out
        result = loads(stdout)
        assert len(result["archives"]) == 1
        archive = result["archives"][0]
        assert archive["archive"].startswith(TEST_PREFIX)
        ret = run_borg_command("list", self.env, self.config, self.config_file, ["--json-lines", "::" + archive["archive"]])
        stdout = capfd.readouterr().out
        lines = stdout.splitlines()
        assert len(lines) == 2
        directory = loads(lines[0])
        assert directory["path"].endswith("files_to_backup")
        file1 = loads(lines[1])
        assert file1["path"].endswith("files_to_backup/file1.txt")


    def test_borg_list_invalid_argument(self):
        ret = run_borg_command("list", self.env, self.config, self.config_file, ["--nonono"])
        assert ret == 2

    #    import subprocess
    #    import sys
    #    p = subprocess.Popen(["echo", "123"], stdout=sys.stdout)
    #    p.wait()
    #    stdout = capsys.readouterr().out
    #    #breakpoint()
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    #    with pytest.raises(SystemExit) as ext:
    #        generate_default_config()
    #        assert ext.value.code == 0
    #    default_config_stdout = capsys.readouterr().out
    #    yaml = YAML()
    #    config = yaml.load(default_config_stdout)
    #    self.config = config
    #    #run_borg_command("init", {}, config, "no_config_file?", [])
