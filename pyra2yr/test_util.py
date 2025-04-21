import asyncio
import unittest
import logging
import json
import os
from functools import cached_property
from dataclasses import dataclass
from enum import Enum

import numpy as np
from ra2yrproto import commands_yr, core, ra2yr

from pyra2yr.manager import Manager, ManagerUtil, PlaceStrategy
from pyra2yr.game import Game, MultiGameInstanceConfig, PlayerEntry
from pyra2yr.state_objects import FactoryEntry, MapData, ObjectEntry
from pyra2yr.util import array2coord, coord2array, setup_logging
from pyra2yr.state_manager import StateManager

cfg_json = r"""
{
  "base_directory": "./test_instances",
  "game_data_directory": "../ra2yrcpp/maingame",
  "ini_overrides": ["./pyra2yr/data/cheap_items.ini"],
  "spawner_name": "gamemd-spawn-ra2yrcpp.exe",
  "container_image": "shmocz/ra2yrcpp:latest",
  "protocol": "zero",
  "syringe_dlls": [],
  "tunnel_address": "0.0.0.0",
  "tunnel_port": 50000,
  "scenario": {
    "allies_allowed": true,
    "bridges_destroyable": true,
    "build_off_ally": true,
    "game_speed": 0,
    "map_path": "./pyra2yr/data/arctic_circle.map",
    "mcv_redeploy": true,
    "multi_engineer": false,
    "ra2_mode": false,
    "seed": 123,
    "short_game": true,
    "start_credits": 10000,
    "superweapons": true,
    "unit_count": 0
  },
  "players": [
    {
      "name": "player_0",
      "color": "Red",
      "side": "1",
      "location": 0,
      "is_host": true,
      "ws_port": 14521
    },
    {
      "name": "player_1",
      "color": "Yellow",
      "side": "6",
      "location": 1,
      "ws_port": 14522
    },
    {
      "name": "player_2",
      "color": "Green",
      "side": "1",
      "location": 2,
      "ws_port": 14523,
      "is_observer": true
    }
  ]
}
"""


async def check_config(U: ManagerUtil = None):
    # Get config
    cmd_1 = await U.inspect_configuration()
    cfg1 = cmd_1.config
    cfg_ex = commands_yr.Configuration()
    cfg_ex.CopyFrom(cfg1)
    cfg_ex.debug_log = True
    cfg_ex.parse_map_data_interval = 1
    assert cfg_ex == cfg1

    # Try changing some settings
    cfg_diff = commands_yr.Configuration(parse_map_data_interval=4)
    cfg2_ex = commands_yr.Configuration()
    cfg2_ex.CopyFrom(cfg1)
    cfg2_ex.MergeFrom(cfg_diff)
    cmd_2 = await U.inspect_configuration(config=cfg_diff)
    cfg2 = cmd_2.config
    assert cfg2 == cfg2_ex


# TODO: put to StateContainer
class HouseFactions(Enum):
    NONE = 0
    SOVIET = 1
    ALLIED = 2
    YURI = 3


