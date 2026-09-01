from __future__ import annotations

import torch
import warnings
from typing import TYPE_CHECKING, Literal
import random


import isaaclab.utils.math as math_utils
from isaaclab.assets import Articulation, RigidObject
from isaaclab.actuators import ImplicitActuator
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


def _randomize_prop_by_op(
    data: torch.Tensor,
    params: tuple[float, float],
    dim_0_ids: torch.Tensor | slice | None,
    dim_1_ids: torch.Tensor | slice | None,
    operation: Literal["add", "scale", "abs"],
    distribution: Literal["uniform", "log_uniform", "gaussian"],
) -> torch.Tensor:
    """Helper function to randomize a property by operation and distribution."""
    # Sample random values
    if distribution == "uniform":
        rand_vals = math_utils.sample_uniform(params[0], params[1], data[dim_0_ids, dim_1_ids].shape, device=data.device)
    elif distribution == "log_uniform":
        rand_vals = torch.exp(math_utils.sample_uniform(torch.log(torch.tensor(params[0])), torch.log(torch.tensor(params[1])), data[dim_0_ids, dim_1_ids].shape, device=data.device))
    elif distribution == "gaussian":
        mean, std = params
        rand_vals = torch.normal(mean, std, data[dim_0_ids, dim_1_ids].shape, device=data.device)
    else:
        raise ValueError(f"Unknown distribution: {distribution}")

    # Apply operation
    if operation == "add":
        data[dim_0_ids, dim_1_ids] += rand_vals
    elif operation == "scale":
        data[dim_0_ids, dim_1_ids] *= rand_vals
    elif operation == "abs":
        data[dim_0_ids, dim_1_ids] = rand_vals
    else:
        raise ValueError(f"Unknown operation: {operation}")
    
    return data


