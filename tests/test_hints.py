import tempfile

import pytest

from spacetrail.hints import hint


@pytest.mark.parametrize("path, word", [
    (r"C:\$Recycle.Bin", "Recycle Bin"),
    (r"C:\Windows\SoftwareDistribution\Download", "Windows Update"),
    (r"C:\Users\me\AppData\Local\Temp", "Temporary"),
    (r"C:\Users\me\AppData\Local\Temp\setup123", "Temporary"),
    (r"C:\Windows\Temp", "Temporary"),
    (r"D:\code\site\node_modules", "npm install"),
    (r"C:\Users\me\AppData\Local\pip\Cache", "pip cache purge"),
    ("/home/me/.cache/pip", "pip cache purge"),
    (r"C:\Users\me\AppData\Local\npm-cache", "npm cache clean"),
    ("/home/me/.npm", "npm cache clean"),
    (r"C:\Users\me\AppData\Local\Google\Chrome", "Browser"),
    (r"C:\Users\me\AppData\Local\Microsoft\Edge\User Data\Default\Cache", "Browser"),
    (r"C:\Users\me\AppData\Local\Mozilla\Firefox", "Browser"),
])
def test_known_hogs(path, word):
    assert word in hint(path)


def test_current_temp_folder():
    assert "Temporary" in hint(tempfile.gettempdir())


@pytest.mark.parametrize("path", [r"C:\Users\me\Downloads", r"C:\Games\temple", "/home/me/node_modules_old"])
def test_ordinary_folders_get_no_hint(path):
    assert hint(path) is None


def test_closest_match_wins():
    assert "npm install" in hint("C:/Users/me/AppData/Local/Temp/build/node_modules")