@dataclass
class BuildableTypes:
    barracks: ra2yr.ObjectTypeClass = None
    battle_lab: ra2yr.ObjectTypeClass = None
    conyard: ra2yr.ObjectTypeClass = None
    mcv: ra2yr.ObjectTypeClass = None
    power: ra2yr.ObjectTypeClass = None
    radar: ra2yr.ObjectTypeClass = None
    refinery: ra2yr.ObjectTypeClass = None
    shipyard: ra2yr.ObjectTypeClass = None
    wall: ra2yr.ObjectTypeClass = None
    war_factory: ra2yr.ObjectTypeClass = None

    @classmethod
    def get(cls, s: StateManager, h: ra2yr.House):
        f = None
        # TODO(shmocz): more robust check
        if h.faction == "Arabs":
            f = HouseFactions.SOVIET
        elif h.faction == "Alliance":
            f = HouseFactions.ALLIED
        pfx = {
            HouseFactions.SOVIET: "Soviet",
            HouseFactions.ALLIED: "Allied",
            HouseFactions.YURI: "Yuri",
        }[f]
        m = {
            "barracks": r"Barracks",
            "battle_lab": r"Battle\s+Lab",
            "conyard": r"Construction\s+Yard",
            "mcv": r"Construction\s+Vehicle",
            "refinery": r"Ore\s+Refinery",
            "war_factory": r"War\s+Factory",
        }
        m = {k: f"{pfx}\\s+{v}" for k, v in m.items()}
        m["power"] = {
            HouseFactions.SOVIET: r"Soviet\s+Tesla\s+Reactor",
            HouseFactions.ALLIED: r"Allied\s+Power\s+Plant",
            HouseFactions.YURI: r"Yuri\s+Bio\s+Reactor",
        }[f]
        m["radar"] = {
            HouseFactions.SOVIET: r"Soviet\s+Radar\s+Tower",
            HouseFactions.ALLIED: r"Allied\s+Airforce\s+Command",
            HouseFactions.YURI: r"Yuri\s+Psychic\s+Sensor",
        }[f]
        m["shipyard"] = {
            HouseFactions.SOVIET: r"Soviet\s+Shipyard",
            HouseFactions.ALLIED: r"Allied\s+Shipyard",
            HouseFactions.YURI: r"Yuri\s+Submarine\s+Pen",
        }[f]
        entries = {k: next(s.query_type_class(p=v)) for k, v in m.items()}
        entries["wall"] = next(
            s.query_type_class(
                p=f"{pfx}\\s+Wall", abstract_type=ra2yr.ABSTRACT_TYPE_BUILDINGTYPE
            )
        )

        return cls(**entries)


class MyManager(Manager):
    async def get_place_locations(
        self, coords: np.array, o: ra2yr.Object, rx: int, ry: int
    ) -> np.array:
        """Return coordinates where a building can be placed.

        Parameters
        ----------
        coords : np.array
            Center point
        o : ra2yr.Object
            The ready building
        rx : int
            Query x radius
        ry : int
            Query y radius

        Returns
        -------
        np.array
            Result coordinates.
        """
        xx = np.arange(rx) - int(rx / 2)
        yy = np.arange(ry) - int(ry / 2)
        if coords.size < 3:
            coords = np.append(coords, 0)
        grid = np.transpose([np.tile(xx, yy.shape), np.repeat(yy, xx.shape)]) * 256
        grid = np.c_[grid, np.zeros((grid.shape[0], 1))] + coords
        res = await self.M.place_query(
            type_class=o.pointer_technotypeclass,
            house_class=o.pointer_house,
            coordinates=[array2coord(x) for x in grid],
        )
        return np.array([coord2array(x) for x in res.coordinates])

    def get_unique_tc(self, pattern) -> ra2yr.ObjectTypeClass:
        tc = list(self.state.query_type_class(p=pattern))
        if len(tc) != 1:
            raise RuntimeError(f"Non unique TypeClass: {pattern}: {tc}")
        return tc[0]

    async def begin_production(self, t: ra2yr.ObjectTypeClass) -> FactoryEntry:
        # TODO: Check for error
        res = await self.M.start_production(t)
        if res.result_code != core.ResponseCode.OK:
            raise RuntimeError(f"Error: {res.error_message}")
        frame = self.state.s.current_frame

        # Wait until corresponding type is being produced
        await self.wait_state(
            lambda: any(
                f
                for f in self.state.query_factories(h=self.state.current_player(), t=t)
            )
            or self.state.s.current_frame - frame >= 300
        )
        try:
            # Get the object
            return next(self.state.query_factories(h=self.state.current_player(), t=t))
        except StopIteration as e:
            raise RuntimeError(f"Failed to start production of {t}") from e

    async def produce_unit(self, t: ra2yr.ObjectTypeClass | str) -> ObjectEntry:
        if isinstance(t, str):
            t = self.get_unique_tc(t)

        fac = await self.begin_production(t)

        # Wait until done
        # TODO: check for cancellation
        await self.wait_state(
            lambda: fac.object.get().current_mission == ra2yr.Mission_Guard
        )
        return fac.object

    async def produce_and_place(
        self,
        t: ra2yr.ObjectTypeClass,
        coords,
        strategy: PlaceStrategy = PlaceStrategy.FARTHEST,
    ) -> ObjectEntry:
        U = self.M
        fac = await self.begin_production(t)
        obj = fac.object

        # wait until done
        await self.wait_state(lambda: fac.get().completed)
        logging.debug("(frame=%d), done=%s", self.state.s.current_frame, obj)

        if strategy == PlaceStrategy.FARTHEST:
            place_locations = await self.get_place_locations(
                coords,
                obj.get(),
                15,
                15,
            )

            # get cell closest away and place
            dists = np.sqrt(np.sum((place_locations - coords) ** 2, axis=1))
            coords = place_locations[np.argsort(dists)[-1]]
        r = await U.place_building(building=obj.get(), coordinates=array2coord(coords))
        if r.result_code != core.ResponseCode.OK:
            raise RuntimeError(f"place failed: {r.error_message}")
        # wait until building has been placed
        await self.wait_state(
            lambda: obj.invalid()
            or fac.invalid()
            and obj.get().current_mission
            not in (ra2yr.Mission_None, ra2yr.Mission_Construction)
        )
        return obj

    async def get_map_data(self) -> MapData:
        W = await self.M.map_data()
        return MapData(W)


