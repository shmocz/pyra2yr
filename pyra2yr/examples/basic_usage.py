#!/usr/bin/env python3
import asyncio
import json

from pyra2yr.game import Game, MultiGameInstanceConfig
from pyra2yr.test_util import ExManager, cfg_json


def get_config():
    return MultiGameInstanceConfig.from_dict(json.loads(cfg_json))


async def basic_test():
    with Game(cfg=get_config()):
        managers = []
        for i in range(2):
            M = ExManager(port=14521 + i)
            M.start()
            managers.append(M)

        for M in managers:
            await M.M.wait_game_to_begin()

        async with asyncio.TaskGroup() as tg:
            for M in managers:
                tg.create_task(M.deploy_mcv())

        # build stuff
        for bkey in [
            "power",
            "barracks",
            "refinery",
            "war_factory",
            "radar",
            "battle_lab",
        ]:
            async with asyncio.TaskGroup() as tg:
                for M in managers:
                    o_mcv = next(
                        M.state.query_objects(
                            t=M.buildable_types.conyard, h=M.state.current_player()
                        )
                    )
                    tg.create_task(
                        M.produce_and_place(
                            getattr(M.buildable_types, bkey), o_mcv.coordinates
                        )
                    )
        await M.M.wait_game_to_exit(timeout=3600)
        await M.stop()


asyncio.run(basic_test())
