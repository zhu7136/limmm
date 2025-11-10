from __future__ import annotations

import torch
from typing import TYPE_CHECKING
from torch import nn

from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor , RayCaster

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv
    from isaaclab.managers.command_manager import CommandTerm

"""
Customized MDP terminations.
"""

# Cauclate the boundary of subterrain based on the env_origin_pos and sub_terrian_size
def base_out_of_subterrain(
    env: ManagerBasedRLEnv,
    tolerance: float = 1.0,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Terminate when the asset's position is out of the boundary of sub-terrain."""
    asset: RigidObject = env.scene[asset_cfg.name]
    root_pos = asset.data.root_pos_w[:, :2] # (num_envs, 2)
    env_origin_pos = env.scene.terrain.env_origins[:, :2] # (num_envs, 2)
    sub_terrian_size = torch.tensor(env.scene.terrain.cfg.terrain_generator.size, dtype=torch.float32,device=root_pos.device) # (x, y)
    # cant get border of each subterrain 

    lower_bound = env_origin_pos - sub_terrian_size * 0.5 * tolerance
    upper_bound = env_origin_pos + sub_terrian_size * 0.5 * tolerance

    # env_origin_pos = (-4, -4)  # For testing purposes
    # sub_terrian_size = 8.0  # For testing purposes
    # if robot_pos -8 < pos_x < 0 and -8 < pos_y < 0, then the robot is in the subterrain
    out_of_subterrain = torch.any((root_pos < lower_bound) | (root_pos > upper_bound), dim=1)

    return out_of_subterrain