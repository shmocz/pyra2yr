import numpy as np
from pyra2yr.test_util import BaseGameTest, SingleStepManager
from pyra2yr.game import Game
from pyra2yr.util import setup_logging


class SingleStepTest(BaseGameTest):
    async def asyncSetUp(self):
        setup_logging()

    async def asyncTearDown(self):
        pass

    async def run_one(self, max_frames: int):
        with Game(cfg=self.get_test_config()):
            M = SingleStepManager(port=14521)
            M.start()
            q = await M.M.set_single_step(True)
            self.assertTrue(q.single_step)
            await M.wait_state(lambda: M.state.s.current_frame >= max_frames)
            await M.deploy_mcv()
            await M.sell_all_buildings()
            await M.M.wait_game_to_exit()
            await M.stop()
            return M

    async def test_single_step(self):
        crcs = []
        max_frames = 60
        for _ in range(2):
            M = await self.run_one(max_frames)
            crcs.append(M.crcs[:max_frames])
        X = np.array(crcs)
        self.assertTrue(np.all(X[0, :] == X[1, :]))
