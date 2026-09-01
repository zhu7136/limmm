from __future__ import annotations

import torch
from typing import TYPE_CHECKING
from torch import nn

from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor, RayCaster

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv
    from isaaclab.managers.command_manager import CommandTerm


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


def inter_leg_collision_termination(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    force_threshold: float,
    left_body_names: list[str],
    right_body_names: list[str],
    consecutive_steps: int = 3,
) -> torch.Tensor:
    """Terminate episode when left and right legs have continuous contact for N steps.
    
    Uses force_matrix_w for true pairwise contact detection.
    Falls back to net_forces_w if force_matrix_w is not available.
    Tracks consecutive contact steps per environment.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    
    asset: RigidObject = env.scene["robot"]
    left_indices = [asset.data.body_names.index(name) for name in left_body_names]
    right_indices = [asset.data.body_names.index(name) for name in right_body_names]
    
    # Try force_matrix_w first (true pairwise), fallback to net_forces_w heuristic
    force_matrix = contact_sensor.data.force_matrix_w
    
    contact_any = torch.zeros(env.num_envs, device=env.device, dtype=torch.bool)
    
    if force_matrix is not None:
        # True pairwise contact detection using force_matrix_w
        for l_idx in left_indices:
            for r_idx in right_indices:
                pair_force = torch.norm(force_matrix[:, l_idx, r_idx], dim=-1)
                pair_force_rev = torch.norm(force_matrix[:, r_idx, l_idx], dim=-1)
                total_pair_force = pair_force + pair_force_rev
                contact_any |= (total_pair_force > force_threshold)
    else:
        # Fallback: check if both left and right bodies have significant contact simultaneously
        # This is less accurate but better than nothing
        net_forces = contact_sensor.data.net_forces_w
        if net_forces is not None:
            for l_idx in left_indices:
                for r_idx in right_indices:
                    l_force = torch.norm(net_forces[:, l_idx], dim=-1)
                    r_force = torch.norm(net_forces[:, r_idx], dim=-1)
                    both_contact = (l_force > force_threshold) & (r_force > force_threshold)
                    contact_any |= both_contact
        else:
            # No contact data available, skip termination
            return torch.zeros(env.num_envs, device=env.device, dtype=torch.bool)
    
    # Track consecutive steps using a buffer in env
    if not hasattr(env, "_inter_leg_contact_steps"):
        env._inter_leg_contact_steps = torch.zeros(env.num_envs, device=env.device, dtype=torch.long)
    
    env._inter_leg_contact_steps = torch.where(
        contact_any,
        env._inter_leg_contact_steps + 1,
        torch.zeros_like(env._inter_leg_contact_steps)
    )
    
    # Terminate if consecutive steps exceeded
    terminate = env._inter_leg_contact_steps >= consecutive_steps
    
    # Reset counter for terminated envs
    env._inter_leg_contact_steps[terminate] = 0
    
    return terminate