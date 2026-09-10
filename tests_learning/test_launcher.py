"""Opt-in Windows launcher check. Existing learning service must be idle on 8765."""
import json
import os
import subprocess
from pathlib import Path
from urllib.request import urlopen

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('LEARNING_LAUNCHER_TEST') != '1', reason='Opt-in local launcher integration check.')
ROOT = Path(__file__).resolve().parent.parent


def health(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2) as r:
            return json.load(r)
    except OSError:
        return None


def test_changing_port_cannot_start_a_second_instance():
    original = health(8765)
    assert original and original['app'] == 'douyin-learning'
    assert health(8876) is None, 'Test port is occupied'
    state_file = ROOT / 'learning_data/server.json'
    original_record = state_file.read_bytes()
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'start.ps1'), '-NoBrowser', '-Port', '8876'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        assert result.returncode == 0
        assert health(8876) is None, 'Second instance started against the same database'
        assert json.loads(state_file.read_text(encoding='utf-8-sig'))['pid'] == original['pid']
    finally:
        # The old implementation starts a second instance: stop only that recorded test process.
        duplicate = health(8876)
        if duplicate and duplicate.get('app') == 'douyin-learning':
            record = json.loads(state_file.read_text(encoding='utf-8-sig'))
            if record.get('pid') == duplicate['pid'] and record.get('port') == 8876:
                subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(ROOT / 'stop.ps1')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        state_file.write_bytes(original_record)
