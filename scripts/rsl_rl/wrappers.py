# Copyright information
#
# © [2025] LimX Dynamics Technology Co., Ltd. All rights reserved.

from abc import ABC, abstractmethod

import gymnasium as gym
import torch
from tensordict import TensorDict


class VecEnv(ABC):
    """Abstract class for vectorized environment.

    The vectorized environment is a collection of environments that are synchronized. This means that
    the same action is applied to all environments and the same observation is returned from all environments.

    All extra observations must be provided as a dictionary to "extras" in the step() method. Based on the
    configuration, the extra observations are used for different purposes. The following keys are reserved
    in the "observations" dictionary (if they are present):

    - "critic": The observation is used as input to the critic network. Useful for asymmetric observation spaces.
    """

    num_envs: int
    """Number of environments."""
    num_obs: int
    """Number of observations."""
    num_privileged_obs: int
    """Number of privileged observations."""
    num_commands: int
    """Number of commands."""
    num_scan_dots: int
    """Number of scan dots."""
    num_actions: int
    """Number of actions."""
    max_episode_length: int
    """Maximum episode length."""
    privileged_obs_buf: torch.Tensor
    """Buffer for privileged observations."""
    obs_buf: torch.Tensor
    """Buffer for observations."""
    rew_buf: torch.Tensor
    """Buffer for rewards."""
    reset_buf: torch.Tensor
    """Buffer for resets."""
    episode_length_buf: torch.Tensor  # current episode duration
    """Buffer for current episode lengths."""
    extras: dict
    """Extra information (metrics).

    Extra information is stored in a dictionary. This includes metrics such as the episode reward, episode length,
    etc. Additional information can be stored in the dictionary such as observations for the critic network, etc.
    """
    device: torch.device
    """Device to use."""

    """
    Operations.
    """

    @abstractmethod
    def get_observations(self) -> tuple[torch.Tensor, dict]:
        """Return the current observations.

        Returns:
            Tuple[torch.Tensor, dict]: Tuple containing the observations and extras.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> tuple[torch.Tensor, dict]:
        """Reset all environment instances.

        Returns:
            Tuple[torch.Tensor, dict]: Tuple containing the observations and extras.
        """
        raise NotImplementedError

    @abstractmethod
    def step(self, actions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict]:
        """Apply input action on the environment.

        Args:
            actions (torch.Tensor): Input actions to apply. Shape: (num_envs, num_actions)

        Returns:
            Tuple[torch.Tensor, torch.Tensor, torch.Tensor, dict]:
                A tuple containing the observations, rewards, dones and extra information (metrics).
        """
        raise NotImplementedError
    # @abstractmethod
    # def update_command(self, new_command: torch.Tensor):
    #     raise NotImplementedError


from isaaclab.envs import DirectRLEnv, ManagerBasedRLEnv
from limx_rl_forge.tasks.locomotion.mdp.rewards import DataCache

class LimxDrlEnvWrapper(VecEnv):
    
    def __init__(self, env: ManagerBasedRLEnv):
        """Initializes the wrapper.

        Note:
            The wrapper calls :meth:`reset` at the start since the RSL-RL runner does not call reset.

        Args:
            env: The environment to wrap around.

        Raises:
            ValueError: When the environment is not an instance of :class:`ManagerBasedRLEnv`.
        """
        # check that input is valid
        if not isinstance(env.unwrapped, ManagerBasedRLEnv) and not isinstance(env.unwrapped, DirectRLEnv):
            raise ValueError(
                "The environment must be inherited from ManagerBasedRLEnv or DirectRLEnv. Environment type:"
                f" {type(env)}"
            )
        # initialize the wrapper
        self.env = env
        # store information required by wrapper
        self.num_envs = self.unwrapped.num_envs
        self.device = self.unwrapped.device
        
        self.max_episode_length = self.unwrapped.max_episode_length
        # Action_dim
        self.num_actions = self.unwrapped.action_manager.total_action_dim

        # Obs_dim
        self.privileged_obs_dim = self.unwrapped.observation_manager.group_obs_dim["critic"][0]
        self.policy_obs_dim = self.unwrapped.observation_manager.group_obs_dim["policy"][0]
        # self.gait_obs_dim = self.unwrapped.observation_manager.group_obs_dim["gait_obs"][0]
        
        if "scan_dots" in self.unwrapped.observation_manager.group_obs_dim:
            self.num_scan_dots = self.unwrapped.observation_manager.group_obs_dim["scan_dots"][0]
        else:
            self.num_scan_dots = 0
        if "commands" in self.unwrapped.observation_manager.group_obs_dim:
            self.num_commands = self.unwrapped.observation_manager.group_obs_dim["commands"][0]
        else:
            self.num_commands = 0
        self.num_obs = self.policy_obs_dim #+ self.gait_obs_dim
        self.num_privileged_obs = self.privileged_obs_dim #+ self.gait_obs_dim
        self.num_critic_obs = self.num_privileged_obs + self.num_scan_dots + self.num_commands
        
        self.num_obs_hist = 5
        self.clip_reward = 100.0
        self.obs_hist = torch.zeros(self.num_envs, self.num_obs_hist * self.num_obs, device=self.device, dtype=torch.float)
        self.env.unwrapped.data_cache = DataCache()

        # reset at the start since the RSL-RL runner does not call reset
        self.env.reset()
        self.reset()

    def __str__(self):
        """Returns the wrapper name and the :attr:`env` representation string."""
        return f"<{type(self).__name__}{self.env}>"

    def __repr__(self):
        """Returns the string representation of the wrapper."""
        return str(self)

    """
    Properties -- Gym.Wrapper
    """

    @property
    def cfg(self) -> object:
        """Returns the configuration class instance of the environment."""
        return self.unwrapped.cfg

    @property
    def render_mode(self) -> str | None:
        """Returns the :attr:`Env` :attr:`render_mode`."""
        return self.env.render_mode

    @property
    def observation_space(self) -> gym.Space:
        """Returns the :attr:`Env` :attr:`observation_space`."""
        return self.env.observation_space

    @property
    def action_space(self) -> gym.Space:
        """Returns the :attr:`Env` :attr:`action_space`."""
        return self.env.action_space

    @classmethod
    def class_name(cls) -> str:
        """Returns the class name of the wrapper."""
        return cls.__name__

    @property
    def unwrapped(self) -> ManagerBasedRLEnv:
        """Returns the base environment of the wrapper.

        This will be the bare :class:`gymnasium.Env` environment, underneath all layers of wrappers.
        """
        return self.env.unwrapped

    """
    Properties
    """

    def get_observations(self) -> TensorDict:
        """Returns the current observations of the environment."""
        if hasattr(self.unwrapped, "observation_manager"):
            obs_dict = self.unwrapped.observation_manager.compute()
        else:
            obs_dict = self.unwrapped._get_observations()
        # obs_dict["critic"] = obs_dict["critic"] #torch.cat((obs_dict["privileged_obs"], obs_dict["gait_obs"]), dim=-1)
        # obs_dict["policy"] = obs_dict["policy"] #torch.cat((obs_dict["policy"], obs_dict["gait_obs"]), dim=-1)
        obs_dict["history"] = self.obs_hist

        return TensorDict(obs_dict, batch_size=[self.num_envs])

    @property
    def episode_length_buf(self) -> torch.Tensor:
        """The episode length buffer."""
        return self.unwrapped.episode_length_buf

    @episode_length_buf.setter
    def episode_length_buf(self, value: torch.Tensor):
        """Set the episode length buffer.

        Note:
            This is needed to perform random initialization of episode lengths in RSL-RL.
        """
        self.unwrapped.episode_length_buf = value

    """
    Operations - MDP
    """

    def seed(self, seed: int = -1) -> int:  # noqa: D102
        return self.unwrapped.seed(seed)

    def reset(self) -> tuple[TensorDict, dict]:  # noqa: D102
        # reset the environment
        obs_dict, _ = self.env.reset()
        self.obs_hist = torch.zeros(self.num_envs, self.num_obs_hist * self.num_obs, device=self.device, dtype=torch.float)
        self.env.unwrapped.data_cache.init(self.num_envs, self.device)
        # obs_dict["critic"] = obs_dict["critic"] #torch.cat((obs_dict["privileged_obs"], obs_dict["gait_obs"]), dim=-1)
        # obs_dict["policy"] = obs_dict["policy"] #torch.cat((obs_dict["policy"], obs_dict["gait_obs"]), dim=-1)
        obs_dict["history"] = self.obs_hist

        # return observations
        return TensorDict(obs_dict, batch_size=[self.num_envs]), {"observations": obs_dict}

    def reset_idx(self, idx):
        if idx.any():
            self.obs_hist[idx] = 0
            self.env.unwrapped.data_cache.reset(idx)

    def step(self, actions: torch.Tensor) -> tuple[TensorDict, torch.Tensor, torch.Tensor, dict]:
        # record step information
        obs_dict, rew, terminated, truncated, extras = self.env.step(actions)
        rew[:] = torch.clip(rew[:], 0.0, self.clip_reward)
        self.reset_idx((terminated | truncated))
        # compute dones for compatibility with RSL-RL
        dones = (terminated | truncated).to(dtype=torch.long)
        # move extra observations to the extras dict
        obs = obs_dict["policy"] #torch.cat((obs_dict["policy"], obs_dict["gait_obs"]), dim=-1)

        self.obs_hist = torch.cat((obs, self.obs_hist[:, :self.num_obs * (self.num_obs_hist - 1)]), dim=-1)
        # obs_dict["critic"] = obs_dict["critic"] #torch.cat((obs_dict["privileged_obs"], obs_dict["gait_obs"]), dim=-1)
        obs_dict["history"] = self.obs_hist
        extras["observations"] = obs_dict
        # move time out information to the extras dict
        # this is only needed for infinite horizon tasks
        if not self.unwrapped.cfg.is_finite_horizon:
            extras["time_outs"] = truncated

        # return the step information
        return TensorDict(obs_dict, batch_size=[self.num_envs]), rew, dones, extras

    def close(self):  # noqa: D102
        return self.env.close()