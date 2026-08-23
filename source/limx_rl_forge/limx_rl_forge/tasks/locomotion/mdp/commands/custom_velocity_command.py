import torch
from isaaclab.envs.mdp.commands.velocity_command import UniformVelocityCommand
from isaaclab.envs.mdp.commands.commands_cfg import UniformVelocityCommandCfg
from isaaclab.managers import CommandTermCfg
from isaaclab.utils import configclass
from dataclasses import MISSING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedEnv


class BiasedVelocityCommand(UniformVelocityCommand):
    """Velocity command with biased sampling toward high speed range."""
    pass


@configclass
class BiasedVelocityCommandCfg(UniformVelocityCommandCfg):
    """Configuration for biased velocity command."""
    class_type = BiasedVelocityCommand

    # Custom biased sampling fields
    high_speed_prob: float = 0.7
    high_speed_range: tuple[float, float] = (1.0, 2.0)
    low_speed_range: tuple[float, float] = (-0.5, 1.0)


# Now add the method to the class
def _resample_command(self, env_ids):
    r = torch.empty(len(env_ids), device=self.device)
    # 按概率决定从哪个区间采样
    use_high = r.uniform_(0.0, 1.0) < self.cfg.high_speed_prob
    # 低速区间
    low_ids = env_ids[~use_high]
    if len(low_ids) > 0:
        r_low = torch.empty(len(low_ids), device=self.device)
        self.vel_command_b[low_ids, 0] = r_low.uniform_(*self.cfg.low_speed_range)
    # 高速区间
    high_ids = env_ids[use_high]
    if len(high_ids) > 0:
        r_high = torch.empty(len(high_ids), device=self.device)
        self.vel_command_b[high_ids, 0] = r_high.uniform_(*self.cfg.high_speed_range)
    # y, yaw 保持原有均匀采样
    self.vel_command_b[env_ids, 1] = r.uniform_(*self.cfg.ranges.lin_vel_y)
    self.vel_command_b[env_ids, 2] = r.uniform_(*self.cfg.ranges.ang_vel_z)
    # heading / standing 逻辑保持不变
    if self.cfg.heading_command:
        self.heading_target[env_ids] = r.uniform_(*self.cfg.ranges.heading)
        self.is_heading_env[env_ids] = r.uniform_(0.0, 1.0) <= self.cfg.rel_heading_envs
    self.is_standing_env[env_ids] = r.uniform_(0.0, 1.0) <= self.cfg.rel_standing_envs

BiasedVelocityCommand._resample_command = _resample_command