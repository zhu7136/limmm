from __future__ import annotations

import torch
from typing import TYPE_CHECKING

from isaaclab.assets import Articulation, RigidObject
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor, RayCaster
import isaaclab.utils.math as math_utils

from isaaclab.envs.mdp import track_lin_vel_xy_exp, track_ang_vel_z_exp

from .gait import gait_handler

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


class DataCache:
    def __init__(self):
        self.initialized_flag = False
        return

    def get_init_flag(self):
        return self.initialized_flag

    def init(self, num_envs, device):
        self.des_hand_positions_x = torch.zeros(num_envs, 2, dtype=torch.float, device=device, requires_grad=False)
        self.des_hand_velocity_x = torch.zeros(num_envs, 2, dtype=torch.float, device=device, requires_grad=False)
        self.last_lin_tracking_reward = torch.zeros(num_envs, dtype=torch.float, device=device, requires_grad=False)
        self.last_ang_tracking_reward = torch.zeros(num_envs, dtype=torch.float, device=device, requires_grad=False)
        self.last_height_tracking_reward = torch.zeros(num_envs, dtype=torch.float, device=device, requires_grad=False)
        self.last_torques = torch.zeros(num_envs, 31, dtype=torch.float, device=device, requires_grad=False)
        self.last_last_action = torch.zeros(num_envs, 31, dtype=torch.float, device=device, requires_grad=False)
        self.lin_vel_z_queue = TorchDeque(maxlen=64, num_envs=num_envs, element_shape=(1,), dtype=torch.float, device=device,requires_grad=False)
        self.stumble_queue = TorchDeque(maxlen=64, num_envs=num_envs, element_shape=(1,), dtype=torch.float, device=device,requires_grad=False)

        self.is_step = torch.zeros(num_envs, dtype=torch.bool, device=device, requires_grad=False)
        self.contact_bool = torch.zeros(num_envs, dtype=torch.bool, device=device, requires_grad=False)
        self.initialized_flag = True

        self.reward_buffer = TorchDeque(maxlen=128, num_envs=1, element_shape=(1,), dtype=torch.float, device=device,requires_grad=False)

    def reset(self,env_id):
        self.des_hand_positions_x[env_id] = 0.0
        self.des_hand_velocity_x[env_id] = 0.0
        self.last_lin_tracking_reward[env_id] = 0.0
        self.last_ang_tracking_reward[env_id] = 0.0
        self.last_height_tracking_reward[env_id] = 0.0
        self.last_torques[env_id] = 0.0
        self.lin_vel_z_queue.reset(env_id)

    def get_des_hand_positions_x(self):
        return self.des_hand_positions_x

    def get_des_hand_velocity_x(self):
        return self.des_hand_velocity_x

    def get_last_lin_tracking_reward(self):
        return self.last_lin_tracking_reward

    def get_last_ang_tracking_reward(self):
        return self.last_ang_tracking_reward

    def get_last_height_tracking_reward(self):
        return self.last_height_tracking_reward

    def get_last_torques(self):
        return self.last_torques
    
    def get_last_last_action(self):
        return self.last_last_action

class TorchDeque:
    def __init__(self, maxlen, num_envs, element_shape, dtype=torch.float32, device='cpu', requires_grad=False):
        self.maxlen = maxlen
        self.num_envs = num_envs
        self.element_shape = element_shape
        
        # 合并所有环境的缓冲区为一个大张量 [maxlen, num_envs, *element_shape]
        self.buffer = torch.zeros(
            (maxlen, num_envs, *element_shape), 
            dtype=dtype, 
            device=device, 
            requires_grad=requires_grad
        )
        
        self.heads = torch.zeros(num_envs, dtype=torch.long, device=device)  # 每个环境的队首索引
        self.lengths = torch.zeros(num_envs, dtype=torch.long, device=device)  # 每个环境的队列长度
    
    def append(self, value):
        if value.shape[0] != self.num_envs:
            raise ValueError(f"Input tensor has {value.shape[0]} environments, but expected {self.num_envs}")
        
        # 扩展维度以匹配缓冲区的形状 [num_envs, *element_shape] -> [1, num_envs, *element_shape]
        value = value.unsqueeze(0)

        tails = (self.heads + self.lengths) % self.maxlen
        
        full_mask = (self.lengths == self.maxlen)
        self.heads = (self.heads + full_mask.long()) % self.maxlen
        self.lengths += (~full_mask).long()
        
        self.buffer[tails, torch.arange(self.num_envs)] = value
    
    def pop(self, env_id):
        """从指定环境的队列移除并返回队首元素"""
        if env_id < 0 or env_id >= self.num_envs:
            raise IndexError(f"env_id {env_id} out of range")
        
        if self.lengths[env_id] == 0:
            raise IndexError(f"pop from empty queue (env_id={env_id})")
        
        # 获取队首元素
        value = self.buffer[self.heads[env_id], env_id]
        
        # 更新队首索引
        self.heads[env_id] = (self.heads[env_id] + 1) % self.maxlen
        
        # 减少队列长度
        self.lengths[env_id] -= 1
        
        return value
    
    def __len__(self):
        """返回所有环境的平均队列长度"""
        return int(self.lengths.mean())
    
    def len_env(self, env_id):
        """返回指定环境的队列长度"""
        if env_id < 0 or env_id >= self.num_envs:
            raise IndexError(f"env_id {env_id} out of range")
        return int(self.lengths[env_id])
    
    def reset(self, env_id):
        self.heads[env_id] = 0
        self.lengths[env_id] = 0
        self.buffer[:, env_id] = 0.0

    def __getitem__(self, env_id):
        """获取指定环境的整个队列作为张量"""
        if env_id < 0 or env_id >= self.num_envs:
            raise IndexError(f"env_id {env_id} out of range")
        
        length = self.lengths[env_id]
        head = self.heads[env_id]
        
        # 生成索引序列
        indices = (head + torch.arange(length, device=self.buffer.device)) % self.maxlen
        
        # 返回指定环境的队列数据
        return self.buffer[indices, env_id]
    
    def to_tensor(self):
        """返回所有环境的队列数据作为一个大张量"""
        max_length = int(self.lengths.max())
        if max_length == 0:
            return torch.zeros(self.num_envs, 0, *self.element_shape, device=self.buffer.device)
        
        # 创建时间索引网格 [max_length, num_envs]
        time_indices = torch.arange(max_length, device=self.buffer.device).unsqueeze(1)
        env_indices = torch.arange(self.num_envs, device=self.buffer.device).unsqueeze(0)
        
        # 计算缓冲区索引 [max_length, num_envs]
        buffer_indices = (self.heads + time_indices) % self.maxlen
        
        # 创建有效掩码 [max_length, num_envs]
        valid_mask = time_indices < self.lengths
        
        # 获取数据 [max_length, num_envs, *element_shape]
        data = self.buffer[buffer_indices, env_indices]
        
        # 应用掩码，将无效位置设为0
        masked_data = data * valid_mask.unsqueeze(-1).expand_as(data)
        
        # 调整维度顺序 [num_envs, max_length, *element_shape]
        return masked_data.permute(1, 0, 2)
    
    def mean(self):
        """计算所有环境队列当前元素的平均值"""
        if self.lengths.max() == 0:
            return torch.zeros(self.num_envs, *self.element_shape, device=self.buffer.device)
        
        # 使用to_tensor方法获取所有数据 [num_envs, max_length, *element_shape]
        all_data = self.to_tensor()
        
        # 计算每个环境的有效元素数量
        valid_counts = self.lengths.unsqueeze(-1).expand(-1, *self.element_shape).clamp(min=1)
        
        # 计算每个环境的平均值（忽略零值）
        sum_per_env = all_data.sum(dim=1)  # [num_envs, *element_shape]
        
        return sum_per_env / valid_counts

    def max(self):
        return self.buffer.max(dim=0)[0]


