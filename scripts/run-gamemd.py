#!/usr/bin/env python3
import shutil
import time
import os
import subprocess
import argparse
import traceback
import datetime as dt
from pathlib import Path
import re
import logging

NAME_SPAWNER = "gamemd-spawn.exe"
NAME_SPAWNER_PATCHED = "gamemd-spawn-ra2yrcpp.exe"

# TODO: handle missing entries
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
expandmd02.mix
expandspawn01.mix
expandspawn02.mix
ecache97.mix
expand97.mix
mapsmd03.mix
maps02.mix
maps01.mix
multimd.mix
MULTI.MIX
RA2MD.ico
Ra2.tlb
ra2md.lcf
yuri.lcf
Ra2.lcf
INI
Maps
RA2.INI
RA2MD.ini
NOTES.ICO
RA2.ICO
ddraw.ini
spawner2.xdp
Blowfish.dll
Blowfish.tlb
ddraw.dll
Syringe.exe
cncnet.fnt
cncnet5.dll
gamemd.exe
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
    for fname in os.listdir(instance_dir):
        p = instance_dir / fname
        if p.is_symlink():
            p.unlink()

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


def find_pid(program_name):
    try:
        pgrep_output = subprocess.check_output(["pgrep", "-f", program_name], text=True)
        pids = [int(pid) for pid in pgrep_output.split()]
        if len(pids) > 1:
            logging.warning("Ambiguous pids: %s", pids)
        return pids[0] if len(pids) == 1 else None
    except subprocess.CalledProcessError:
        logging.warning("couldn't find pid %s", program_name)
        return None


def run_syringe(program, cwd=None, timeout=20.0):
    cmdline = ["wine", "Syringe.exe", program + " ", "-SPAWN", "-CD", "-LOG"]
    subprocess.run(cmdline, cwd=cwd)
    deadline = dt.datetime.now() + dt.timedelta(seconds=timeout)
    while dt.datetime.now() < deadline:
        pid = find_pid(program)
        if pid is None:
            time.sleep(0.5)
    if pid is None:
        raise RuntimeError("gamemd failed to launch")
    # Wait until process exits
    try:
        while os.path.exists(f"/proc/{pid}"):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def run_gamemd(a):
    os.environ["WINEPREFIX"] = str(a.wineprefix_dir.absolute())
    prepare_wine_prefix(a.wineprefix_dir)
    create_symlinks(a.instance_dir, a.game_data_dir)
    cmdline = ["wine", a.spawner_name, "-SPAWN"]
    cwd = str(a.instance_dir.absolute())
    if a.syringe:
        run_syringe("gamemd.exe", cwd=cwd)
    else:
        subprocess.run(cmdline, cwd=cwd)


# TODO: Help string
def parse_args():
    a = argparse.ArgumentParser(
        description="RA2YR game launcher helper",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    a.add_argument("-w", "--wineprefix-dir", type=Path)
    a.add_argument("-i", "--instance-dir", type=Path)
    a.add_argument("-g", "--game-data-dir", type=Path)
    a.add_argument("-s", "--spawner-name", type=str)
    a.add_argument("-S", "--syringe", help="Use syringe", action="store_true")
    a.set_defaults(func=run_gamemd)
    return a.parse_args()


def main():
    a = parse_args()
    FORMAT = (
        "[%(levelname)s] %(asctime)s %(module)s.%(filename)s:%(lineno)d: %(message)s"
    )
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)
    a.func(a)


if __name__ == "__main__":
    main()
