import math

from isaaclab.utils import configclass
from isaaclab.utils.noise import AdditiveGaussianNoiseCfg as Gausnoise
from isaaclab.assets import ArticulationCfg, AssetBaseCfg
from isaaclab.terrains import TerrainImporterCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.managers import EventTermCfg as EventTerm
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import ObservationGroupCfg as ObsGroup
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
import isaaclab.sim as sim_utils

from limx_rl_forge.assets.config.HU_D04_01 import LIMX_HUD04_01_CFG_SERIAL as HU_D04_01  # isort: skip
from limx_rl_forge.tasks.locomotion.terrain.rough import ROUGH_TERRAINS_CFG as ROUGH_TERRAINS_CFG
import limx_rl_forge.tasks.locomotion.mdp as mdp


BODY_NAMES = [
    'base_link',

    'left_hip_pitch_link',
    'left_hip_roll_link',
    'left_hip_yaw_link',
    'left_knee_link',
    'left_ankle_pitch_link',
    'left_ankle_roll_link',

    'right_hip_pitch_link',
    'right_hip_roll_link',
    'right_hip_yaw_link',
    'right_knee_link',
    'right_ankle_pitch_link',
    'right_ankle_roll_link',

    'waist_yaw_link',
    'waist_roll_link',
    'waist_pitch_link',

    'head_yaw_link',
    'head_pitch_link',

    'left_shoulder_pitch_link',
    'left_shoulder_roll_link',
    'left_shoulder_yaw_link',
    'left_elbow_link',
    'left_wrist_yaw_link',
    'left_wrist_pitch_link',
    'left_wrist_roll_link',

    'right_shoulder_pitch_link',
    'right_shoulder_roll_link',
    'right_shoulder_yaw_link',
    'right_elbow_link',
    'right_wrist_yaw_link',
    'right_wrist_pitch_link',
    'right_wrist_roll_link',
]

JOINT_NAMES = [
    # leg
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    # "left_A_achilles_joint",
    # "left_B_achilles_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    # "right_A_achilles_joint",
    # "right_B_achilles_joint",
    # waist
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    # "waist_B_joint",
    # "waist_A_joint",
    # head
    "head_pitch_joint",
    "head_yaw_joint",
    # arm
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_yaw_joint",
    "left_wrist_pitch_joint",
    "left_wrist_roll_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_yaw_joint",
    "right_wrist_pitch_joint",
    "right_wrist_roll_joint",
]

JOINT_WEIGHT = [
    1, # left_hip_pitch_joint
    1, # left_hip_roll_joint
    1, # left_hip_yaw_joint
    1, # left_knee_joint
    1, # left_ankle_pitch_joint
    1, # left_ankle_roll_joint

    1, # right_hip_pitch_joint
    1, # right_hip_roll_joint
    1, # right_hip_yaw_joint
    1, # right_knee_joint
    1, # right_ankle_pitch_joint
    1, # right_ankle_roll_joint
        
    1, # waist_yaw_joint
    1, # waist_roll_joint
    1, # waist_pitch_joint
        
    1, # head_pitch_joint
    1, # head_yaw_joint

    1, # left_shoulder_pitch_joint
    1, # left_shoulder_roll_joint
    1, # left_shoulder_yaw_joint
    1, # left_elbow_joint
    1, # left_wrist_roll_joint
    1, # left_wrist_yaw_joint
    1, # left_wrist_pitch_joint
        
    1, # right_shoulder_pitch_joint
    1, # right_shoulder_roll_joint
    1, # right_shoulder_yaw_joint
    1, # right_elbow_joint
    1, # right_wrist_roll_joint
    1, # right_wrist_yaw_joint
    1, # right_wrist_pitch_joint
]


@configclass
class MySceneCfg(InteractiveSceneCfg):
    # ground terrain
    terrain = TerrainImporterCfg(
        prim_path="/World/ground",
        terrain_type="generator",
        terrain_generator=ROUGH_TERRAINS_CFG,
        max_init_terrain_level=0,
        collision_group=-1,
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
        ),
        visual_material=sim_utils.MdlFileCfg(
            mdl_path="{NVIDIA_NUCLEUS_DIR}/Materials/Base/Architecture/Shingles_01.mdl",
            project_uvw=True,
        ),
        debug_vis=False,
    )
    # robots
    robot: ArticulationCfg = HU_D04_01.replace(prim_path="{ENV_REGEX_NS}/Robot")
    # sensors
    height_scanner = None
    contact_forces = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/.*", history_length=3, track_air_time=True)
    # lights
    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DistantLightCfg(color=(0.75, 0.75, 0.75), intensity=3000.0),
    )
    sky_light = AssetBaseCfg(
        prim_path="/World/skyLight",
        spawn=sim_utils.DomeLightCfg(color=(0.13, 0.13, 0.13), intensity=1000.0),
    )

