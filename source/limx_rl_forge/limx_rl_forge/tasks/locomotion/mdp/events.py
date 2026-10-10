from __future__ import annotations

import torch
import warnings
from typing import TYPE_CHECKING, Literal
import random


import isaaclab.utils.math as math_utils
from isaaclab.actuators import ImplicitActuator
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


def _sample_distribution(
    distribution_params: tuple[float, float],
    size: tuple[int, ...],
    distribution: str,
    device: str,
) -> torch.Tensor:
    """Sample values from the requested distribution. Mirrors IsaacLab's internal helper."""
    if distribution == "uniform":
        dist_fn = math_utils.sample_uniform
    elif distribution == "log_uniform":
        dist_fn = math_utils.sample_log_uniform
    elif distribution == "gaussian":
        dist_fn = math_utils.sample_gaussian
    else:
        raise NotImplementedError(
            f"Unknown distribution: '{distribution}'. Please use 'uniform', 'log_uniform' or 'gaussian'."
        )
    return dist_fn(*distribution_params, size, device=device)


def _resolve_ids(env, env_ids, num_items, ids, device: str):
    """Resolve environment ids and item (body/joint) ids."""
    if env_ids is None:
        env_ids = torch.arange(env.scene.num_envs, device=device)
    else:
        env_ids = env_ids.cpu()
    if isinstance(ids, slice):
        item_ids = torch.arange(num_items, dtype=torch.int, device=device)
    else:
        item_ids = torch.tensor(ids, dtype=torch.int, device=device)
    return env_ids, item_ids


def _randomize_by_op(
    data: torch.Tensor,
    env_ids: torch.Tensor,
    item_ids: torch.Tensor,
    distribution_params: tuple[float, float],
    operation: str,
    distribution: str,
) -> torch.Tensor:
    """Apply `operation` (add/scale/abs) on data[env_ids][:, item_ids] with freshly sampled values."""
    samples = _sample_distribution(
        distribution_params, (len(env_ids), len(item_ids)), distribution, device=data.device
    )
    if operation == "add":
        data[env_ids[:, None], item_ids] += samples
    elif operation == "scale":
        data[env_ids[:, None], item_ids] *= samples
    elif operation == "abs":
        data[env_ids[:, None], item_ids] = samples
    else:
        raise NotImplementedError(
            f"Unknown operation: '{operation}'. Please use 'add', 'scale' or 'abs'."
        )
    return data


def randomize_rigid_body_mass(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    asset_cfg: SceneEntityCfg,
    mass_distribution_params: tuple[float, float],
    operation: Literal["add", "scale", "abs"],
    distribution: Literal["uniform", "log_uniform", "gaussian"] = "uniform",
    recompute_inertia: bool = True,
    min_mass: float = 1e-6,
):
    """Function-based re-implementation of IsaacLab's ``randomize_rigid_body_mass``.

    Needed because recent IsaacLab versions ship this term as a class, which is only usable
    with ``mode="prestartup"`` (which in turn requires disabling scene replication).
    """
    asset: RigidObject | Articulation = env.scene[asset_cfg.name]
    env_ids, body_ids = _resolve_ids(env, env_ids, asset.num_bodies, asset_cfg.body_ids, device="cpu")

    # get the current masses of the bodies (num_assets, num_bodies)
    masses = asset.root_physx_view.get_masses()

    # randomize the default values (avoids compounding over multiple calls)
    masses[env_ids[:, None], body_ids] = (
        asset.data.default_mass[env_ids[:, None], body_ids].clone().to(device=masses.device)
    )
    masses = _randomize_by_op(
        masses, env_ids, body_ids, mass_distribution_params, operation=operation, distribution=distribution
    )
    masses = torch.clamp(masses, min=min_mass)  # ensure masses stay positive

    # set the mass into the physics simulation
    asset.root_physx_view.set_masses(masses, env_ids)

    # recompute inertia tensors if needed
    if recompute_inertia:
        # since mass randomization is done on default values, we can use the default inertia tensors
        ratios = masses[env_ids[:, None], body_ids] / asset.data.default_mass[env_ids[:, None], body_ids].to(
            device=masses.device
        )
        inertias = asset.root_physx_view.get_inertias()
        if isinstance(asset, Articulation):
            # inertia has shape: (num_envs, num_bodies, 9) for articulation
            inertias[env_ids[:, None], body_ids] = (
                asset.data.default_inertia[env_ids[:, None], body_ids].to(device=inertias.device) * ratios[..., None]
            )
        else:
            # inertia has shape: (num_envs, 9) for rigid object
            inertias[env_ids] = asset.data.default_inertia[env_ids].to(device=inertias.device) * ratios
        asset.root_physx_view.set_inertias(inertias, env_ids)


