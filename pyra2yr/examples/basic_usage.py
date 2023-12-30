#!/usr/bin/env python3
import atexit
import asyncio
import json

from ra2yrproto import ra2yr
from pyra2yr.game import Game, MultiGameInstanceConfig
from pyra2yr.manager import Manager

# In this example, ra2yrcpp repository resides in parent folder and CnCNet data folder inside it.
cfg_json = r"""
{
  "base_directory": "./test_instances",
  "game_data_directory": "../ra2yrcpp/maingame",
  "ini_overrides": ["./pyra2yr/data/cheap_items.ini"],
  "spawner_name": "gamemd-spawn-ra2yrcpp.exe",
  "protocol": "zero",
  "syringe_dlls": [],
  "tunnel_address": "0.0.0.0",
  "tunnel_port": 50000,
  "scenario": {
    "allies_allowed": true,
    "bridges_destroyable": true,
    "build_off_ally": true,
    "game_speed": 0,
    "map_path": "./pyra2yr/data/dry_heat.map",
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
      "side": "6",
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
    }
  ]
}
"""

PT_CONYARD = r"Yard"
PT_MCV = r"Construction\s+Vehicle"


class MyManager(Manager):
    async def deploy_mcvs(self):
        o = next(self.state.query_objects(p=PT_MCV, h=self.state.current_player()))
        await self.M.deploy(o.o)
        # wait until deployed
        await self.wait_state(
            lambda: len(list(self.state.query_objects(p=PT_CONYARD))) == 1
        )
        await self.wait_state(
            lambda: all(
                o.get().current_mission == ra2yr.Mission_Guard
                for o in self.state.query_objects(p=PT_CONYARD)
            )
        )

    async def sell_all_buildings(self):
        for o in self.state.query_objects(
            h=self.state.current_player(), a=ra2yr.ABSTRACT_TYPE_BUILDING
        ):
            await self.M.sell(objects=o.get())


async def amain():
    M = MyManager(port=14521)
    M.start()
    await M.M.wait_game_to_begin()
    await M.deploy_mcvs()
    await M.sell_all_buildings()
    await M.M.wait_game_to_exit()


G = Game(cfg=MultiGameInstanceConfig.from_dict(json.loads(cfg_json)))
atexit.register(G.stop)
G.start()
asyncio.run(amain())