@configclass
class VelocityCommandsCfg:
    base_velocity = mdp.UniformVelocityCommandCfg(
        asset_name="robot",
        resampling_time_range=(10.0, 10.0),
        rel_standing_envs=0.1,
        rel_heading_envs=1.0,
        heading_command=True,
        heading_control_stiffness=1.0 / math.pi,
        debug_vis=True,
        ranges=mdp.UniformVelocityCommandCfg.Ranges(
            lin_vel_x=(-0.5, 1.5), lin_vel_y=(-0.3, 0.3), ang_vel_z=(-1.0, 1.0), heading=(-math.pi, math.pi)
        ),
    )

@configclass
class VelocityObservationsCfg:
    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for policy group."""

        # observation terms (order preserved)
        base_ang_vel = ObsTerm(
            func=mdp.base_ang_vel, 
            scale=0.25, 
            noise=Gausnoise(mean=0.0, std=0.15)
        )
        projected_gravity = ObsTerm(
            func=mdp.projected_gravity,
            scale=1.0,
            noise=Gausnoise(mean=0.0, std=0.03),
        )

        velocity_commands = ObsTerm(
            func=mdp.generated_commands, 
            scale=1.0,
            params={"command_name": "base_velocity"},
        )

        joint_pos = ObsTerm(
            func=mdp.joint_pos_rel, 
            scale=1.0,
            noise=Gausnoise(mean=0.0, std=0.075),
            params={
                "asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)
            },
        )
        joint_vel = ObsTerm(
            func=mdp.joint_vel_rel,
            scale=0.05, 
            noise=Gausnoise(mean=0.0, std=0.25),
            params={
                "asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)
            },
        )
        actions = ObsTerm(
            func=mdp.last_action,
            scale=1.0
        )

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    @configclass
    class PrivilegedObsCfg(ObsGroup):
        base_lin_vel = ObsTerm(func=mdp.base_lin_vel, scale=2.0)
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel, scale=0.25)
        projected_gravity = ObsTerm(func=mdp.projected_gravity, scale=1.0)
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(
            func=mdp.joint_pos_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)},
            scale=1.0,
        )
        joint_vel = ObsTerm(
            func=mdp.joint_vel_rel,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)},
            scale=0.05,
        )
        actions = ObsTerm(func=mdp.last_action, scale=1.0)
        # base_height = ObsTerm(func=mdp.base_pos_z, scale=1.0)
        joint_acc = ObsTerm(
            func=mdp.joint_acc,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)},
            scale=0.0025,
        )
        joint_torque = ObsTerm(
            func=mdp.joint_torque,
            params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)},
            scale=0.025,
        )


        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True


        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True

    # observation groups
    policy: PolicyCfg = PolicyCfg()
    critic: PrivilegedObsCfg = PrivilegedObsCfg()


@configclass
class VelocityActionsCfg:
    """Action specifications for the MDP."""

    joint_pos = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=JOINT_NAMES,
        scale={
            ".*hip_pitch.*": 0.2511,
            ".*hip_roll.*": 0.2511,
            ".*hip_yaw.*": 0.2511,
            ".*knee.*": 0.2511,
            ".*ankle.*": 0.1121,
            # ".*A_achilles.*": 0.25,
            # ".*B_achilles.*": 0.25,
            ".*waist.*": 0.1121,
            # ".*waist_yaw.*": 0.1,
            # ".*A_joint.*": 0.1,
            # ".*B_joint.*": 0.1,
            ".*head.*": 0.3141,
            ".*shoulder_pitch.*": 0.1200,
            ".*shoulder_roll.*": 0.1200,
            ".*shoulder_yaw.*": 0.1200,
            ".*elbow.*": 0.1200,
            ".*wrist.*": 0.3141,
        },
        use_default_offset=True,
        preserve_order=True,
    )


@configclass
class VelocityRewardsCfg:
    """Reward terms for the MDP."""

    # -- Task rewards
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_exp, 
        weight=2.5, 
        params={
            "command_name": "base_velocity", 
            "std": math.sqrt(0.09), 
        }
    )
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_exp, 
        weight=2.0, 
        params={
            "command_name": "base_velocity", 
            "std": math.sqrt(0.25)
        }
    )

    # -- gait -- #
    gait = RewTerm(
        func=mdp.feet_gait,
        weight=0.5,
        params={
            "period": 1.2,
            "offset": [0.0, 0.5],
            "threshold": 0.55,
            "command_name": "base_velocity",
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*ankle_roll.*"),
        },
    )

    feet_air_time = RewTerm(
        func=mdp.feet_air_time_positive_biped,
        weight=0.5,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*ankle_roll.*"),
            "command_name": "base_velocity",
            "threshold": 0.5,
        },
    )

    feet_clearance = RewTerm(
        func=mdp.foot_clearance_reward,
        weight=1.0,
        params={
            "std": 0.05,
            "tanh_mult": 2.0,
            "target_height": 0.10,
            "asset_cfg": SceneEntityCfg("robot", body_names=".*ankle_roll.*"),
        },
    )
    # -- termination -- #
    is_alive = RewTerm(func=mdp.is_alive, weight=1.0)
    is_terminated = RewTerm(func=mdp.is_terminated, weight=-1.0)

    # -- torso control -- #
    body_ang_vel = RewTerm(
        func=mdp.body_ang_vel_l2,
        weight=-0.1,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["waist_pitch_link", "base_link"]),
        },
    )
    body_orientation = RewTerm(
        func=mdp.body_projected_gravity_l2, 
        weight=-0.1, 
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["waist_pitch_link", "base_link"]), 
            "std": math.sqrt(0.01)
        }
    )
    body_lin_acc = RewTerm(
        func=mdp.body_lin_acc_l2,
        weight=-0.001,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["waist_pitch_link", "base_link"]),
        },
    )

    # -- penalties -- #
    feet_slide = RewTerm(
        func=mdp.feet_slide, 
        weight=-0.1, 
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*ankle_roll.*"), 
            "asset_cfg": SceneEntityCfg("robot", body_names=".*ankle_roll.*")
        }
    )
    undesired_contacts = RewTerm(
        func=mdp.undesired_contacts,
        weight=-10.0,
        params={
            "sensor_cfg": SceneEntityCfg(
                "contact_forces",
                body_names=["(?!.*ankle.*).*"]
            ),
            "threshold": 1.0,
        },
    )

    joint_position_normalization_amp = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-0.1,
        # params={
        #     "asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True),
        # },
    )

    # -- energy
    dof_acc_l2 = RewTerm(func=mdp.joint_acc_l2, params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)}, weight=-5.0e-7)
    dof_vel_l2 = RewTerm(func=mdp.joint_vel_l2, params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)}, weight=-7.5e-4)
    dof_torques_l2 = RewTerm(func=mdp.joint_torques_l2, params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)}, weight=-3.0e-7)
    joint_pos_limits = RewTerm(func=mdp.joint_pos_limits, params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)}, weight=-1.0)
    applied_torque_limits = RewTerm(func=mdp.applied_torque_limits, params={"asset_cfg": SceneEntityCfg("robot", joint_names=JOINT_NAMES, preserve_order=True)}, weight=-5.0e-2)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-5.0e-3)

    
@configclass
class VelocityTerminationsCfg:
    """Termination terms for the MDP."""

    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    base_contact = DoneTerm(
        func=mdp.illegal_contact,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link"), 
            "threshold": 10.0
        },
    )
    bad_orientation = DoneTerm(
        func=mdp.bad_orientation,
        params={
            "limit_angle": 1.3
        },
    )

    root_height_below_minimum = DoneTerm(
        func=mdp.root_height_below_minimum,
        params={"minimum_height": 0.4},
    )


@configclass
class VelocityEventCfg:
    """Configuration for events."""

    # startup
    physics_material = EventTerm(
        func=mdp.randomize_rigid_body_material,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=".*"),
            "static_friction_range": (0.2, 1.5),
            "dynamic_friction_range": (0.1, 1.2),
            "restitution_range": (0.0, 1.0),
            "num_buckets": 64,
            # "make_consistent": True,
        },
    )

    actuator_gains = EventTerm(
        func=mdp.randomize_actuator_gains,
        mode="reset",
        params={
            "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
            "stiffness_distribution_params": (1.0, 0.1),
            "damping_distribution_params": (1.0, 0.1),
            "operation": "scale",
            "distribution": "gaussian",
        },
    )

    add_base_mass = EventTerm(
        func=mdp.randomize_rigid_body_mass,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="base_link"),
            "mass_distribution_params": (-1.0, 3.0),
            "operation": "add",
        },
    )

    add_waist_mass = EventTerm(
        func=mdp.randomize_rigid_body_mass,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="waist_pitch_link"),
            "mass_distribution_params": (-2.0, 4.0),
            "operation": "add",
        },
    )

    add_hip_mass = EventTerm(
        func=mdp.randomize_rigid_body_mass,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=[".*hip_yaw_link", ".*knee_link", ".*ankle_roll_link"]),
            "mass_distribution_params": (-0.1, 0.1),
            "operation": "add",
        },
    )

    reset_base = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "pose_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5), "yaw": (-3.14, 3.14)},
            "velocity_range": {
                "x": (-0.1, 0.1),
                "y": (-0.1, 0.1),
                "z": (-0.1, 0.1),
                "roll": (-0.1, 0.1),
                "pitch": (-0.1, 0.1),
                "yaw": (-0.1, 0.1),
            },
        },
    )

    random_centroid = EventTerm(
        func= mdp.randomize_rigid_body_centroid,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names="waist_pitch_link"),
            "x_range": (-0.1, 0.1),
            "y_range": (-0.08, 0.08),
            "z_range": (-0.1, 0.1),
        },
    )

    reset_robot_joints = EventTerm(
        func=mdp.reset_joints_by_scale,
        mode="reset",
        params={
            "position_range": (1.0, 1.0),
            "velocity_range": (0.0, 0.0),
        },
    )

    # interval
    push_robot = EventTerm(
        func=mdp.push_by_setting_velocity,
        mode="interval",
        interval_range_s=(5.0, 15.0),
        params={
            "velocity_range": {"x": (-1.0, 1.0), "y": (-0.5, 0.5)}, 
            "asset_cfg": SceneEntityCfg("robot", body_names="base_link"),
        },
    )

    random_inertias = EventTerm(
        func=mdp.randomize_rigid_body_inertia,
        mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["base_link", "waist_pitch_link"]),
            "scale": (0.9, 1.3),
        },
    )

    base_external_force_torque = EventTerm(
        func=mdp.apply_external_force_torque,
        mode="interval",
        interval_range_s=(5.0, 15.0),
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["base_link", "waist_pitch_link"]),
            "force_range": (-5.0, 5.0),
            "torque_range": (-5.0, 5.0),
        },
    )


@configclass
class VelocityCurriculumCfg:
    """Curriculum terms for the MDP."""
    terrain_levels = CurrTerm(func=mdp.terrain_levels_vel)


@configclass
class VelocityEnvCfg(ManagerBasedRLEnvCfg):
    # Scene settings
    scene: MySceneCfg = MySceneCfg(4096, env_spacing=2.5)
    # Basic settings
    observations: VelocityObservationsCfg = VelocityObservationsCfg()
    actions: VelocityActionsCfg = VelocityActionsCfg()
    commands: VelocityCommandsCfg = VelocityCommandsCfg()
    # MDP settings
    rewards: VelocityRewardsCfg = VelocityRewardsCfg()
    terminations: VelocityTerminationsCfg = VelocityTerminationsCfg()
    events: VelocityEventCfg = VelocityEventCfg()
    curriculum: VelocityCurriculumCfg = VelocityCurriculumCfg()


    def __post_init__(self):
        """Post initialization."""
        # general settings
        self.decimation = 5
        self.episode_length_s = 20.0
        # simulation settings
        self.sim.dt = 0.002
        self.sim.render_interval = self.decimation
        self.sim.physics_material = self.scene.terrain.physics_material
        # update sensor update periods
        # we tick all the sensors based on the smallest update period (physics update period)
        if self.scene.height_scanner is not None:
            self.scene.height_scanner.update_period = self.decimation * self.sim.dt
        if self.scene.contact_forces is not None:
            self.scene.contact_forces.update_period = self.sim.dt

        # check if terrain levels curriculum is enabled - if so, enable curriculum for terrain generator
        # this generates terrains with increasing difficulty and is useful for training
        if getattr(self.curriculum, "terrain_levels", None) is not None:
            if self.scene.terrain.terrain_generator is not None:
                self.scene.terrain.terrain_generator.curriculum = True
        else:
            if self.scene.terrain.terrain_generator is not None:
                self.scene.terrain.terrain_generator.curriculum = False

    

@configclass
class VelocityEnvCfg_PLAY(VelocityEnvCfg):
    def __post_init__(self):
        super().__post_init__()
        # make a smaller scene for play
        self.scene.num_envs = 100
        # spawn the robot randomly in the grid (instead of their terrain levels)
        self.scene.robot.spawn.semantic_tags = [("class", "robot")]

        self.scene.terrain.max_init_terrain_level = None
        # reduce the number of terrains to save memory
        self.scene.terrain.terrain_generator.num_rows = 5
        self.scene.terrain.terrain_generator.num_cols = 5
        self.scene.terrain.terrain_generator.curriculum = True
        self.events.push_robot = None
        self.episode_length_s = 10
        self.commands.base_velocity.resampling_time_range = (10.0, 10.0)
