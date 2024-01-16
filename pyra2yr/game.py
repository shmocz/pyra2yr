import subprocess
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field, fields
from enum import Enum
from yaml import dump
from pyra2yr.util import read_file, write_file
from pyra2yr.docker import Docker, ComposeService

try:
    # pylint: disable=ungrouped-imports
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper


def try_fn(fn, retry_interval=2.0, tries=3):
    for _ in range(tries):
        try:
            r = fn()
            return r
        except KeyboardInterrupt as e:
            raise e
        except Exception:
            time.sleep(retry_interval)
    raise RuntimeError("Timeout")


def prun(args, **kwargs):
    cmdline = [str(x) for x in args]
    logging.info("exec: %s", cmdline)
    # pylint: disable=subprocess-run-check
    return subprocess.run(cmdline, **kwargs)


def popen(args, **kwargs):
    return subprocess.Popen([str(x) for x in args], **kwargs)


def get_game_uid():
    return int(
        prun(
            Docker.run(
                [
                    "python3",
                    "-c",
                    'import os; print(os.stat("/home/user/project").st_uid)',
                ],
                "game",
            ),
            check=True,
            capture_output=True,
        ).stdout.strip()
    )


def get_compose_file(ws_ports: list[int], container_image: str) -> str:
    s = {"version": "3.9"}
    ports = [6081, 12001, 5901, 50000] + ws_ports
    if len(set(ports)) != len(ports) or any(p < 1 for p in ports):
        raise RuntimeError(
            f"All ports must be unique and positive numbers. Got: {ports}"
        )
    srv = [
        ComposeService(
            "vnc",
            "shmocz/vnc:latest",
            command=(
                "sh -c 'Xvnc :1 -depth 24 -geometry $$RESOLUTION -br -rfbport=5901 "
                "-SecurityTypes None -AcceptSetDesktopSize=off'"
            ),
            ports=[f"{p}:{p}" for p in ports],
            environment={"RESOLUTION": "1280x1024"},
        ),
        ComposeService(
            "novnc",
            "shmocz/vnc:latest",
            command="/utils/novnc_proxy --vnc localhost:5901 --listen 6081",
            network_mode="service:vnc",
            user="root",
        ),
        ComposeService(
            "wm",
            "shmocz/vnc:latest",
            command="sh -c 'exec openbox-session'",
            depends_on=["vnc"],
            network_mode="service:vnc",
            environment={"DISPLAY": ":1"},
        ),
        ComposeService(
            "tunnel",
            "shmocz/pycncnettunnel:latest",
            network_mode="service:vnc",
            stop_signal="SIGKILL",
        ),
        ComposeService(
            "game",
            container_image,
            network_mode="service:vnc",
            stop_signal="SIGKILL",
            volumes=[".:/home/user/project"],
            working_dir="/home/user/project",
            depends_on=["wm"],
            cap_add=["SYS_PTRACE"],
        ),
    ]
    s["services"] = {}
    for x in srv:
        s["services"].update(x.to_dict())

    return dump(s, Dumper=Dumper)


class ProtocolVersion(Enum):
    zero = 0
    compress = 2


class Color(Enum):
    Yellow = 0
    Red = 1
    Blue = 2
    Green = 3
    Orange = 4
    Teal = 5
    Purple = 6
    Pink = 7


@dataclass
class PlayerEntry:
    name: str
    color: Color
    side: int
    location: int
    index: int
    is_host: bool = False
    is_observer: bool = False
    ai_difficulty: int = -1
    port: int = 0
    ws_port: int = -1
    backend: str = None

    def __post_init__(self):
        if self.port <= 0:
            self.port = 13360 + self.index
        if not isinstance(self.color, Color):
            self.color = Color[self.color]


@dataclass
class ScenarioConfig:
    map_path: str
    unit_count: int
    start_credits: int
    seed: int
    ra2_mode: bool
    short_game: bool
    superweapons: bool
    game_speed: int = 0
    frame_send_rate: int = 1
    crates: bool = False
    mcv_redeploy: bool = True
    allies_allowed: bool = True
    multi_engineer: bool = False
    bridges_destroyable: bool = True
    build_off_ally: bool = True

    @classmethod
    def from_dict(cls, d):
        fld = {f.name: f.type for f in fields(cls)}
        args = {}
        for k, v in d.items():
            args[k] = fld[k](v)
        return cls(**args)