def randomize_rigid_body_material(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    asset_cfg: SceneEntityCfg,
    static_friction_range: tuple[float, float] = (1.0, 1.0),
    dynamic_friction_range: tuple[float, float] = (1.0, 1.0),
    restitution_range: tuple[float, float] = (0.0, 0.0),
    num_buckets: int = 1,
    make_consistent: bool = False,
):
    """Function-based re-implementation of IsaacLab's ``randomize_rigid_body_material``.

    The material buckets are sampled once per asset and then reused, matching the original behavior.
    """
    asset: RigidObject | Articulation = env.scene[asset_cfg.name]
    if not isinstance(asset, (RigidObject, Articulation)):
        raise ValueError(
            f"Randomization term 'randomize_rigid_body_material' not supported for asset: '{asset_cfg.name}'"
            f" with type: '{type(asset)}'."
        )

    env_ids, _ = _resolve_ids(env, env_ids, asset.num_bodies, asset_cfg.body_ids, device="cpu")

    # obtain number of shapes per body (needed for indexing the material properties correctly)
    if isinstance(asset, Articulation) and asset_cfg.body_ids != slice(None):
        num_shapes_per_body = getattr(asset, "_rand_num_shapes_per_body", None)
        if num_shapes_per_body is None:
            num_shapes_per_body = []
            for link_path in asset.root_physx_view.link_paths[0]:
                link_physx_view = asset._physics_sim_view.create_rigid_body_view(link_path)  # type: ignore
                num_shapes_per_body.append(link_physx_view.max_shapes)
            # ensure the parsing is correct
            if sum(num_shapes_per_body) != asset.root_physx_view.max_shapes:
                raise ValueError(
                    "Randomization term 'randomize_rigid_body_material' failed to parse the number of shapes per body."
                    f" Expected total shapes: {asset.root_physx_view.max_shapes}, but got: {sum(num_shapes_per_body)}."
                )
            asset._rand_num_shapes_per_body = num_shapes_per_body
    else:
        num_shapes_per_body = None

    # sample the material buckets only once, afterwards they are randomly assigned to the geometries
    bucket_key = (static_friction_range, dynamic_friction_range, restitution_range, int(num_buckets), make_consistent)
    cache = getattr(asset, "_rand_material_buckets", None)
    if cache is None or cache[0] != bucket_key:
        range_list = [static_friction_range, dynamic_friction_range, restitution_range]
        ranges = torch.tensor(range_list, device="cpu")
        material_buckets = math_utils.sample_uniform(
            ranges[:, 0], ranges[:, 1], (int(num_buckets), 3), device="cpu"
        )
        # ensure dynamic friction is always less than static friction
        if make_consistent:
            material_buckets[:, 1] = torch.min(material_buckets[:, 0], material_buckets[:, 1])
        asset._rand_material_buckets = (bucket_key, material_buckets)
    else:
        material_buckets = cache[1]

    # randomly assign material IDs to the geometries
    total_num_shapes = asset.root_physx_view.max_shapes
    bucket_ids = torch.randint(0, int(num_buckets), (len(env_ids), total_num_shapes), device="cpu")
    material_samples = material_buckets[bucket_ids]

    # retrieve material buffer from the physics simulation
    materials = asset.root_physx_view.get_material_properties()

    # update material buffer with new samples
    if num_shapes_per_body is not None:
        for body_id in asset_cfg.body_ids:
            start_idx = sum(num_shapes_per_body[:body_id])
            end_idx = start_idx + num_shapes_per_body[body_id]
            materials[env_ids, start_idx:end_idx] = material_samples[:, start_idx:end_idx]
    else:
        materials[env_ids] = material_samples[:]

    # apply to simulation
    asset.root_physx_view.set_material_properties(materials, env_ids)