class ExManager(MyManager):
    @cached_property
    def buildable_types(self) -> BuildableTypes:
        return BuildableTypes.get(self.state, self.state.current_player())

    async def deploy_mcv(self):
        o = next(
            self.state.query_objects(
                t=self.buildable_types.mcv, h=self.state.current_player()
            )
        )
        await self.M.deploy(o.o)
        await self.wait_state(
            lambda: len(
                list(
                    self.state.query_objects(
                        t=self.buildable_types.conyard, h=self.state.current_player()
                    )
                )
            )
            == 1
        )
        o = next(
            self.state.query_objects(
                t=self.buildable_types.conyard, h=self.state.current_player()
            )
        )
        await self.wait_state(lambda: o.get().current_mission == ra2yr.Mission_Guard)

    async def sell_all_buildings(self):
        for o in self.state.query_objects(
            h=self.state.current_player(), a=ra2yr.ABSTRACT_TYPE_BUILDING
        ):
            await self.M.sell(objects=o.get())


class BaseGameTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        setup_logging()
        self.poll_frequency = 30
        self.fetch_state_timeout = 10.0
        self.all_managers: list[tuple[PlayerEntry, ExManager]] = []
        for P in self.game.cfg.players:
            M = ExManager(port=P.ws_port)
            M.start()
            self.all_managers.append((P, M))

    def run(self, result=None):
        with Game(cfg=self.get_test_config()) as G:
            self.game = G
            return super().run(result)

    @cached_property
    def managers(self) -> list[tuple[PlayerEntry, ExManager]]:
        return [M for P, M in self.all_managers if not P.is_observer]

    async def asyncTearDown(self):
        async with asyncio.TaskGroup() as tg:
            for _, M in self.all_managers:
                tg.create_task(M.stop())
        self.all_managers.clear()
        del self.managers

    @classmethod
    def get_test_config(cls):
        cfg = MultiGameInstanceConfig.from_dict(json.loads(cfg_json))
        if os.environ.get("USE_SYRINGE", None) is not None:
            cfg.use_syringe = True
        return cfg


class SingleStepManager(ExManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.crcs = []
        self._pending_tasks = []

    async def step(self, s: ra2yr.GameState):
        self.crcs.append(s.crc)
