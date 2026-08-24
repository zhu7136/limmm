# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Script to train RL agent with RSL-RL."""

"""Launch Isaac Sim Simulator first."""

import argparse
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
grandparent_dir = os.path.dirname(os.path.dirname(current_dir)) 

sys.path.extend([
    current_dir,
    grandparent_dir,  
    os.path.join(current_dir, "../../source/limx_rl_forge"),
    os.path.join(current_dir, "../../rsl_rl_lib")
])

from isaaclab.app import AppLauncher

# local imports
import cli_args  # isort: skip


# add argparse arguments
parser = argparse.ArgumentParser(description="Train an RL agent with RSL-RL.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument("--video_interval", type=int, default=2000, help="Interval between video recordings (in steps).")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default=None, help="Name of the task.")
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")
parser.add_argument("--max_iterations", type=int, default=None, help="RL Policy training iterations.")
parser.add_argument(
    "--distributed", action="store_true", default=False, help="Run training with multiple GPUs or nodes."
)
# append RSL-RL cli arguments
cli_args.add_rsl_rl_args(parser)
# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()

# always enable cameras to record video
if args_cli.video:
    args_cli.enable_cameras = True

# clear out sys.argv for Hydra
sys.argv = [sys.argv[0]] + hydra_args

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

import gymnasium as gym
import os
import torch
from datetime import datetime

from rsl_rl.runners import OnPolicyRunner

from isaaclab.envs import (
    DirectMARLEnv,
    DirectMARLEnvCfg,
    DirectRLEnvCfg,
    ManagerBasedRLEnvCfg,
    multi_agent_to_single_agent,
)
from isaaclab.utils.dict import print_dict
from isaaclab.utils.io import dump_pickle, dump_yaml

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

from wrappers import LimxDrlEnvWrapper
import limx_rl_forge.tasks

# PLACEHOLDER: Extension template (do not remove this comment)

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.deterministic = False
torch.backends.cudnn.benchmark = False


@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlOnPolicyRunnerCfg):
    """Train with RSL-RL agent."""
    # override configurations with non-hydra CLI arguments
    agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
    agent_cfg.max_iterations = (
        args_cli.max_iterations if args_cli.max_iterations is not None else agent_cfg.max_iterations
    )

    # set the environment seed
    # note: certain randomizations occur in the environment initialization so we set the seed here
    env_cfg.seed = agent_cfg.seed
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # multi-gpu training configuration
    if args_cli.distributed:
        env_cfg.sim.device = f"cuda:{app_launcher.local_rank}"
        agent_cfg.device = f"cuda:{app_launcher.local_rank}"

        # set seed to have diversity in different threads
        seed = agent_cfg.seed + app_launcher.local_rank
        env_cfg.seed = seed
        agent_cfg.seed = seed

    # specify directory for logging experiments
    log_root_path = os.path.join("logs", "rsl_rl", args_cli.note)
    log_root_path = os.path.abspath(log_root_path)
    print(f"[INFO] Logging experiment in directory: {log_root_path}")
    # specify directory for logging runs: {time-stamp}_{run_name}
    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # The Ray Tune workflow extracts experiment name using the logging line below, hence, do not change it (see PR #2346, comment-2819298849)
    print(f"Exact experiment name requested from command line: {log_dir}")
    if agent_cfg.run_name:
        log_dir += f"_{agent_cfg.run_name}"
    log_dir = os.path.join(log_root_path, log_dir)

    # create isaac environment
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    # convert to single-agent instance if required by the RL algorithm
    if isinstance(env.unwrapped, DirectMARLEnv):
        env = multi_agent_to_single_agent(env)

    # save resume path before creating a new log_dir
    if agent_cfg.resume or agent_cfg.algorithm.class_name == "Distillation":
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)

    # wrap for video recording
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "train"),
            "step_trigger": lambda step: step % args_cli.video_interval == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    # wrap around environment for rsl-rl
    env = LimxDrlEnvWrapper(env)

    # add custom metrics logging to extras
    class MetricsLoggingWrapper:
        def __init__(self, env):
            self.env = env
            # pre-fetch torque limits (shape: [num_envs, num_joints])
            robot = self.env.unwrapped.scene["robot"]
            self._effort_limits = robot.root_physx_view.get_dof_max_forces().to(robot.device).clone()
            # warmup: filter envs in first ~1.0s after reset
            self._warmup_steps = int(1.0 / self.env.unwrapped.step_dt)
            
        def step(self, actions):
            # capture pre-step high-speed command mask for correct fall attribution
            raw_env = self.env.unwrapped
            robot = raw_env.scene["robot"]
            command_vx_pre = raw_env.command_manager.get_command("base_velocity")[:, 0].clone()
            
            obs, rew, dones, extras = self.env.step(actions)
            
            # post-step data
            base_vx = robot.data.root_lin_vel_b[:, 0]
            command_vx = command_vx_pre  # use pre-step command for consistency
            
            if "log" not in extras:
                extras["log"] = {}
            
            # global metrics
            extras["log"]["Metrics/base_vx"] = base_vx.mean().item()
            extras["log"]["Metrics/command_vx"] = command_vx.mean().item()
            
            # high-speed bucket metrics
            import torch
            
            # termination/fall detection
            timeouts = extras.get("time_outs", torch.zeros_like(dones, dtype=torch.bool, device=dones.device)).bool()
            falls = dones.bool() & ~timeouts
            
            # warmup filter: exclude envs recently reset
            valid = raw_env.episode_length_buf > self._warmup_steps
            
            for threshold in (2.0, 2.3, 2.5, 2.6, 2.7, 2.8):
                mask = (command_vx > threshold) & valid
                prefix = f"Metrics/high_speed_gt_{str(threshold).replace('.', '_')}"
                
                # sample fraction & count
                extras["log"][f"{prefix}/sample_fraction"] = mask.float().mean().item()
                extras["log"][f"{prefix}/sample_count"] = mask.sum().item()
                
                if mask.any():
                    cmd_h = command_vx[mask]
                    actual_h = base_vx[mask]
                    abs_error = (actual_h - cmd_h).abs()
                    
                    extras["log"][f"{prefix}/command_vx"] = cmd_h.mean().item()
                    extras["log"][f"{prefix}/base_vx"] = actual_h.mean().item()
                    extras["log"][f"{prefix}/error_vx"] = abs_error.mean().item()
                    extras["log"][f"{prefix}/undertracking_vx"] = (cmd_h - actual_h).clamp_min(0).mean().item()
                    extras["log"][f"{prefix}/success_rate_0p2"] = (abs_error < 0.2).float().mean().item()
                    extras["log"][f"{prefix}/success_rate_0p25"] = (abs_error < 0.25).float().mean().item()
                    
                    # torque saturation
                    torque = robot.data.applied_torque[mask].abs()
                    effort_limit = self._effort_limits[mask].abs().clamp_min(1e-6)
                    torque_ratio = torque / effort_limit
                    saturated = torque_ratio >= 0.95
                    
                    extras["log"][f"{prefix}/joint_torque_sat_rate"] = saturated.float().mean().item()
                    extras["log"][f"{prefix}/env_torque_sat_rate"] = saturated.any(dim=1).float().mean().item()
                    extras["log"][f"{prefix}/max_torque_ratio"] = torque_ratio.max().item()
                    
                    # termination / fall rates (use PRE-STEP high-speed mask)
                    high_mask_pre = command_vx_pre > threshold
                    high_done = dones.bool() & high_mask_pre
                    high_fall = falls & high_mask_pre
                    
                    extras["log"][f"{prefix}/done_count"] = high_done.sum().item()
                    extras["log"][f"{prefix}/fall_count"] = high_fall.sum().item()
                    
                    if high_done.any():
                        extras["log"][f"{prefix}/fall_rate_on_done"] = (
                            high_fall.sum().float() / high_done.sum()
                        ).item()
            
            return obs, rew, dones, extras
            
        def __getattr__(self, name):
            return getattr(self.env, name)

    env = MetricsLoggingWrapper(env)

    # create runner from rsl-rl
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=log_dir, device=agent_cfg.device)
    # write git state to logs
    runner.add_git_repo_to_log(__file__)
    # load the checkpoint
    if agent_cfg.resume or agent_cfg.algorithm.class_name == "Distillation":
        print(f"[INFO]: Loading model checkpoint from: {resume_path}")
        # load previously trained model
        runner.load(resume_path)

    # dump the configuration into log-directory
    dump_yaml(os.path.join(log_dir, "params", "env.yaml"), env_cfg)
    dump_yaml(os.path.join(log_dir, "params", "agent.yaml"), agent_cfg)
    dump_pickle(os.path.join(log_dir, "params", "env.pkl"), env_cfg)
    dump_pickle(os.path.join(log_dir, "params", "agent.pkl"), agent_cfg)

    # run training
    runner.learn(num_learning_iterations=agent_cfg.max_iterations, init_at_random_ep_len=True)

    # close the simulator
    env.close()


if __name__ == "__main__":
    # run the main function
    main()
    # close sim app
    simulation_app.close()
