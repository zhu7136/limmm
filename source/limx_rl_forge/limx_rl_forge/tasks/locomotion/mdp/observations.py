from __future__ import annotations

import torch
from typing import TYPE_CHECKING

from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor, RayCaster

from .gait import gait_handler

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv

# TODO, use the height information to fulfill the scan mat 
def scan_matrix(env: ManagerBasedRLEnv, row : int = 17, col : int = 11):
    scan_mat = torch.zeros(env.num_envs, row * col, device=env.device, dtype = torch.float)
    return scan_mat

def robot_mass(env: ManagerBasedRLEnv, robot_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    robot : RigidObject = env.scene[robot_cfg.name]
    masses = robot.data._root_physx_view.get_masses()
    return masses.to(env.device)

def gait_observation(env: ManagerBasedRLEnv, frequency_range, offset_range, height_range):
    # init gait
    if gait_handler.get_init_flag() == False:
        gait_handler.init(kappa=0.05, num_envs=env.num_envs, device=env.device, frequency_range = frequency_range, offset_range = offset_range, height_range = height_range)
    
    gait_phase = gait_handler.get_phase()
    gait_info = gait_handler.get_gait_info()

    cmd = env.command_manager.get_command("base_velocity")
    stand_still_flag = gait_handler.get_stand_still_flag()
    stand_still_flag[:] = torch.norm(cmd[:, :3], dim=-1) < 0.1
        
    dt = env.cfg.sim.dt * env.cfg.decimation
    gait_phase[:] = torch.remainder(gait_phase + dt * (~stand_still_flag) * gait_info[:, 0], 1.0)
    
    if hasattr(env, "reset_buf"):
        reset_idx = env.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        gait_phase[reset_idx] = (torch.rand(len(reset_idx), device=env.device) > 0.5) * 0.5
        gait_info[reset_idx, 0] = torch.rand(len(reset_idx), device=env.device) * (frequency_range[1] - frequency_range[0]) + frequency_range[0] 
        gait_info[reset_idx, 1] = torch.rand(len(reset_idx), device=env.device) * (offset_range[1] - offset_range[0]) + offset_range[0]
        gait_info[reset_idx, 2] = torch.rand(len(reset_idx), device=env.device) * (height_range[1] - height_range[0]) + height_range[0]
    
    stand_still_idx = stand_still_flag.nonzero(as_tuple=False).flatten()
    gait_phase[stand_still_idx] = (gait_phase[stand_still_idx] >= 0.5) * 0.5
    
    gait_info[:, 3] = torch.sin(2. * torch.pi * gait_phase)
    gait_info[:, 4] = torch.cos(2. * torch.pi * gait_phase)
    
    gait_handler.reference_compute()

    return gait_info

def gait_des_foot_height(env: ManagerBasedRLEnv):
    des_foot_height = gait_handler.get_desired_foot_height()
    return des_foot_height.reshape(env.num_envs, -1)

def gait_des_foot_vel(env: ManagerBasedRLEnv):
    des_foot_vel = gait_handler.get_desired_foot_velocity()
    return des_foot_vel.reshape(env.num_envs, -1)


def joint_torque(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """The joint torques of the asset."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    return asset.data.applied_torque[:, asset_cfg.joint_ids]

def joint_acc(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """The joint acceleration of the asset."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    return asset.data.joint_acc[:, asset_cfg.joint_ids]


def foot_speed_norm(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    foot_vel = asset.data.body_lin_vel_w[:, asset_cfg.body_ids, :2]
    foot_speed_norm = torch.norm(foot_vel, dim=2)
    return foot_speed_norm.reshape(env.num_envs, -1)

def foot_speed_z(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    foot_vel_z = asset.data.body_lin_vel_w[:, asset_cfg.body_ids, 2]
    return foot_vel_z.reshape(env.num_envs, -1)

def foot_speed(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    foot_vel = asset.data.body_lin_vel_w[:, asset_cfg.body_ids]
    return foot_vel.reshape(env.num_envs, -1)

def contact_forces_state(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg = SceneEntityCfg) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contact_forces = contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids]
    return contact_forces.reshape(env.num_envs, -1)