@dataclass
class MultiGameInstanceConfig:
    scenario: ScenarioConfig
    syringe_dlls: list = field(default_factory=list)
    # Either "docker" or "native"
    backend: str = "docker"
    base_directory: Path = None
    container_image: str = "shmocz/pyra2yr:latest"
    docker_game_data: Path = Path("/home/user/RA2")
    game_data_directory: Path = None
    ini_overrides: list[Path] = field(default_factory=list)
    players: list[PlayerEntry] = field(default_factory=list)
    protocol: ProtocolVersion = ProtocolVersion.zero
    spawner_name: str = "gamemd-spawn-ra2yrcpp.exe"
    tunnel_address: str = "0.0.0.0"
    tunnel_port: int = 50000

    def __post_init__(self):
        for k in ["color", "location", "name"]:
            if len(set(getattr(p, k) for p in self.players)) != len(self.players):
                raise RuntimeError(f'Duplicate player attribute: "{k}"')

    @classmethod
    def from_dict(cls, d):
        fld = {f.name: f.type for f in fields(cls)}
        args = {
            "players": [
                PlayerEntry(index=i, **x) for (i, x) in enumerate(d.pop("players"))
            ]
        }
        for k, v in d.items():
            if k == "protocol":
                args[k] = ProtocolVersion[v]
            elif k == "scenario":
                args[k] = ScenarioConfig.from_dict(v)
            else:
                args[k] = fld[k](v)
        return cls(**args)

    def kv_to_string(self, name, x):
        return f"[{name}]\n" + "\n".join(f"{k}={v}" for k, v in x)

    def others_sections(self, player_index: int):
        oo = [
            p for p in self.players if p.ai_difficulty < 0 and p.index != player_index
        ]
        res = []
        for o in oo:
            pv = self.player_values(o) + [("Ip", self.tunnel_address)]
            res.append(self.kv_to_string(f"Other{o.index + 1}", pv))
        return "\n\n".join(res)

    def player_values(self, p: PlayerEntry):
        kmap = [
            ("Name", "name"),
            ("Side", "side"),
            ("IsSpectator", "is_observer"),
            ("Port", "port"),
        ]
        return [(k, getattr(p, v)) for k, v in kmap] + [("Color", p.color.value)]

    def to_ini(self, player_index: int):
        player = next(p for p in self.players if p.index == player_index)
        ai_players = [p for p in self.players if p.ai_difficulty > -1]
        S = self.scenario
        main_section_values = [
            ("Credits", S.start_credits),
            ("FrameSendRate", S.frame_send_rate),
            ("GameMode", 1),
            ("GameSpeed", S.game_speed),
            ("MCVRedeploy", S.mcv_redeploy),
            ("Protocol", self.protocol.value),
            ("Ra2Mode", S.ra2_mode),
            ("ShortGame", S.short_game),
            ("SidebarHack", "Yes"),
            ("SuperWeapons", S.superweapons),
            ("GameID", 12850),
            ("Bases", "Yes"),
            ("UnitCount", S.unit_count),
            ("UIGameMode", "Battle"),
            ("Host", player.is_host),
            ("Seed", S.seed),
            ("Scenario", "spawnmap.ini"),
            ("PlayerCount", len(self.players) - len(ai_players)),
            ("AIPlayers", len(ai_players)),
            ("Crates", S.crates),
            ("AlliesAllowed", S.allies_allowed),
            ("MultiEngineer", S.multi_engineer),
            ("BridgeDestory", S.bridges_destroyable),
            ("BuildOffAlly", S.build_off_ally),
        ]

        main_section_values.extend(self.player_values(player))

        res = []
        res.append(self.kv_to_string("Settings", main_section_values))
        res.append(self.others_sections(player_index))
        res.append(
            self.kv_to_string(
                "SpawnLocations",
                [(f"Multi{p.index + 1}", p.location) for p in self.players],
            )
        )
        res.append(
            self.kv_to_string(
                "Tunnel", [("Ip", self.tunnel_address), ("Port", self.tunnel_port)]
            )
        )
        if ai_players:
            res.append(
                self.kv_to_string(
                    "HouseHandicaps",
                    [(f"Multi{x.index + 1}", f"{x.ai_difficulty}") for x in ai_players],
                )
            )
            res.append(
                self.kv_to_string(
                    "HouseCountries",
                    [(f"Multi{x.index + 1}", f"{x.side}") for x in ai_players],
                )
            )
            res.append(
                self.kv_to_string(
                    "HouseColors",
                    [(f"Multi{x.index + 1}", f"{x.color.value}") for x in ai_players],
                )
            )
        return "\n\n".join(res) + "\n"


