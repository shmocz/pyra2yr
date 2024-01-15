#!/usr/bin/env python3
import shutil
import time
import os
import subprocess
import argparse
import traceback
from pathlib import Path
import re
import logging

NAME_SPAWNER = "gamemd-spawn.exe"
NAME_SPAWNER_PATCHED = "gamemd-spawn-ra2yrcpp.exe"
NAME_SPAWNER_SYRINGE = "gamemd-spawn-syr.exe"

FILE_PATHS = f"""\
BINKW32.DLL
spawner.xdp
ra2.mix
ra2md.mix
theme.mix
thememd.mix
langmd.mix
language.mix
expandmd01.mix
mapsmd03.mix
maps02.mix
maps01.mix
Ra2.tlb
INI
Maps
RA2.INI
RA2MD.ini
ddraw.ini
spawner2.xdp
Blowfish.dll
ddraw.dll
Syringe.exe
cncnet5.dll
{NAME_SPAWNER}\
"""


LIB_PATHS = f"""\
{NAME_SPAWNER_PATCHED}
libgcc_s_dw2-1.dll
libra2yrcpp.dll
libstdc++-6.dll
libwinpthread-1.dll
zlib1.dll\
"""


def mklink(dst, src):
    if os.path.islink(dst):
        os.unlink(dst)
    os.symlink(src, dst)


def prun(args, **kwargs):
    cmdline = [str(x) for x in args]
    logging.info("exec: %s", cmdline)
    return subprocess.run(cmdline, **kwargs)


def create_symlinks(instance_dir: Path, game_data_dir: Path):
    """Symlink relevant data files for this test instance."""
    # Clear old symlinks
    for p in os.listdir(instance_dir):
        if os.path.islink(p):
            os.unlink(p)

    for p in re.split(r"\s+", FILE_PATHS):
        mklink(instance_dir / p, game_data_dir / p)

    for p in re.split(r"\s+", LIB_PATHS):
        mklink(instance_dir / p, (game_data_dir / p).absolute())

    # for p in self.cfg.syringe_dlls:
    #     mklink(instance_dir / p, (self.game_data_dir / p).absolute())


def registry_commands():
    items = {
        r"HKEY_CURRENT_USER\Software\Wine\DllOverrides": [
            ("ddraw", "native,builtin"),
            ("zlib1", "builtin,native"),
        ],
        r"HKEY_CURRENT_USER\Environment": [
            (
                "PATH",
                r"Z:\\usr\\i686-w64-mingw32\\bin;Z:\\usr\\i686-w64-mingw32\\lib",
            )
        ],
        r"HKEY_CURRENT_USER\Software\Wine\Explorer": [("Desktop", "Default")],
        r"HKEY_CURRENT_USER\Software\Wine\Explorer\Desktops": [("Default", "1024x768")],
    }
    for k, v in items.items():
        for key, value in v:
            yield ["wine", "reg", "add", k, "/v", key, "/d", value]


def prepare_wine_prefix(wineprefix_dir: Path):
    if wineprefix_dir.exists():
        return
    cmds = (
        [["wineboot", "-ik"]]
        + list(registry_commands())
        + [["wineboot", "-s"], ["wineserver", "-w"]]
    )
    try:
        for c in cmds:
            r = prun(c, check=True)
    except Exception as e:
        logging.error("%s", traceback.format_exc())
        shutil.rmtree(wineprefix_dir)
        raise


def run_gamemd(a):
    os.environ["WINEPREFIX"] = str(a.wineprefix_dir.absolute())
    os.environ["RA2YRCPP_PORT"] = str(a.port)
    os.environ["RA2YRCPP_RECORD_PATH"] = ""
    prepare_wine_prefix(a.wineprefix_dir)
    create_symlinks(a.instance_dir, a.game_data_dir)
    subprocess.run(
        ["wine", a.spawner_name, "-SPAWN"], cwd=str(a.instance_dir.absolute())
    )


def parse_args():
    a = argparse.ArgumentParser(
        description="RA2YR game launcher helper",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    a.add_argument("-w", "--wineprefix-dir", type=Path)
    a.add_argument("-i", "--instance-dir", type=Path)
    a.add_argument("-g", "--game-data-dir", type=Path)
    a.add_argument("-p", "--port", type=int)
    a.add_argument("-s", "--spawner-name", type=str)
    a.set_defaults(func=run_gamemd)
    return a.parse_args()


def main():
    a = parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
