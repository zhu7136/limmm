import gymnasium as gym

##
# Register Gym environments.
##
gym.register(
    id="LimX-Oli-31dof-Velocity",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.velocity_env_cfg:VelocityEnvCfg",
        "rsl_rl_cfg_entry_point": f"limx_rl_forge.tasks.locomotion.agents.rsl_rl_ppo_cfg:PPORunnerCfg",
    },
)

gym.register(
    id="LimX-Oli-31dof-Velocity-Play",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.velocity_env_cfg:VelocityEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"limx_rl_forge.tasks.locomotion.agents.rsl_rl_ppo_cfg:PPORunnerCfg",
    },
)