joint_order = torch.tensor(
              [0, 3, 6,  9, 14, 19,
               1, 4, 7, 10, 15, 20,
               2, 5, 8,
               11, 16,
               12, 17, 21, 23, 25, 27, 29,
               13, 18, 22, 24, 26, 28, 30], device="cuda:0", requires_grad=False)

torque_limits_vec = torch.tensor([75., 75., 75., 75., 46., 46.,
                                  75., 75., 75., 75., 46., 46.,
                                  23, 46, 46,
                                  10, 10,
                                  15.5, 15.5, 15.5, 15.5, 10, 10, 10,
                                  15.5, 15.5, 15.5, 15.5, 10, 10, 10], device="cuda:0", requires_grad=False)


# action smoothness
def action_smoothness(env: ManagerBasedRLEnv) -> torch.Tensor:
    action_t = env.action_manager.action
    action_last = env.action_manager.prev_action
    action_last2 = env.data_cache.get_last_last_action()
    reward = torch.sum(torch.square(action_t - 2*action_last + action_last2), dim=1)
    action_last2[:] = action_last
    return reward

# distance
def distance_aligned(env: ManagerBasedRLEnv, 
                    asset_cfg: SceneEntityCfg, 
                    min_dist: float, 
                    max_dist: float,
                    desired_dist: float) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]

    left_idx = asset_cfg.body_ids[0]
    right_idx = asset_cfg.body_ids[1]
    base_quat = asset.data.root_quat_w
    heading_aligned = math_utils.yaw_quat(base_quat)

    left_pos = math_utils.quat_rotate_inverse(heading_aligned, asset.data.body_pos_w[:, left_idx])
    right_pos = math_utils.quat_rotate_inverse(heading_aligned, asset.data.body_pos_w[:, right_idx])

    distance_y = torch.abs(left_pos[:, 1] - right_pos[:, 1])
    # print("distance: ", distance_y)
    d_min = torch.where(distance_y < min_dist, min_dist - distance_y, torch.tensor(0.0, device=distance_y.device))
    d_max = torch.where(distance_y > max_dist, distance_y - max_dist, torch.tensor(0.0, device=distance_y.device))

    reward_1 = (torch.exp(-(d_min+d_max)/0.02))
    reward_2 = torch.exp(-torch.square((distance_y - desired_dist) / 0.02))

    return (reward_1 + reward_2) / 2

# distance
def close_feet(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]

    left_foot_idx = asset.data.body_names.index("left_ankle_roll_link")
    right_foot_idx = asset.data.body_names.index("right_ankle_roll_link")

    left_foot_pos = asset.data.body_pos_w[:, left_foot_idx]
    right_foot_pos = asset.data.body_pos_w[:, right_foot_idx]

    distance = torch.norm(left_foot_pos[:, :2] - right_foot_pos[:, :2], dim=1)
    return (distance - 0.2).clip(max=0.)

# symmetric
def symmetric_stand_still(
        env: ManagerBasedRLEnv,
        nominal_joints,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]

    nominal_pos = torch.tensor(nominal_joints, device=env.device, requires_grad=False)
    dof_pos = torch.abs(asset.data.joint_pos[:, joint_order] - nominal_pos)

    leg_diff = torch.sum(torch.abs(dof_pos[:, 0:4] - dof_pos[:, 6:10]), dim=1)
    arm_diff = torch.sum(torch.abs(dof_pos[:, 12:]), dim=1)

    stand_still_flag = gait_handler.get_stand_still_flag()
    return (leg_diff + arm_diff) * stand_still_flag

# symmetric
def symmetric_stand_still_contact_force(
        env: ManagerBasedRLEnv,
        sensor_cfg: SceneEntityCfg,
) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w

    left_foot_force = torch.norm(net_contact_forces[:, sensor_cfg.body_ids[0]], dim=-1)
    right_foot_force = torch.norm(net_contact_forces[:, sensor_cfg.body_ids[1]], dim=-1)

    stand_still_flag = gait_handler.get_stand_still_flag()
    return torch.abs(left_foot_force - right_foot_force) * stand_still_flag

# symmetric
def symmetric_arm(
        env: ManagerBasedRLEnv,
        nominal_joints,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]
    nominal_pos = torch.tensor(nominal_joints, device=env.device, requires_grad=False)
    dof_pos = torch.abs(asset.data.joint_pos[:, joint_order] - nominal_pos)
    arm_diff = torch.sum(torch.abs(dof_pos[:, 12:]), dim=1)
    return arm_diff