class GameInstance:
    def __init__(self, cfg: MultiGameInstanceConfig, player_index: int, game_uid: int):
        self.mcfg = cfg
        self.cfg = self.mcfg.players[player_index]
        self.player_index = player_index
        self.game_uid = game_uid
        self.game_data_dir: Path = None
        self.base_directory: Path = self.mcfg.base_directory
        self.instance_dir = self.base_directory / self.cfg.name
        self.map_path = self.instance_dir / "spawnmap.ini"
        self.spawn_path = self.instance_dir / "spawn.ini"
        self.wineprefix_dir = self.instance_dir / ".wine"
        self._container_name = f"game-{self.player_index}"
        self._proc = None
        if not self.cfg.backend:
            self.cfg.backend = self.mcfg.backend

    def generate_map_ini(self):
        m = read_file(self.mcfg.scenario.map_path, encoding="latin-1")
        if self.mcfg.ini_overrides:
            write_file(
                self.map_path,
                "\n\n".join([m] + [read_file(p) for p in self.mcfg.ini_overrides]),
            )

    def generate_spawn_ini(self):
        write_file(self.spawn_path, self.mcfg.to_ini(self.player_index))

    def prepare_instance_directory(self):
        if not self.instance_dir.exists():
            self.instance_dir.mkdir(parents=True)
        self.generate_map_ini()
        self.generate_spawn_ini()

    def __start_native(self):
        raise NotImplementedError()

    def __start_docker(self):
        cmd = Docker.run(
            [
                "./scripts/run-gamemd.py",
                "-w",
                self.wineprefix_dir,
                "-i",
                self.instance_dir,
                "-g",
                self.mcfg.docker_game_data,
                "-p",
                self.cfg.ws_port,
                "-s",
                self.mcfg.spawner_name,
            ],
            service="game",
            name=self._container_name,
            env=[
                ("DISPLAY", ":1"),
                ("HOME", "/home/user"),
                ("RA2YRCPP_GAME_DIR", "/home/user/RA2"),
                ("WINEARCH", "win32"),
            ],
            uid=self.game_uid,
            compose_files=["docker-compose.instance.yml"],
            volumes=[(self.mcfg.game_data_directory.absolute(), "/home/user/RA2")],
        )
        return popen(cmd)

    # TODO: call non-member fn
    def start(self):
        try:
            self.prepare_instance_directory()
            self._proc = {"docker": self.__start_docker, "native": self.__start_native}[
                self.cfg.backend
            ]()
        except KeyError as e:
            raise RuntimeError(f"Unknown backend: {self.cfg.backend}") from e

    def stop(self):
        prun(["docker", "stop", self._container_name])
        self._proc.wait()

    def wait(self):
        self._proc.wait()


class Game:
    def __init__(self, cfg: MultiGameInstanceConfig):
        self.cfg = cfg
        self.uid = get_game_uid()
        self.human_players = [p for p in cfg.players if p.ai_difficulty < 0]
        self.games = [
            GameInstance(cfg, c.index, game_uid=self.uid) for c in self.human_players
        ]
        self._proc: subprocess.Popen = None

    def start(self):
        """Start the main game."""
        # This needs to be generated dynamically to properly set port numbers
        c = "docker-compose.instance.yml"
        ws_ports = [p.ws_port for p in self.human_players]
        write_file(
            c, get_compose_file(ws_ports, container_image=self.cfg.container_image)
        )
        # TODO(shmocz): monitor in separate thread for errors
        self._proc = popen(
            Docker.up(["vnc", "novnc", "wm", "tunnel"], compose_files=[c])
        )
        # hack to wait until tunnel service has started
        try_fn(
            lambda: prun(["docker", "exec", "pyra2yr-tunnel-1", "ls", "-l"], check=True)
        )
        for g in self.games:
            g.start()

    def stop(self):
        """Stop all game instances."""
        prun(["docker-compose", "down", "--remove-orphans", "-t", "1"])
        self._proc.kill()
        self._proc.wait()
        for g in self.games:
            g.stop()
        self.wait()

    def wait(self):
        """Wait for game to exit."""
        for g in self.games:
            g.wait()
