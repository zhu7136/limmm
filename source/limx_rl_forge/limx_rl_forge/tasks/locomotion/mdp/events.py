from __future__ import annotations

import torch
import warnings
from typing import TYPE_CHECKING, Literal
import random


import isaaclab.utils.math as math_utils
from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import RayCaster

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv

def randomize_rigid_body_centroid(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    z_range: tuple[float, float],
    asset_cfg: SceneEntityCfg,
):
    # extract the used quantities (to enable type-hinting)
    asset: RigidObject | Articulation = env.scene[asset_cfg.name]

    # resolve environment ids
    if env_ids is None:
        env_ids = torch.arange(env.scene.num_envs, device="cpu")
    else:
        env_ids = env_ids.cpu()
        
    # resolve body indices
    if asset_cfg.body_ids == slice(None):
        body_ids = torch.arange(asset.num_bodies, dtype=torch.int, device="cpu")
    else:
        body_ids = torch.tensor(asset_cfg.body_ids, dtype=torch.int, device="cpu")

    centroid = asset.root_physx_view.get_coms()
    size = centroid[env_ids[:, None], body_ids, 0].size()
    centroid[env_ids[:, None], body_ids, 0] += math_utils.sample_uniform(x_range[0], x_range[1], size, device="cpu")
    centroid[env_ids[:, None], body_ids, 1] += math_utils.sample_uniform(y_range[0], y_range[1], size, device="cpu")
    centroid[env_ids[:, None], body_ids, 2] += math_utils.sample_uniform(z_range[0], z_range[1], size, device="cpu")
    
    asset.root_physx_view.set_coms(centroid, env_ids)

def randomize_rigid_body_inertia(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    scale: tuple[float, float],
    asset_cfg: SceneEntityCfg,
):
    # extract the used quantities (to enable type-hinting)
    asset: RigidObject | Articulation = env.scene[asset_cfg.name]

    # resolve environment ids
    if env_ids is None:
        env_ids = torch.arange(env.scene.num_envs, device="cpu")
    else:
        env_ids = env_ids.cpu()
        
    # resolve body indices
    if asset_cfg.body_ids == slice(None):
        body_ids = torch.arange(asset.num_bodies, dtype=torch.int, device="cpu")
    else:
        body_ids = torch.tensor(asset_cfg.body_ids, dtype=torch.int, device="cpu")
        
    inertias = asset.root_physx_view.get_inertias()
    size = inertias[env_ids[:, None], body_ids].size()
    
    inertias[env_ids[:, None], body_ids] *= math_utils.sample_uniform(scale[0], scale[1], size, device="cpu")
    
    asset.root_physx_view.set_inertias(inertias, env_ids)
