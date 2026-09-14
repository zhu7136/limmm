"""评估脚本：固定速度测试直线行走能力"""

import argparse
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
grandparent_dir = os.path.dirname(os.path.dirname(current_dir))

sys.path.extend([
    current_dir,
    grandparent_dir,
    os.path.join(current_dir, "../../source/limx_rl_forge"),
    os.path.join(current_dir, "../../rsl_rl_lib")
])

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="评估直线行走能力")
parser.add_argument("--num_envs", type=int, default=100, help="环境数量")
parser.add_argument("--task", type=str, default="LimX-Oli-31dof-Velocity", help="任务名称")
parser.add_argument("--checkpoint", type=str, required=True, help="checkpoint路径")
parser.add_argument("--speed", type=float, default=2.8, help="测试速度 (m/s)")
parser.add_argument("--num_episodes", type=int, default=100, help="评估episode数")
parser.add_argument("--episode_length", type=float, default=60.0, help="episode长度 (秒)")

AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = False

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch
import numpy as np
from rsl_rl.runners import OnPolicyRunner
from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg
from wrappers import LimxDrlEnvWrapper
import limx_rl_forge.tasks
from isaaclab.utils.dict import print_dict

@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg, agent_cfg):
    """主评估函数"""
    # 配置环境
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.seed = 42
    
    # 创建环境
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
    env = LimxDrlEnvWrapper(env)
    
    # 加载模型
    print(f"[INFO] Loading checkpoint: {args_cli.checkpoint}")
    ppo_runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    ppo_runner.load(args_cli.checkpoint)
    policy = ppo_runner.get_inference_policy(device=env.unwrapped.device)
    
    # 评估统计
    stats = {
        "completion_rate": [],
        "fall_rate": [],
        "velocity_error": [],
        "torque_saturation": [],
        "joint_torque_saturation": [],
        "episode_reward": [],
    }
    
    # 获取command manager
    command_manager = env.unwrapped.command_manager
    command_term = command_manager.get_term("base_velocity")
    
    # 设置固定速度
    num_envs = args_cli.num_envs
    target_speed = args_cli.speed
    
    # 重置环境
    obs, _ = env.get_observations()
    
    # 运行评估
    total_episodes = 0
    episode_returns = torch.zeros(num_envs, device=env.unwrapped.device)
    episode_lengths = torch.zeros(num_envs, device=env.unwrapped.device)
    done_mask = torch.zeros(num_envs, dtype=torch.bool, device=env.unwrapped.device)
    
    # 记录每个环境的状态
    env_fallen = torch.zeros(num_envs, dtype=torch.bool, device=env.unwrapped.device)
    env_completed = torch.zeros(num_envs, dtype=torch.bool, device=env.unwrapped.device)
    env_distance = torch.zeros(num_envs, device=env.unwrapped.device)
    env_initial_pos = torch.zeros(num_envs, 2, device=env.unwrapped.device)
    
    step_count = 0
    max_steps = int(args_cli.episode_length / env.unwrapped.step_dt)
    
    print(f"[INFO] 开始评估: 速度={target_speed}m/s, episodes={args_cli.num_episodes}, episode长度={args_cli.episode_length}s")
    
    while total_episodes < args_cli.num_episodes and simulation_app.is_running():
        with torch.inference_mode():
            # 设置固定速度命令
            for i in range(num_envs):
                if not done_mask[i]:
                    command_term.vel_command_b[i, 0] = target_speed
                    command_term.vel_command_b[i, 1] = 0.0
                    command_term.vel_command_b[i, 2] = 0.0
                    command_term.is_straight_env[i] = True
                    command_term.env_mode[i] = 0  # STRAIGHT
            
            # 执行动作（使用推理模式，禁止采样）
            actions = policy(obs)
            obs, rewards, terminated, truncated, infos = env.step(actions)
            
            # 更新统计
            step_count += 1
            episode_returns += rewards
            episode_lengths += 1
            
            # 检查是否完成或跌倒
            for i in range(num_envs):
                if not done_mask[i]:
                    # 检查跌倒
                    if terminated[i] or truncated[i]:
                        done_mask[i] = True
                        total_episodes += 1
                        
                        # 判断是否跌倒（高度低于阈值或base接触）
                        base_height = env.unwrapped.scene["robot"].data.root_pos_w[i, 2]
                        if base_height < 0.4:
                            env_fallen[i] = True
                        else:
                            env_completed[i] = True
                        
                        # 记录统计
                        stats["episode_reward"].append(episode_returns[i].item())
                        stats["fall_rate"].append(1.0 if env_fallen[i] else 0.0)
                        stats["completion_rate"].append(1.0 if env_completed[i] and not env_fallen[i] else 0.0)
                        
                        # 计算速度误差
                        actual_vx = env.unwrapped.scene["robot"].data.root_lin_vel_b[i, 0].item()
                        stats["velocity_error"].append(abs(actual_vx - target_speed))
                        
                        # 重置环境状态
                        episode_returns[i] = 0
                        episode_lengths[i] = 0
                        env_fallen[i] = False
                        env_completed[i] = False
            
            # 检查超时
            if step_count >= max_steps:
                # 强制结束所有未完成的环境
                for i in range(num_envs):
                    if not done_mask[i]:
                        done_mask[i] = True
                        total_episodes += 1
                        env_completed[i] = True  # 60秒完成
                        
                        stats["episode_reward"].append(episode_returns[i].item())
                        stats["fall_rate"].append(0.0)
                        stats["completion_rate"].append(1.0)
                        
                        actual_vx = env.unwrapped.scene["robot"].data.root_lin_vel_b[i, 0].item()
                        stats["velocity_error"].append(abs(actual_vx - target_speed))
                
                # 重置
                done_mask[:] = False
                episode_returns[:] = 0
                episode_lengths[:] = 0
                step_count = 0
                
                # 重置环境
                env.unwrapped.reset()
                obs, _ = env.get_observations()
            
            # 打印进度
            if total_episodes % 10 == 0 and total_episodes > 0:
                print(f"[INFO] 已完成 {total_episodes}/{args_cli.num_episodes} episodes")
    
    # 输出结果
    print("\n" + "="*60)
    print(f"评估结果: 速度={target_speed}m/s")
    print("="*60)
    
    results = {
        "completion_rate": np.mean(stats["completion_rate"]) if stats["completion_rate"] else 0,
        "fall_rate": np.mean(stats["fall_rate"]) if stats["fall_rate"] else 0,
        "velocity_error": np.mean(stats["velocity_error"]) if stats["velocity_error"] else 0,
        "episode_reward_mean": np.mean(stats["episode_reward"]) if stats["episode_reward"] else 0,
        "episode_reward_std": np.std(stats["episode_reward"]) if stats["episode_reward"] else 0,
    }
    
    print(f"60秒完成率: {results['completion_rate']*100:.1f}%")
    print(f"跌倒率: {results['fall_rate']*100:.1f}%")
    print(f"速度误差: {results['velocity_error']:.3f} m/s")
    print(f"平均奖励: {results['episode_reward_mean']:.2f} ± {results['episode_reward_std']:.2f}")
    
    # 检查是否通过验收标准
    passed = True
    if results["completion_rate"] < 0.90:
        print(f"[FAIL] 完成率 {results['completion_rate']*100:.1f}% < 90%")
        passed = False
    if results["fall_rate"] > 0.05:
        print(f"[FAIL] 跌倒率 {results['fall_rate']*100:.1f}% > 5%")
        passed = False
    if results["velocity_error"] > 0.15:
        print(f"[FAIL] 速度误差 {results['velocity_error']:.3f} > 0.15 m/s")
        passed = False
    
    if passed:
        print("[PASS] 所有验收标准通过!")
    else:
        print("[FAIL] 部分验收标准未通过")
    
    env.close()
    return results


if __name__ == "__main__":
    main()
    simulation_app.close()
