import asyncio
from pyra2yr.test_util import BaseGameTest


class BasicTest(BaseGameTest):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        for _, M in self.all_managers:
            await M.M.wait_game_to_begin()

    async def asyncTearDown(self):
        for _, M in self.all_managers:
            await M.M.wait_game_to_exit(20)
        await super().asyncTearDown()

    async def test_mcv_deploy_sell(self):
        async with asyncio.TaskGroup() as tg:
            for M in self.managers:
                tg.create_task(M.deploy_mcv())

        # FIXME: yrpp-spawner freezes at game exit if this is used
        for M in self.managers:
            await M.sell_all_buildings()

    async def test_basic_build(self):
        async with asyncio.TaskGroup() as tg:
            for M in self.managers:
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
                for M in self.managers:
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
                    # FIXME: Small delay to avoid buggy dupe event check for DoList
                    await asyncio.sleep(0.5)

        # FIXME: yrpp-spawner freezes at game exit if this is used
        for M in self.managers:
            await M.sell_all_buildings()
