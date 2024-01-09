#!/usr/bin/env python3
import datetime
from pathlib import Path


class Py3status:
    format = 'B:{days}d'
    log_dir = Path("/var/log/borgctl")

    def last_update(self):

        days_last_backup = 9000
        now = datetime.datetime.now()

        for state_file in self.log_dir.glob("borg_state*_create.txt"):
            backup_date = state_file.read_text()
            backup_date = datetime.datetime.strptime(backup_date, "%Y-%m-%d_%H:%M:%S")
            diff = now - backup_date
            if diff.days < days_last_backup:
                days_last_backup = diff.days

        full_text = self.py3.safe_format(self.format, {'days': days_last_backup})

        if days_last_backup > 7:
            color = self.py3.COLOR_BAD
        else:
            color = self.py3.COLOR_GOOD

        return {
            'full_text': full_text,
            'color': color,
            'cached_until': self.py3.time_in(seconds=900)

        }


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test
    module_test(Py3status)