def randomize_actuator_gains_paired(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    asset_cfg: SceneEntityCfg,
    stiffness_distribution_params: tuple[float, float] | None = None,
    damping_distribution_params: tuple[float, float] | None = None,
    operation: Literal["add", "scale", "abs"] = "abs",
    distribution: Literal["uniform", "log_uniform", "gaussian"] = "uniform",
    joint_pairs: list[tuple[str, str]] | None = None,
):
    """Randomize actuator gains with paired left/right symmetry.
    
    For each (left_joint, right_joint) pair, sample ONE random value and apply 
    to both joints. This maintains left/right symmetry in actuator gains.
    
    Args:
        joint_pairs: List of (left_joint_name, right_joint_name) tuples. 
                     If None, attempts to auto-detect from "left_*" and "right_*" naming.
    """
    asset: Articulation = env.scene[asset_cfg.name]

    if env_ids is None:
        env_ids = torch.arange(env.scene.num_envs, device=asset.device)

    # Get all joint names and build name->index mapping
    joint_names = asset.joint_names
    name_to_idx = {name: i for i, name in enumerate(joint_names)}

    # Determine joint pairs
    if joint_pairs is None:
        # Auto-detect left/right pairs
        left_names = [n for n in joint_names if n.startswith("left_")]
        right_names = [n for n in joint_names if n.startswith("right_")]
        joint_pairs = []
        for ln in left_names:
            rn = ln.replace("left_", "right_")
            if rn in right_names:
                joint_pairs.append((ln, rn))

    # Loop through actuators and randomize gains
    for actuator in asset.actuators.values():
        # Get actuator joint indices
        if isinstance(actuator.joint_indices, slice):
            actuator_joint_ids = list(range(*actuator.joint_indices.indices(asset.num_joints)))
        else:
            actuator_joint_ids = list(actuator.joint_indices)

        # Filter to only joints in asset_cfg
        if asset_cfg.joint_ids != slice(None):
            asset_joint_ids = set(asset_cfg.joint_ids if isinstance(asset_cfg.joint_ids, list) else [asset_cfg.joint_ids])
            actuator_joint_ids = [j for j in actuator_joint_ids if j in asset_joint_ids]

        if not actuator_joint_ids:
            continue

        # Map joint indices to names for this actuator
        actuator_joint_names = [joint_names[j] for j in actuator_joint_ids]

        # Randomize stiffness
        if stiffness_distribution_params is not None:
            stiffness = actuator.stiffness[env_ids].clone()  # [num_envs, num_actuator_joints]
            
            # Reset to defaults first
            default_stiffness = asset.data.default_joint_stiffness[env_ids][:, actuator_joint_ids].clone()
            stiffness[:] = default_stiffness
            
            # Apply paired randomization
            for left_name, right_name in joint_pairs:
                if left_name in actuator_joint_names and right_name in actuator_joint_names:
                    left_local_idx = actuator_joint_names.index(left_name)
                    right_local_idx = actuator_joint_names.index(right_name)
                    
                    # Sample ONE value for the pair
                    if distribution == "uniform":
                        rand_val = math_utils.sample_uniform(
                            stiffness_distribution_params[0], stiffness_distribution_params[1],
                            (len(env_ids),), device=asset.device
                        )
                    elif distribution == "log_uniform":
                        rand_val = torch.exp(math_utils.sample_uniform(
                            torch.log(torch.tensor(stiffness_distribution_params[0])), 
                            torch.log(torch.tensor(stiffness_distribution_params[1])),
                            (len(env_ids),), device=asset.device
                        ))
                    elif distribution == "gaussian":
                        rand_val = torch.normal(
                            stiffness_distribution_params[0], stiffness_distribution_params[1],
                            (len(env_ids),), device=asset.device
                        )
                    
                    # Apply to both left and right
                    if operation == "add":
                        stiffness[:, left_local_idx] += rand_val
                        stiffness[:, right_local_idx] += rand_val
                    elif operation == "scale":
                        stiffness[:, left_local_idx] *= rand_val
                        stiffness[:, right_local_idx] *= rand_val
                    elif operation == "abs":
                        stiffness[:, left_local_idx] = rand_val
                        stiffness[:, right_local_idx] = rand_val

            actuator.stiffness[env_ids] = stiffness
            if isinstance(actuator, ImplicitActuator):
                asset.write_joint_stiffness_to_sim(stiffness, joint_ids=actuator.joint_indices, env_ids=env_ids)

        # Randomize damping (same logic)
        if damping_distribution_params is not None:
            damping = actuator.damping[env_ids].clone()
            
            default_damping = asset.data.default_joint_damping[env_ids][:, actuator_joint_ids].clone()
            damping[:] = default_damping
            
            for left_name, right_name in joint_pairs:
                if left_name in actuator_joint_names and right_name in actuator_joint_names:
                    left_local_idx = actuator_joint_names.index(left_name)
                    right_local_idx = actuator_joint_names.index(right_name)
                    
                    if distribution == "uniform":
                        rand_val = math_utils.sample_uniform(
                            damping_distribution_params[0], damping_distribution_params[1],
                            (len(env_ids),), device=asset.device
                        )
                    elif distribution == "log_uniform":
                        rand_val = torch.exp(math_utils.sample_uniform(
                            torch.log(torch.tensor(damping_distribution_params[0])), 
                            torch.log(torch.tensor(damping_distribution_params[1])),
                            (len(env_ids),), device=asset.device
                        ))
                    elif distribution == "gaussian":
                        rand_val = torch.normal(
                            damping_distribution_params[0], damping_distribution_params[1],
                            (len(env_ids),), device=asset.device
                        )
                    
                    if operation == "add":
                        damping[:, left_local_idx] += rand_val
                        damping[:, right_local_idx] += rand_val
                    elif operation == "scale":
                        damping[:, left_local_idx] *= rand_val
                        damping[:, right_local_idx] *= rand_val
                    elif operation == "abs":
                        damping[:, left_local_idx] = rand_val
                        damping[:, right_local_idx] = rand_val

            actuator.damping[env_ids] = damping
            if isinstance(actuator, ImplicitActuator):
                asset.write_joint_damping_to_sim(damping, joint_ids=actuator.joint_indices, env_ids=env_ids)
