# borgctl - wrapper around borgbackup

## Overview
[borgbackup](https://www.borgbackup.org/) is cool and easy to use. But in the end, we all have to write our own bash script arround borg. borgctl helps you by having
 
## Features
- One or more configuration files used by borgctl to invoke borg. You can backup different directories to different repositories.
- Run multiple borg commands using `--cron` (commands can be specified in the config file)
- Write a state file (text file with current timestamp in) after sucessfully executing borg commands (can be used for monitoring)
- Add logging

## Quickstart
- ascinema

## Installation
- pip install borgctl
- yay borgctl
- debian Paket?

## Configuration
- default locations for logging/config

- creates passwords (10 words)
