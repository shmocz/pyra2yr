import asyncio
from pyra2yr.test_util import BaseGameTest


class BasicTest(BaseGameTest):
    async def test_basic(self):
        M0 = self.managers[0]

        for M in self.managers:
            await M.M.wait_game_to_begin()

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

        for M in self.managers:
            await M.sell_all_buildings()

        await M0.M.wait_game_to_exit()
