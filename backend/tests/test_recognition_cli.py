"""Check that the executable entry points import correctly and explain usage."""
import subprocess
import sys
from pathlib import Path
import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", [
    "scripts_fingerprint_catalog.py", "tools/index_licensed_audio.py", "tools/match_audio_files.py", "tools/diagnose_recording.py",
])
def test_recognition_cli_help_works_from_another_directory(tmp_path, script):
    result = subprocess.run([sys.executable, str(BACKEND / script), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_indexer_requires_explicit_reference_permission(tmp_path):
    result = subprocess.run([sys.executable, str(BACKEND / "tools/index_licensed_audio.py"),
                             "--file", str(tmp_path / "recording.wav")],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert "--i-have-rights" in result.stderr