# motion gait
def keep_ankle_joint_zero_in_the_air(
        env: ManagerBasedRLEnv,
        joint_idx,
        sensor_cfg: SceneEntityCfg,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    air_time = contact_sensor.data.current_air_time[:, sensor_cfg.body_ids]
    no_contact = air_time > 0.0

    asset: Articulation = env.scene[asset_cfg.name]
    ankle_pos = torch.abs(asset.data.joint_pos[:, joint_order[joint_idx]])

    return torch.exp(-torch.sum(ankle_pos * no_contact, dim=1) / 0.2)

# motion gait
def natural_swing_arm(
        env: ManagerBasedRLEnv,
        command_name: str,
        std_pos,
        std_vel,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    asset: RigidObject = env.scene[asset_cfg.name]
    left_hand_idx = asset.data.body_names.index("left_hand_contact")
    right_hand_idx = asset.data.body_names.index("right_hand_contact")

    idx = [left_hand_idx, right_hand_idx]
    hand_positions = asset.data.body_pos_w[:, idx]
    hand_velocities = asset.data.body_lin_vel_w[:, idx]

    gait_info = gait_handler.get_gait_info()

    des_hand_positions_x = env.data_cache.get_des_hand_positions_x()
    des_hand_velocity_x = env.data_cache.get_des_hand_velocity_x()

    command = env.command_manager.get_command(command_name)
    arm_swing_distance = (0.1 + 0.1 * torch.abs(command[:, 0])) * torch.where(command[:, 0] < 0., torch.tensor(-1.), torch.tensor(1.))
    stand_still_flag = gait_handler.get_stand_still_flag()
    arm_swing_distance[stand_still_flag] = 0.0
    des_hand_positions_x[:, 0] = -arm_swing_distance * gait_info[:, 4]
    des_hand_positions_x[:, 1] = arm_swing_distance * gait_info[:, 4]
    des_hand_velocity_x[:, 0] = 2.0 * arm_swing_distance * torch.pi * gait_info[:, 0] * gait_info[:, 3]
    des_hand_velocity_x[:, 1] = -2.0 * arm_swing_distance * torch.pi * gait_info[:, 0] * gait_info[:, 3]

    hand_pos_body = torch.zeros_like(hand_positions)
    hand_vel_body = torch.zeros_like(hand_velocities)

    body_quat = asset.data.root_quat_w
    body_pos = asset.data.root_pos_w
    hand_pos_body[:, 0] = math_utils.quat_rotate_inverse(body_quat, hand_positions[:, 0] - body_pos)
    hand_pos_body[:, 1] = math_utils.quat_rotate_inverse(body_quat, hand_positions[:, 1] - body_pos)

    body_vel = asset.data.root_lin_vel_w
    hand_vel_body[:, 0] = math_utils.quat_rotate_inverse(body_quat, hand_velocities[:, 0] - body_vel)
    hand_vel_body[:, 1] = math_utils.quat_rotate_inverse(body_quat, hand_velocities[:, 1] - body_vel)

    reward = torch.exp(-(hand_pos_body[:, 0, 0] - des_hand_positions_x[:, 0]) ** 2 / std_pos ** 2) \
             + torch.exp(-(hand_pos_body[:, 1, 0] - des_hand_positions_x[:, 1]) ** 2 / std_pos ** 2) \
             + torch.exp(-(hand_vel_body[:, 0, 0] - des_hand_velocity_x[:, 0]) ** 2 / std_vel ** 2) \
             + torch.exp(-(hand_vel_body[:, 1, 0] - des_hand_velocity_x[:, 1]) ** 2 / std_vel ** 2)

    # stand_still_flag = gait_handler.get_stand_still_flag()
    # return reward / 2. * ~stand_still_flag
    return reward / 2.

# contact
def no_fly(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contact_time = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids]
    robot_no_fly = torch.sum(contact_time, dim=1) > 0.0

    return robot_no_fly

# contact force
def tracking_contacts_shaped_force(
        env: ManagerBasedRLEnv,
        sensor_cfg: SceneEntityCfg,
        std,
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w

    desired_contact_states = gait_handler.get_desired_contact_states()

    reward = (1 - desired_contact_states[:, 0]) * torch.exp(
        -net_contact_forces[:, sensor_cfg.body_ids[0], 2] ** 2 / std ** 2) \
             + (1 - desired_contact_states[:, 1]) * torch.exp(
        -net_contact_forces[:, sensor_cfg.body_ids[1], 2] ** 2 / std ** 2)

    # stand_still_flag = gait_handler.get_stand_still_flag()
    # return reward / 2. * ~stand_still_flag
    return reward / 2.

# contact base velocity + desired velocity
def tracking_contacts_shaped_linear_velocity(
        env: ManagerBasedRLEnv,
        stance_std,
        swing_std,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    asset: RigidObject = env.scene[asset_cfg.name]
    left_velocity = asset.data.body_lin_vel_w[:, asset_cfg.body_ids[0], 2]
    right_velocity = asset.data.body_lin_vel_w[:, asset_cfg.body_ids[1], 2]

    desired_contact_states = gait_handler.get_desired_contact_states()
    desired_foot_velocity = gait_handler.get_desired_foot_velocity().view(env.num_envs)

    reward = (1 - desired_contact_states[:, 0]) * torch.exp(
        -(left_velocity - desired_foot_velocity) ** 2 / swing_std ** 2) \
             + (1 - desired_contact_states[:, 1]) * torch.exp(
        -(right_velocity - desired_foot_velocity) ** 2 / swing_std ** 2) \
             + desired_contact_states[:, 0] * torch.exp(-(left_velocity) ** 2 / stance_std ** 2) \
             + desired_contact_states[:, 1] * torch.exp(-(right_velocity) ** 2 / stance_std ** 2)

    # stand_still_flag = gait_handler.get_stand_still_flag()
    # return reward / 2. * ~stand_still_flag
    return reward / 2.

# contact force + base velocity
def tracking_contacts_shaped_contacts(
        env: ManagerBasedRLEnv,
        sensor_cfg: SceneEntityCfg,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
        std_force: float = 1.0,
        std_vel: float = 1.0,
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w

    asset: RigidObject = env.scene[asset_cfg.name]
    left_velocity = torch.norm(asset.data.body_lin_vel_w[:, asset_cfg.body_ids[0], :], dim=-1)
    right_velocity = torch.norm(asset.data.body_lin_vel_w[:, asset_cfg.body_ids[1], :], dim=-1)

    desired_contact_states = gait_handler.get_desired_contact_states()

    # force penalty while no contact
    reward = (1 - desired_contact_states[:, 0]) * torch.exp(
        -net_contact_forces[:, sensor_cfg.body_ids[0], 2] ** 2 / std_force ** 2) \
             + (1 - desired_contact_states[:, 1]) * torch.exp(
        -net_contact_forces[:, sensor_cfg.body_ids[1], 2] ** 2 / std_force ** 2)
    reward += desired_contact_states[:, 0] * torch.exp(-left_velocity ** 2 / std_vel ** 2) \
              + desired_contact_states[:, 1] * torch.exp(-right_velocity ** 2 / std_vel ** 2)

    # stand_still_flag = gait_handler.get_stand_still_flag()
    # return reward / 1. * ~stand_still_flag
    return reward / 2.

# contact base velocity
def tracking_contact_shaped_angular_velocity(
        env: ManagerBasedRLEnv,
        std,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    asset: RigidObject = env.scene[asset_cfg.name]
    left_foot_idx = asset.data.body_names.index("left_ankle_roll_link")
    right_foot_idx = asset.data.body_names.index("right_ankle_roll_link")

    left_angular_velocity = asset.data.body_ang_vel_w[:, left_foot_idx, 2]
    right_angular_velocity = asset.data.body_ang_vel_w[:, right_foot_idx, 2]

    desired_contact_states = gait_handler.get_desired_contact_states()
    reward = desired_contact_states[:, 0] * torch.exp(-(left_angular_velocity) ** 2 / std ** 2) \
             + desired_contact_states[:, 1] * torch.exp(-(right_angular_velocity) ** 2 / std ** 2)

    stand_still_flag = gait_handler.get_stand_still_flag()
    return reward / 2. * ~stand_still_flag

# contact base height + desired height
def tracking_contact_shaped_height(
        env: ManagerBasedRLEnv,
        std,
        height_offset,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    if not hasattr(env, "obs_buf"):
        return 0

    asset: RigidObject = env.scene[asset_cfg.name]
    left_foot_idx = asset.data.body_names.index("left_ankle_roll_link")
    right_foot_idx = asset.data.body_names.index("right_ankle_roll_link")

    left_foot_position = asset.data.body_pos_w[:, left_foot_idx, 2] + height_offset
    right_foot_position = asset.data.body_pos_w[:, right_foot_idx, 2] + height_offset  # -0.05

    desired_contact_states = gait_handler.get_desired_contact_states()
    desired_foot_height = gait_handler.get_desired_foot_height().view(env.num_envs)

    reward = (1 - desired_contact_states[:, 0]) * torch.exp(-(left_foot_position - desired_foot_height) ** 2 / std ** 2) \
             + (1 - desired_contact_states[:, 1]) * torch.exp(
        -(right_foot_position - desired_foot_height) ** 2 / std ** 2) \
             + desired_contact_states[:, 0] * torch.exp(-(left_foot_position) ** 2 / std ** 2) \
             + desired_contact_states[:, 1] * torch.exp(-(right_foot_position) ** 2 / std ** 2)

    stand_still_flag = gait_handler.get_stand_still_flag()
    return reward / 2. * ~stand_still_flag

# both foot on ground when stand_still_flag
def foot_ground_stand_still(
        env: ManagerBasedRLEnv,
        step_force_threshold: float, 
        contact_sensor_cfg: SceneEntityCfg,
    ) -> torch.Tensor:

    contact_sensor: ContactSensor = env.scene.sensors[contact_sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w[:, contact_sensor_cfg.body_ids]
    both_step = (torch.abs(net_contact_forces[:, :, 2]) > step_force_threshold).all(dim=-1)
    one_step = ((torch.abs(net_contact_forces[:, :, 2]) > step_force_threshold).any(dim=-1) & ~both_step)
    stand_still_flag = gait_handler.get_stand_still_flag()
    # reward stand still is True and both step is True
    reward = (both_step & stand_still_flag).float() * 2.0
    # penalty stand still is True and both step is False
    reward += (one_step & stand_still_flag).float() * -1.0
    return reward

# velocity tracking
def tracking_lin_vel_pb(
        env: ManagerBasedRLEnv, std: float, command_name: str, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:

    current_reward = track_lin_vel_xy_exp(env, std, command_name, asset_cfg)
    last_reward = env.data_cache.get_last_lin_tracking_reward()
    reward = (current_reward - last_reward).clip(min=0.0)
    last_reward[:] = current_reward
    return reward

# velocity tracking
def tracking_ang_vel_pb(
        env: ManagerBasedRLEnv, std: float, command_name: str, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:

    current_reward = track_ang_vel_z_exp(env, std, command_name, asset_cfg)
    last_reward = env.data_cache.get_last_ang_tracking_reward()
    reward = (current_reward - last_reward).clip(min=0.0)
    last_reward[:] = current_reward
    return reward

# velocity mismatch
def vel_mismatch_exp(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    lin_z_mismatch = torch.exp(-torch.square(asset.data.root_lin_vel_b[:, 2]) * 10)
    ang_mismatch = torch.exp(-torch.norm(asset.data.root_ang_vel_b[:, :2], dim=1) * 5.)
    return (lin_z_mismatch + ang_mismatch) / 2.0

# angular velocity
def ang_vel_l2(
        env: ManagerBasedRLEnv,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    # get torso orientation state
    asset: RigidObject = env.scene[asset_cfg.name]
    ang_vel = asset.data.body_ang_vel_w[:, asset_cfg.body_ids]
    return torch.mean(torch.sum(torch.square(ang_vel[..., :2]), dim=-1), dim=1)

# base height
def base_height_exp(
        env: ManagerBasedRLEnv, target_height: float, std: float, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    base_height_error = torch.square(asset.data.root_pos_w[:, 2] - target_height)
    return torch.exp(-base_height_error / std ** 2)

# base height
# def base_height_rough_exp(
#         env: ManagerBasedRLEnv, target_height: float, std: float, sensor_cfg: SceneEntityCfg,
#         asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
# ) -> torch.Tensor:
#     asset: RigidObject = env.scene[asset_cfg.name]
#     sensor: RayCaster = env.scene.sensors[sensor_cfg.name]
#     base_height , is_inf = compute_base_height_rough(asset, sensor, False)
#     reward = torch.exp(-torch.square(base_height - target_height) / std ** 2)
#     # Set the reward to -1 for inf values
#     reward[is_inf] = -1.0
#     return reward

# base height
def base_height_exp_pb(
        env: ManagerBasedRLEnv, target_height: float, std: float, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:

    current_reward = base_height_exp(env, target_height, std, asset_cfg)
    last_reward = env.data_cache.get_last_height_tracking_reward()
    reward = (current_reward - last_reward).clip(min=0.0)
    last_reward[:] = current_reward
    return reward

# base height
def base_height_rough_exp_pb(
        env: ManagerBasedRLEnv, target_height: float, std: float, sensor_cfg: SceneEntityCfg,
        asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:

    current_reward = base_height_rough_exp(env, target_height, std, sensor_cfg, asset_cfg)
    last_reward = env.data_cache.get_last_height_tracking_reward()
    reward = (current_reward - last_reward).clip(min=0.0)
    last_reward[:] = current_reward
    return reward

# base acc
def base_acc(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    # print(asset.data.body_lin_acc_w[:, asset_cfg.body_ids, :])
    return torch.exp(-0.1 * torch.sum(torch.norm(asset.data.body_lin_acc_w[:, asset_cfg.body_ids, :], dim=-1), dim=1))

# base low speed
def base_low_speed(
    env: ManagerBasedRLEnv, std: float, min_speed, command_name: str, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
    ) -> torch.Tensor:
    """Penalize low speed of the base."""
    # extract the used quantities (to enable type-hinting)
    asset: RigidObject = env.scene[asset_cfg.name]
    lin_vel = torch.abs(asset.data.root_lin_vel_b[:, 0])  # only x
    com_vel = torch.abs(env.command_manager.get_command(command_name)[:, 0])
    com_higher_speed = com_vel > min_speed
    # return torch.exp(-torch.square(lin_vel) / std ** 2) * com_higher_speed
    low_speed = lin_vel < 0.1
    return torch.logical_and(com_higher_speed, low_speed).float()

# orientation
def orientation_exp(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    r, p, y = math_utils.euler_xyz_from_quat(asset.data.root_quat_w)
    ruler_angle = torch.stack([normalize_angle(r), normalize_angle(p), normalize_angle(y)], dim=-1)
    quat_mismatch = torch.exp(-torch.sum(torch.abs(ruler_angle[:, :2]), dim=1) * 10)
    orientation = torch.exp(-torch.norm(asset.data.projected_gravity_b[:, :2], dim=1) * 20)
    return (quat_mismatch + orientation) / 2.0

# orientation
def orientation_multi_body_exp(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    asset: RigidObject = env.scene[asset_cfg.name]
    reward2 = 0.0
    base_quat = asset.data.root_quat_w
    inverse_base_quat = math_utils.quat_inv(base_quat)

    for i in range(len(asset_cfg.body_ids)):
        body_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids[i], :]
        body_quat_b = math_utils.quat_mul(inverse_base_quat, body_quat_w)
        r, p, y = math_utils.euler_xyz_from_quat(body_quat_b.squeeze(1))
        ruler_angle = torch.stack([normalize_angle(r), normalize_angle(p), normalize_angle(y)], dim=-1)
        quat_mismatch = torch.exp(-torch.sum(torch.abs(ruler_angle), dim=1) * 10)
        reward2 += quat_mismatch
    reward1 = torch.exp(-torch.norm(asset.data.projected_gravity_b[:, :2], dim=1) * 20) # base orientation
    reward2 = reward2 / len(asset_cfg.body_ids)
    # return reward / len(asset_cfg.body_ids) + orientation
    return reward2 + reward1

# orientation
def orientation_exp_knee(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    # yaw
    asset: RigidObject = env.scene[asset_cfg.name]
    reward = 0.0
    base_quat = asset.data.root_quat_w
    inverse_base_quat = math_utils.quat_inv(base_quat)

    for i in range(len(asset_cfg.body_ids)):
        body_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids[i], :]
        body_quat_b = math_utils.quat_mul(inverse_base_quat, body_quat_w)
        r, p, y = math_utils.euler_xyz_from_quat(body_quat_b.squeeze(1))
        ruler_angle = torch.stack([normalize_angle(r), normalize_angle(p), normalize_angle(y)], dim=-1)
        quat_mismatch = torch.exp(-torch.abs(ruler_angle[:, 2]) * 10) # only yaw angle
        reward += quat_mismatch
    return reward / len(asset_cfg.body_ids)

# orientation
def body_orientation_yaw_exp(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    # yaw
    asset: RigidObject = env.scene[asset_cfg.name]
    num_body = len(asset_cfg.body_ids)
    base_quat = asset.data.root_quat_w
    inverse_base_quat = math_utils.quat_inv(base_quat).unsqueeze(1).expand(-1, num_body, -1) #[env, body_num, 4]
    body_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids, :] #[env, body_num, 4]
    body_quat_b = math_utils.quat_mul(inverse_base_quat, body_quat_w).flatten(0,1) #[env * body_num, 4]
    r, p, y = math_utils.euler_xyz_from_quat(body_quat_b.squeeze(1))
    ruler_angle = torch.stack([normalize_angle(r), normalize_angle(p), normalize_angle(y)], dim=-1).reshape(-1,num_body,3)  #[env, body_num, 3]
    quat_mismatch = torch.exp(-torch.abs(ruler_angle[:,:,2]) * 10) #[env, body_num], yaw
    return torch.mean(quat_mismatch, dim=1) #[env]

# orientation
def body_orientation_exp(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    # roll, pitch
    asset: RigidObject = env.scene[asset_cfg.name]
    num_body = len(asset_cfg.body_ids)
    base_quat = asset.data.root_quat_w
    inverse_base_quat = math_utils.quat_inv(base_quat).unsqueeze(1).expand(-1, num_body, -1) #[env, body_num, 4]
    body_quat_w = asset.data.body_quat_w[:, asset_cfg.body_ids, :] #[env, body_num, 4]
    body_quat_b = math_utils.quat_mul(inverse_base_quat, body_quat_w).flatten(0,1) #[env * body_num, 4]
    r, p, y = math_utils.euler_xyz_from_quat(body_quat_b.squeeze(1))
    ruler_angle = torch.stack([normalize_angle(r), normalize_angle(p), normalize_angle(y)], dim=-1).reshape(-1,num_body,3)  #[env, body_num, 3]
    quat_mismatch = torch.exp(-torch.sum(torch.abs(ruler_angle[:,:,:2]), dim=(2)) * 10) #[env, body_num], roll pitch
    return torch.mean(quat_mismatch, dim=1) #[env]

# orientation
def body_projected_gravity_l2(env: ManagerBasedRLEnv, std: float, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    # get body orientation state
    asset: RigidObject = env.scene[asset_cfg.name]
    body_projected_gravity = math_utils.quat_rotate_inverse(asset.data.body_quat_w[:, asset_cfg.body_ids], asset.data.GRAVITY_VEC_W.unsqueeze(1))
    gravity_reward = torch.sum(torch.square(body_projected_gravity[:, :, :2]), dim=-1) / std ** 2 # [env, body_num]
    # gravity_reward = torch.norm(body_projected_gravity[:, :, :2], dim=-1) / std # [env, body_num]
    return torch.mean(gravity_reward,dim=1)

# joint
def joint_deviation_l1_w(env: ManagerBasedRLEnv,joint_weights=None, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """Penalize joint positions that deviate from the default one."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    # compute out of limits constraints
    angle = asset.data.joint_pos[:, asset_cfg.joint_ids] - asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    if joint_weights is None:
        joint_weights_tensor = torch.ones_like(angle, device=env.device, requires_grad=False)
    else:
        joint_weights_tensor = torch.tensor(joint_weights, device=env.device, requires_grad=False)
    return torch.sum(torch.abs(angle) * joint_weights_tensor, dim=1)

def joint_deviation_l1_stand(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    """Penalize joint positions that deviate from the default one."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    # compute out of limits constraints
    angle = asset.data.joint_pos[:, asset_cfg.joint_ids] - asset.data.default_joint_pos[:, asset_cfg.joint_ids]
    stand_still_flag = gait_handler.get_stand_still_flag()
    reward = torch.sum(torch.abs(angle), dim=1)
    return reward * stand_still_flag

# torque 
def power(env: ManagerBasedRLEnv, joint_weights=None, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]
    torque = asset.data.applied_torque[:, asset_cfg.joint_ids]
    vel = asset.data.joint_vel[:, asset_cfg.joint_ids]
    if joint_weights is None:
        joint_weights_tensor = torch.ones_like(torque, device=env.device, requires_grad=False)
    else:
        joint_weights_tensor = torch.tensor(joint_weights, device=env.device, requires_grad=False)
    power = torch.abs(torque * vel)
    return torch.sum(torch.square(power) * joint_weights_tensor, dim=1)

# torque 
def torque_soft_limits(env: ManagerBasedRLEnv, soft_ratio, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]
    torque = asset.data.applied_torque[:, asset_cfg.joint_ids]
    return torch.sum((torch.abs(torque[:, joint_order]) - torque_limits_vec * soft_ratio).clip(min=0.), dim=1)

# torque
def torques_smoothness(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")) -> torch.Tensor:

    asset: Articulation = env.scene[asset_cfg.name]
    torques = asset.data.applied_torque[:, asset_cfg.joint_ids]
    last_torques = env.data_cache.get_last_torques()
    reward = torch.sum(torch.square(torques - last_torques), dim=1)
    last_torques[:] = torques[:]
    return reward

# feet
def stumble(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w
    horizon_force = torch.norm(net_contact_forces[:, sensor_cfg.body_ids, :2], dim=-1).float()
    vertical_force = torch.abs(net_contact_forces[:, sensor_cfg.body_ids, 2]).float()
    return torch.any(horizon_force > 2.0 * vertical_force, dim=1)

# feet
def stumble_mean(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    net_contact_forces = contact_sensor.data.net_forces_w
    horizon_force = torch.norm(net_contact_forces[:, sensor_cfg.body_ids, :2], dim=-1).float()
    vertical_force = torch.abs(net_contact_forces[:, sensor_cfg.body_ids, 2]).float()
    stumble_flag = torch.any(horizon_force > 2.0 * vertical_force, dim=1).float()
    env.data_cache.stumble_queue.append(stumble_flag.unsqueeze(1))
    mean_stumble_flag = env.data_cache.stumble_queue.mean().squeeze(1)
    return torch.square(mean_stumble_flag *2)

# feet
def feet_air_time(
    env: ManagerBasedRLEnv, command_name: str, sensor_cfg: SceneEntityCfg, threshold: float
) -> torch.Tensor:
    """Reward long steps taken by the feet using L2-kernel.

    This function rewards the agent for taking steps that are longer than a threshold. This helps ensure
    that the robot lifts its feet off the ground and takes steps. The reward is computed as the sum of
    the time for which the feet are in the air.

    If the commands are small (i.e. the agent is not supposed to take a step), then the reward is zero.
    """
    # extract the used quantities (to enable type-hinting)
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # compute the reward
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    last_air_time = contact_sensor.data.last_air_time[:, sensor_cfg.body_ids]
    reward = torch.sum((last_air_time - threshold) * first_contact, dim=1)
    # no reward for zero command
    reward *= torch.norm(env.command_manager.get_command(command_name)[:, :2], dim=1) > 0.1
    return reward

# feet
def feet_air_time(
        env: ManagerBasedRLEnv, command_name: str, sensor_cfg: SceneEntityCfg, threshold: float
) -> torch.Tensor:
    """Reward long steps taken by the feet using L2-kernel.

    This function rewards the agent for taking steps that are longer than a threshold. This helps ensure
    that the robot lifts its feet off the ground and takes steps. The reward is computed as the sum of
    the time for which the feet are in the air.

    If the commands are small (i.e. the agent is not supposed to take a step), then the reward is zero.
    """
    # extract the used quantities (to enable type-hinting)
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # compute the reward
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    last_air_time = contact_sensor.data.last_air_time[:, sensor_cfg.body_ids]
    reward = torch.sum((last_air_time - threshold) * first_contact, dim=1)
    # no reward for zero command
    reward *= torch.norm(env.command_manager.get_command(command_name)[:, :2], dim=1) > 0.1
    return reward

# feet
def feet_air_time_positive_biped(
        env: ManagerBasedRLEnv, command_name: str, threshold: float, sensor_cfg: SceneEntityCfg
) -> torch.Tensor:
    """Reward long steps taken by the feet for bipeds.

    This function rewards the agent for taking steps up to a specified threshold and also keep one foot at
    a time in the air.

    If the commands are small (i.e. the agent is not supposed to take a step), then the reward is zero.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # compute the reward
    air_time = contact_sensor.data.current_air_time[:, sensor_cfg.body_ids]
    contact_time = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids]
    in_contact = contact_time > 0.0
    in_mode_time = torch.where(in_contact, contact_time, air_time)
    single_stance = torch.sum(in_contact.int(), dim=1) == 1
    reward = torch.min(torch.where(single_stance.unsqueeze(-1), in_mode_time, 0.0), dim=1)[0]
    reward = torch.clamp(reward, max=threshold)
    # no reward for zero command
    reward *= torch.norm(env.command_manager.get_command(command_name)[:, :2], dim=1) > 0.1
    return reward

# feet
def feet_slide(env, sensor_cfg: SceneEntityCfg, 
               step_force_threshold: float = 100.0,
               asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
               ) -> torch.Tensor:
    """Penalize feet sliding.

    This function penalizes the agent for sliding its feet on the ground. The reward is computed as the
    norm of the linear velocity of the feet multiplied by a binary contact sensor. This ensures that the
    agent is penalized only when the feet are in contact with the ground.
    """
    # Penalize feet sliding #???contacts 状态判断，如果是踩到楼梯边缘？
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0] > step_force_threshold
    asset = env.scene[asset_cfg.name]

    body_vel = asset.data.body_com_lin_vel_w[:, asset_cfg.body_ids, :2]
    ang_vel = asset.data.body_com_ang_vel_w[:, asset_cfg.body_ids, :]
    reward = torch.sum((body_vel.norm(dim=-1) + 0.25 * ang_vel.norm(dim=-1)) * contacts, dim=1)
    return reward

def feet_flat(env, sensor_cfg: SceneEntityCfg, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"), step_force_threshold: float = 200.0, std: float = 0.1) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0] > step_force_threshold
    asset:RigidObject = env.scene[asset_cfg.name]
    # get feet projected gravity
    feet_quat = asset.data.body_quat_w[:, asset_cfg.body_ids, :]
    feet_projected_gravity = math_utils.quat_rotate_inverse(feet_quat, asset.data.GRAVITY_VEC_W.unsqueeze(1))
    return torch.sum(torch.sum(torch.square(feet_projected_gravity[:, :, :2]) , dim=2) * contacts / std ** 2, dim=1)

def normalize_angle(x):
    return torch.atan2(torch.sin(x), torch.cos(x))

def nominal_joints_l1(
        env: ManagerBasedRLEnv, joint_idx, nominal_joints, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]
    joint_index_tensor = torch.tensor(joint_idx, device=env.device, requires_grad=False)
    index = joint_order[joint_index_tensor]
    nominal_pos = torch.tensor(nominal_joints, device=env.device, requires_grad=False)
    return torch.sum(torch.abs(asset.data.joint_pos[:, index] - nominal_pos), dim=1)

def body_ang_vel_l2(
    env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:

    # get torso orientation state
    asset: RigidObject = env.scene[asset_cfg.name]
    body_ang_vel = asset.data.body_ang_vel_w[:, asset_cfg.body_ids, :2].squeeze(1)
    return torch.sum(torch.sum(torch.square(body_ang_vel), dim=1), dim=1)  # sum over body ids and x, y components

def feet_gait(
    env: ManagerBasedRLEnv,
    period: float,
    offset: list[float],
    sensor_cfg: SceneEntityCfg,
    threshold: float = 0.5,
    command_name=None,
) -> torch.Tensor:
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    is_contact = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids] > 0

    global_phase = ((env.episode_length_buf * env.step_dt) % period / period).unsqueeze(1)
    phases = []
    for offset_ in offset:
        phase = (global_phase + offset_) % 1.0
        phases.append(phase)
    leg_phase = torch.cat(phases, dim=-1)

    reward = torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    for i in range(len(sensor_cfg.body_ids)):
        is_stance = leg_phase[:, i] < threshold
        reward += ~(is_stance ^ is_contact[:, i])

    if command_name is not None:
        cmd_norm = torch.norm(env.command_manager.get_command(command_name), dim=1)
        reward *= cmd_norm > 0.1
    return reward

def foot_clearance_reward(
    env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg, target_height: float, std: float, tanh_mult: float
) -> torch.Tensor:
    """Reward the swinging feet for clearing a specified height off the ground"""
    asset: RigidObject = env.scene[asset_cfg.name]
    foot_z_target_error = torch.square(asset.data.body_pos_w[:, asset_cfg.body_ids, 2] - target_height)
    foot_velocity_tanh = torch.tanh(tanh_mult * torch.norm(asset.data.body_lin_vel_w[:, asset_cfg.body_ids, :2], dim=2))
    reward = foot_z_target_error * foot_velocity_tanh
    return torch.exp(-torch.sum(reward, dim=1) / std)


def base_lin_vel_x(
    env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Root linear velocity x component in the asset's root frame (for logging, weight=0)."""
    asset = env.scene[asset_cfg.name]
    return asset.data.root_lin_vel_b[:, 0]


def leg_separation_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    min_separation: float,
) -> torch.Tensor:
    """Penalize when left and right legs get too close in robot's local Y axis.
    
    In robot's local frame, left leg should have positive Y, right leg negative Y.
    sep = left_y - right_y should be > min_separation.
    """
    asset: RigidObject = env.scene[asset_cfg.name]
    
    left_idx = asset_cfg.body_ids[0]
    right_idx = asset_cfg.body_ids[1]
    
    base_quat = asset.data.root_quat_w
    heading_aligned = math_utils.yaw_quat(base_quat)
    
    left_pos = math_utils.quat_rotate_inverse(heading_aligned, asset.data.body_pos_w[:, left_idx])
    right_pos = math_utils.quat_rotate_inverse(heading_aligned, asset.data.body_pos_w[:, right_idx])
    
    sep = left_pos[:, 1] - right_pos[:, 1]
    violation = torch.clamp(min_separation - sep, min=0.0)
    return violation


def leg_pairwise_contact_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    force_threshold: float,
    left_body_names: list[str],
    right_body_names: list[str],
) -> torch.Tensor:
    """Penalize contact between left and right leg bodies (pairwise).
    
    Uses filtered contact pair forces from force_matrix_w.
    Falls back to net_forces_w heuristic if force_matrix_w not available.
    Only checks left leg bodies vs right leg bodies, not ground contacts.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    
    # Get body indices for left and right leg bodies
    asset: RigidObject = env.scene["robot"]
    left_indices = [asset.data.body_names.index(name) for name in left_body_names]
    right_indices = [asset.data.body_names.index(name) for name in right_body_names]
    
    # Use force_matrix_w for true pairwise contact forces [num_envs, num_bodies, num_bodies, 3]
    force_matrix = contact_sensor.data.force_matrix_w
    
    penalty = torch.zeros(env.num_envs, device=env.device, dtype=torch.float)
    
    if force_matrix is not None:
        # Check pairwise: each left body vs each right body using force_matrix
        for l_idx in left_indices:
            for r_idx in right_indices:
                # force_matrix[:, l_idx, r_idx] gives force on l_idx from r_idx
                pair_force = torch.norm(force_matrix[:, l_idx, r_idx], dim=-1)
                pair_force_rev = torch.norm(force_matrix[:, r_idx, l_idx], dim=-1)
                # Sum both directions for total contact force between the pair
                total_pair_force = pair_force + pair_force_rev
                
                # Penalize if contact force exceeds threshold
                contact_mask = total_pair_force > force_threshold
                penalty += contact_mask.float() * total_pair_force
    else:
        # Fallback: use net_forces_w (less accurate)
        net_forces = contact_sensor.data.net_forces_w
        if net_forces is not None:
            for l_idx in left_indices:
                for r_idx in right_indices:
                    l_force = torch.norm(net_forces[:, l_idx], dim=-1)
                    r_force = torch.norm(net_forces[:, r_idx], dim=-1)
                    both_contact = (l_force > force_threshold) & (r_force > force_threshold)
                    penalty += both_contact.float() * (l_force + r_force)
    
    return penalty


def mirror_symmetry_loss(
    env: ManagerBasedRLEnv,
    joint_names: list[str],
) -> torch.Tensor:
    """Mirror symmetry loss: encourage left/right joint symmetry.
    
    For a symmetric gait, left and right joints should be mirrored.
    Hip/ankle roll and yaw have opposite signs.
    """
    asset = env.scene["robot"]
    
    # Build mirror mapping for joint names
    # Left joints -> corresponding right joints with sign flips
    mirror_map = {}
    sign_flip = {}
    
    for i, name in enumerate(joint_names):
        if name.startswith("left_"):
            right_name = name.replace("left_", "right_")
            if right_name in joint_names:
                mirror_map[i] = joint_names.index(right_name)
                # hip/ankle roll and yaw flip sign
                if "roll" in name or "yaw" in name:
                    sign_flip[i] = -1.0
                else:
                    sign_flip[i] = 1.0
        elif name.startswith("right_"):
            left_name = name.replace("right_", "left_")
            if left_name in joint_names:
                mirror_map[i] = joint_names.index(left_name)
                if "roll" in name or "yaw" in name:
                    sign_flip[i] = -1.0
                else:
                    sign_flip[i] = 1.0
        else:
            mirror_map[i] = i
            sign_flip[i] = 1.0
    
    joint_pos = asset.data.joint_pos
    loss = torch.zeros(env.num_envs, device=env.device, dtype=torch.float)
    
    for i, j in mirror_map.items():
        if i < j:  # Only compute once per pair
            expected = sign_flip[i] * joint_pos[:, j]
            loss += torch.square(joint_pos[:, i] - expected)
    
    return loss


def inter_leg_collision_count(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    force_threshold: float,
    left_body_names: list[str],
    right_body_names: list[str],
) -> torch.Tensor:
    """Count inter-leg collisions per step (for logging, weight=0).
    
    Uses force_matrix_w for true pairwise contact detection.
    Falls back to net_forces_w heuristic if force_matrix_w not available.
    Returns count of left-right body pairs in contact above threshold.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    
    asset: RigidObject = env.scene["robot"]
    left_indices = [asset.data.body_names.index(name) for name in left_body_names]
    right_indices = [asset.data.body_names.index(name) for name in right_body_names]
    
    force_matrix = contact_sensor.data.force_matrix_w
    
    count = torch.zeros(env.num_envs, device=env.device, dtype=torch.float)
    
    if force_matrix is not None:
        for l_idx in left_indices:
            for r_idx in right_indices:
                pair_force = torch.norm(force_matrix[:, l_idx, r_idx], dim=-1)
                pair_force_rev = torch.norm(force_matrix[:, r_idx, l_idx], dim=-1)
                total_pair_force = pair_force + pair_force_rev
                count += (total_pair_force > force_threshold).float()
    else:
        # Fallback to net_forces_w
        net_forces = contact_sensor.data.net_forces_w
        if net_forces is not None:
            for l_idx in left_indices:
                for r_idx in right_indices:
                    l_force = torch.norm(net_forces[:, l_idx], dim=-1)
                    r_force = torch.norm(net_forces[:, r_idx], dim=-1)
                    count += ((l_force > force_threshold) & (r_force > force_threshold)).float()
        else:
            # No contact data available
            pass
    
    return count


def base_lin_vel_y_l2(
    env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Penalize lateral (y) velocity in base frame.
    
    High lateral velocity often indicates instability / near-fall.
    """
    asset = env.scene[asset_cfg.name]
    return torch.square(asset.data.root_lin_vel_b[:, 1])


def base_orientation_roll_yaw_l2(
    env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")
) -> torch.Tensor:
    """Penalize roll and yaw orientation deviation from upright.
    
    Large roll or yaw angle indicates near-fall state.
    """
    asset = env.scene[asset_cfg.name]
    roll, pitch, yaw = math_utils.euler_xyz_from_quat(asset.data.root_quat_w)
    return torch.square(roll) + torch.square(yaw)


def leg_min_distance_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    min_distance: float,
) -> torch.Tensor:
    """Penalize when any left-right leg body pair gets too close.
    
    Computes minimum distance between all left-right body pairs in world frame.
    Acts as early warning for inter-leg collision.
    """
    asset: RigidObject = env.scene[asset_cfg.name]
    
    # Expect 4 bodies: [left_ankle, left_knee, right_ankle, right_knee]
    # with preserve_order=True, indices 0,1 are left, 2,3 are right
    left_indices = asset_cfg.body_ids[:2]
    right_indices = asset_cfg.body_ids[2:]
    
    min_dist = torch.full((env.num_envs,), float('inf'), device=env.device, dtype=torch.float)
    
    for l_idx in left_indices:
        for r_idx in right_indices:
            dist = torch.norm(asset.data.body_pos_w[:, l_idx] - asset.data.body_pos_w[:, r_idx], dim=-1)
            min_dist = torch.minimum(min_dist, dist)
    
    # Penalty when distance < min_distance
    violation = torch.clamp(min_distance - min_dist, min=0.0)
    return violation


def straight_line_heading_reward(
    env: ManagerBasedRLEnv,
    command_name: str,
    std: float = 0.08,
) -> torch.Tensor:
    """Reward for maintaining straight line heading in straight mode."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term(command_name)
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    straight_mask = command_term.env_mode == EnvMode.STRAIGHT
    heading_error = math_utils.wrap_to_pi(
        command_term.straight_heading_target - env.scene["robot"].data.heading_w
    )
    
    reward = torch.exp(-(heading_error / std) ** 2)
    reward = reward * straight_mask.float()
    return reward


def straight_line_lateral_path_reward(
    env: ManagerBasedRLEnv,
    command_name: str,
    std: float = 0.30,
) -> torch.Tensor:
    """Reward for staying on a straight line path in straight mode."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term(command_name)
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    straight_mask = command_term.env_mode == EnvMode.STRAIGHT
    
    init_pos = command_term.straight_init_pos
    init_heading = command_term.straight_heading_target
    current_pos = env.scene["robot"].data.root_pos_w[:, :2]
    
    dx = current_pos[:, 0] - init_pos[:, 0]
    dy = current_pos[:, 1] - init_pos[:, 1]
    lateral_error = -torch.sin(init_heading) * dx + torch.cos(init_heading) * dy
    
    reward = torch.exp(-(lateral_error / std) ** 2)
    reward = reward * straight_mask.float()
    return reward


def lateral_velocity_penalty(
    env: ManagerBasedRLEnv,
    command_name: str,
) -> torch.Tensor:
    """Penalize lateral velocity in straight mode."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term(command_name)
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    straight_mask = command_term.env_mode == EnvMode.STRAIGHT
    base_vel_y = env.scene["robot"].data.root_lin_vel_b[:, 1]
    command_vel_y = command_term.vel_command_b[:, 1]
    
    penalty = (base_vel_y - command_vel_y) ** 2
    penalty = penalty * straight_mask.float()
    return penalty


def straight_heading_error_log(
    env: ManagerBasedRLEnv,
    command_name: str,
) -> torch.Tensor:
    """Log heading error in straight mode (weight=0)."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term(command_name)
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    heading_error = math_utils.wrap_to_pi(
        command_term.straight_heading_target - env.scene["robot"].data.heading_w
    )
    return heading_error.abs()


def straight_cross_track_error_log(
    env: ManagerBasedRLEnv,
    command_name: str,
) -> torch.Tensor:
    """Log cross track error in straight mode (weight=0)."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term(command_name)
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    init_pos = command_term.straight_init_pos
    init_heading = command_term.straight_heading_target
    current_pos = env.scene["robot"].data.root_pos_w[:, :2]
    
    dx = current_pos[:, 0] - init_pos[:, 0]
    dy = current_pos[:, 1] - init_pos[:, 1]
    lateral_error = -torch.sin(init_heading) * dx + torch.cos(init_heading) * dy
    
    return lateral_error.abs()


def straight_torque_saturation_log(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Log torque saturation ratio in straight mode (weight=0)."""
    from .commands.custom_velocity_command import BiasedVelocityCommand, EnvMode
    
    command_term = env.command_manager.get_term("base_velocity")
    if not isinstance(command_term, BiasedVelocityCommand):
        return torch.zeros(env.num_envs, device=env.device)
    
    asset: Articulation = env.scene[asset_cfg.name]
    torque = asset.data.applied_torque[:, asset_cfg.joint_ids]
    torque_limit = torque_limits_vec.unsqueeze(0).expand_as(torque)
    
    sat_ratio = (torque.abs() > 0.85 * torque_limit).float().mean(dim=1)
    return sat_ratio