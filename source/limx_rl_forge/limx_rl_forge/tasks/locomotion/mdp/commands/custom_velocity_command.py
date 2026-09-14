from __future__ import annotations

import torch
from enum import IntEnum
from isaaclab.envs.mdp.commands.velocity_command import UniformVelocityCommand
from isaaclab.envs.mdp.commands.commands_cfg import UniformVelocityCommandCfg
from isaaclab.managers import CommandTermCfg
from isaaclab.utils import configclass
from dataclasses import MISSING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv


class EnvMode(IntEnum):
    """环境模式枚举"""
    STRAIGHT = 0      # 高速直线模式
    PERTURBED = 1     # 轻微方向扰动模式
    LOW_SPEED = 2     # 低速和恢复状态模式


class BiasedVelocityCommand(UniformVelocityCommand):
    """Velocity command with multiple environment modes."""

    def __init__(self, cfg: UniformVelocityCommandCfg, env: ManagerBasedEnv):
        super().__init__(cfg, env)
        # 环境模式标记
        self.env_mode = torch.zeros(self.num_envs, dtype=torch.long, device=self.device)
        # 直线模式的初始heading和位置（用于路径奖励）
        self.straight_heading_target = torch.zeros(self.num_envs, device=self.device)
        self.straight_init_pos = torch.zeros(self.num_envs, 2, device=self.device)
        # 是否是直线模式环境
        self.is_straight_env = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        # 直线模式是否已初始化（heading固定后不再重采样）
        self.straight_initialized = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)


@configclass
class BiasedVelocityCommandCfg(UniformVelocityCommandCfg):
    """Configuration for biased velocity command."""
    class_type = BiasedVelocityCommand

    # 三种环境模式的概率
    straight_prob: float = 0.7      # 70% 高速直线
    perturbed_prob: float = 0.2     # 20% 轻微方向扰动
    low_speed_prob: float = 0.1     # 10% 低速和恢复状态

    # 高速直线模式参数
    straight_speed_range: tuple[float, float] = (2.6, 3.0)

    # 轻微方向扰动模式参数
    perturbed_vy_range: tuple[float, float] = (-0.03, 0.03)
    perturbed_yaw_rate_range: tuple[float, float] = (-0.05, 0.05)

    # 低速模式参数
    low_speed_range: tuple[float, float] = (-0.5, 1.0)


def _resample_command(self, env_ids):
    r = torch.empty(len(env_ids), device=self.device)

    # 按概率决定环境模式
    mode_rand = r.uniform_(0.0, 1.0)
    is_straight = mode_rand < self.cfg.straight_prob
    is_perturbed = (mode_rand >= self.cfg.straight_prob) & (mode_rand < self.cfg.straight_prob + self.cfg.perturbed_prob)
    is_low_speed = ~is_straight & ~is_perturbed

    # 记录环境模式
    self.env_mode[env_ids[is_straight]] = EnvMode.STRAIGHT
    self.env_mode[env_ids[is_perturbed]] = EnvMode.PERTURBED
    self.env_mode[env_ids[is_low_speed]] = EnvMode.LOW_SPEED
    self.is_straight_env[env_ids] = is_straight

    # 高速直线模式：vx=2.6-3.0, vy=0, ang_vel=0, 固定heading
    straight_ids = env_ids[is_straight]
    if len(straight_ids) > 0:
        r_straight = torch.empty(len(straight_ids), device=self.device)
        self.vel_command_b[straight_ids, 0] = r_straight.uniform_(*self.cfg.straight_speed_range)
        self.vel_command_b[straight_ids, 1] = 0.0  # vy = 0
        self.vel_command_b[straight_ids, 2] = 0.0  # ang_vel = 0
        # 记录初始heading和位置（用于路径奖励）
        self.straight_heading_target[straight_ids] = self.robot.data.heading_w[straight_ids]
        self.straight_init_pos[straight_ids] = self.robot.data.root_pos_w[straight_ids, :2]
        self.straight_initialized[straight_ids] = True

    # 轻微方向扰动模式
    perturbed_ids = env_ids[is_perturbed]
    if len(perturbed_ids) > 0:
        r_perturbed = torch.empty(len(perturbed_ids), device=self.device)
        self.vel_command_b[perturbed_ids, 0] = r_perturbed.uniform_(*self.cfg.straight_speed_range)
        self.vel_command_b[perturbed_ids, 1] = r_perturbed.uniform_(*self.cfg.perturbed_vy_range)
        self.vel_command_b[perturbed_ids, 2] = r_perturbed.uniform_(*self.cfg.perturbed_yaw_rate_range)

    # 低速模式
    low_speed_ids = env_ids[is_low_speed]
    if len(low_speed_ids) > 0:
        r_low = torch.empty(len(low_speed_ids), device=self.device)
        self.vel_command_b[low_speed_ids, 0] = r_low.uniform_(*self.cfg.low_speed_range)
        self.vel_command_b[low_speed_ids, 1] = 0.0
        self.vel_command_b[low_speed_ids, 2] = 0.0

    # 对于非直线模式，使用默认的heading采样
    non_straight_ids = env_ids[~is_straight]
    if len(non_straight_ids) > 0 and self.cfg.heading_command:
        r_non_straight = torch.empty(len(non_straight_ids), device=self.device)
        self.heading_target[non_straight_ids] = r_non_straight.uniform_(*self.cfg.ranges.heading)
        self.is_heading_env[non_straight_ids] = r_non_straight.uniform_(0.0, 1.0) <= self.cfg.rel_heading_envs

    # standing环境处理
    self.is_standing_env[env_ids] = r.uniform_(0.0, 1.0) <= self.cfg.rel_standing_envs


def _update_command(self):
    """Post-processes the velocity command."""
    import isaaclab.utils.math as math_utils

    # 直线模式：heading在整个episode固定，不受resampling_time_range影响
    straight_env_ids = self.is_straight_env.nonzero(as_tuple=False).flatten()
    if len(straight_env_ids) > 0:
        # 计算heading error并生成角速度指令
        heading_error = math_utils.wrap_to_pi(
            self.straight_heading_target[straight_env_ids] - self.robot.data.heading_w[straight_env_ids]
        )
        self.vel_command_b[straight_env_ids, 2] = torch.clip(
            self.cfg.heading_control_stiffness * heading_error,
            min=self.cfg.ranges.ang_vel_z[0],
            max=self.cfg.ranges.ang_vel_z[1],
        )

    # 非直线模式：使用默认的heading控制
    non_straight_env_ids = (~self.is_straight_env).nonzero(as_tuple=False).flatten()
    if len(non_straight_env_ids) > 0 and self.cfg.heading_command:
        heading_error = math_utils.wrap_to_pi(
            self.heading_target[non_straight_env_ids] - self.robot.data.heading_w[non_straight_env_ids]
        )
        self.vel_command_b[non_straight_env_ids, 2] = torch.clip(
            self.cfg.heading_control_stiffness * heading_error,
            min=self.cfg.ranges.ang_vel_z[0],
            max=self.cfg.ranges.ang_vel_z[1],
        )

    # Enforce standing (i.e., zero velocity command) for standing envs
    standing_env_ids = self.is_standing_env.nonzero(as_tuple=False).flatten()
    self.vel_command_b[standing_env_ids, :] = 0.0


BiasedVelocityCommand._resample_command = _resample_command
BiasedVelocityCommand._update_command = _update_command