def randomize_actuator_gains(
    env: ManagerBasedEnv,
    env_ids: torch.Tensor | None,
    asset_cfg: SceneEntityCfg,
    stiffness_distribution_params: tuple[float, float] | None = None,
    damping_distribution_params: tuple[float, float] | None = None,
    operation: Literal["add", "scale", "abs"] = "abs",
    distribution: Literal["uniform", "log_uniform", "gaussian"] = "uniform",
):
    """Function-based re-implementation of IsaacLab's ``randomize_actuator_gains``."""
    asset: Articulation = env.scene[asset_cfg.name]
    if env_ids is None:
        env_ids = torch.arange(env.scene.num_envs, device=asset.device)

    def randomize(data: torch.Tensor, params: tuple[float, float]) -> torch.Tensor:
        indices = actuator_indices
        n_dim_1 = data.shape[1] if isinstance(indices, slice) else len(indices)
        samples = _sample_distribution(params, (data.shape[0], n_dim_1), distribution, device=data.device)
        if operation == "add":
            data[:, indices] += samples
        elif operation == "scale":
            data[:, indices] *= samples
        elif operation == "abs":
            data[:, indices] = samples
        else:
            raise NotImplementedError(
                f"Unknown operation: '{operation}'. Please use 'add', 'scale' or 'abs'."
            )
        return data

    # loop through actuators and randomize gains
    for actuator in asset.actuators.values():
        if isinstance(asset_cfg.joint_ids, slice):
            # we take all the joints of the actuator
            actuator_indices = slice(None)
            if isinstance(actuator.joint_indices, slice):
                global_indices = slice(None)
            elif isinstance(actuator.joint_indices, torch.Tensor):
                global_indices = actuator.joint_indices.to(asset.device)
            else:
                raise TypeError("Actuator joint indices must be a slice or a torch.Tensor.")
        elif isinstance(actuator.joint_indices, slice):
            # we take the joints defined in the asset config
            global_indices = actuator_indices = torch.tensor(asset_cfg.joint_ids, device=asset.device)
        else:
            # we take the intersection of the actuator joints and the asset config joints
            actuator_joint_indices = actuator.joint_indices
            asset_joint_ids = torch.tensor(asset_cfg.joint_ids, device=asset.device)
            actuator_indices = torch.nonzero(torch.isin(actuator_joint_indices, asset_joint_ids)).view(-1)
            if len(actuator_indices) == 0:
                continue
            global_indices = actuator_joint_indices[actuator_indices]

        # randomize stiffness
        if stiffness_distribution_params is not None:
            stiffness = actuator.stiffness[env_ids].clone()
            stiffness[:, actuator_indices] = asset.data.default_joint_stiffness[env_ids][:, global_indices].clone()
            randomize(stiffness, stiffness_distribution_params)
            actuator.stiffness[env_ids] = stiffness
            if isinstance(actuator, ImplicitActuator):
                asset.write_joint_stiffness_to_sim(stiffness, joint_ids=actuator.joint_indices, env_ids=env_ids)
        # randomize damping
        if damping_distribution_params is not None:
            damping = actuator.damping[env_ids].clone()
            damping[:, actuator_indices] = asset.data.default_joint_damping[env_ids][:, global_indices].clone()
            randomize(damping, damping_distribution_params)
            actuator.damping[env_ids] = damping
            if isinstance(actuator, ImplicitActuator):
                asset.write_joint_damping_to_sim(damping, joint_ids=actuator.joint_indices, env_ids=env_ids)
