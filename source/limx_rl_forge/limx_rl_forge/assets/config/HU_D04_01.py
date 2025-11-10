# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Configuration for Agility robots.

The following configurations are available:

* :obj:`LIMX_CFG`: Limx robot with simple PD controller for the legs

"""

import isaaclab.sim as sim_utils
# from locomotion.assets.actuators import DelayedImplicitActuatorCfg
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.actuators import DelayedPDActuatorCfg
from isaaclab.assets.articulation import ArticulationCfg
import os

ARMATURE_LEG = 0.14125
ARMATURE_ANKLE_WAIST = 0.1845504
ARMATURE_ANKLE_WAIST_BACK = 0.094889232
ARMATURE_HEAD_WRIST = 0.0153218
ARMATURE_SHOULDER_ELBOW = 0.0886706 

NATURAL_FREQ = 5.0 * 2.0 * 3.1415926535 # 5Hz
DAMPING_RATIO = 2.0

STIFFNESS_LEG = ARMATURE_LEG * NATURAL_FREQ ** 2 
STIFFNESS_ANKLE_WAIST = ARMATURE_ANKLE_WAIST_BACK * NATURAL_FREQ ** 2
STIFFNESS_HEAD_WRIST = ARMATURE_HEAD_WRIST * NATURAL_FREQ ** 2
STIFFNESS_SHOULDER_ELBOW = ARMATURE_SHOULDER_ELBOW * NATURAL_FREQ ** 2

DAMPING_LEG = 2.0 * DAMPING_RATIO * ARMATURE_LEG * NATURAL_FREQ
DAMPING_ANKLE_WAIST = 2.0 * DAMPING_RATIO * ARMATURE_ANKLE_WAIST_BACK * NATURAL_FREQ
DAMPING_HEAD_WRIST = 2.0 * DAMPING_RATIO * ARMATURE_HEAD_WRIST * NATURAL_FREQ
DAMPING_SHOULDER_ELBOW = 2.0 * DAMPING_RATIO * ARMATURE_SHOULDER_ELBOW * NATURAL_FREQ

##
# Configuration
##

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
usd_dir_path = os.path.join(BASE_DIR, "../../../../../humanoid-description/HU_D04_description/usd/")
robot_usd = "HU_D04_01.usd"

LIMX_HUD04_01_CFG_SERIAL = ArticulationCfg(
    spawn=sim_utils.UsdFileCfg(
        usd_path=usd_dir_path + robot_usd,
        activate_contact_sensors=True,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            retain_accelerations=False,
            linear_damping=0.0,
            angular_damping=0.0,
            max_linear_velocity=1000.0,
            max_angular_velocity=1000.0,
            max_depenetration_velocity=3.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=True,
            solver_position_iteration_count=8,
            solver_velocity_iteration_count=1,
        ),
        # collision_props=sim_utils.CollisionPropertiesCfg(
        #     contact_offset=0.01, rest_offset=0.005
        # ),
        joint_drive_props=sim_utils.JointDrivePropertiesCfg(drive_type="force")
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.92),
        joint_pos={
            'left_hip_pitch_joint': -0.15,
            'left_hip_roll_joint': -0.00,
            'left_hip_yaw_joint': -0.05,
            'left_knee_joint': 0.30,
            'left_ankle_pitch_joint': -0.16,
            'left_ankle_roll_joint': 0.0,

            'right_hip_pitch_joint': -0.15,
            'right_hip_roll_joint': 0.00,
            'right_hip_yaw_joint': 0.05,
            'right_knee_joint': 0.3,
            'right_ankle_pitch_joint': -0.16,
            'right_ankle_roll_joint': 0.0,

            'waist_yaw_joint': 0.0,
            'waist_roll_joint': 0.0,
            'waist_pitch_joint': 0.0,

            'head_pitch_joint': 0.0,
            'head_yaw_joint': 0.0,

            'left_shoulder_pitch_joint': 0.1,
            'left_shoulder_roll_joint': 0.1,
            'left_shoulder_yaw_joint': -0.2,
            'left_elbow_joint': -0.2,
            'left_wrist_yaw_joint': 0.0,
            'left_wrist_pitch_joint': 0.0,
            'left_wrist_roll_joint': 0.0,

            'right_shoulder_pitch_joint': 0.1,
            'right_shoulder_roll_joint': -0.1,
            'right_shoulder_yaw_joint': 0.2,
            'right_elbow_joint': -0.2,
            'right_wrist_yaw_joint': 0.0,
            'right_wrist_pitch_joint': 0.0,
            'right_wrist_roll_joint': 0.0,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=1.00,
    actuators={
        "robot": ImplicitActuatorCfg(
            joint_names_expr=[
                '.*_hip_pitch_joint',
                '.*_hip_roll_joint',
                '.*_hip_yaw_joint',
                '.*_knee_joint',

                ".*_ankle_pitch_joint",
                ".*_ankle_roll_joint",

                'waist_yaw_joint',
                'waist_roll_joint',
                'waist_pitch_joint',

                'head_pitch_joint',
                'head_yaw_joint',

                '.*_shoulder_pitch_joint',
                '.*_shoulder_roll_joint',
                '.*_shoulder_yaw_joint',
                '.*_elbow_joint',

                '.*_wrist_yaw_joint',
                '.*_wrist_pitch_joint',
                '.*_wrist_roll_joint',
            ],
            stiffness={
                '.*_hip_pitch_joint': STIFFNESS_LEG,
                '.*_hip_roll_joint': STIFFNESS_LEG,
                '.*_hip_yaw_joint': STIFFNESS_LEG,
                '.*_knee_joint': STIFFNESS_LEG,

                ".*_ankle_pitch_joint": STIFFNESS_ANKLE_WAIST,
                ".*_ankle_roll_joint": STIFFNESS_ANKLE_WAIST,

                'waist_yaw_joint': STIFFNESS_ANKLE_WAIST,
                'waist_roll_joint': STIFFNESS_ANKLE_WAIST,
                'waist_pitch_joint': STIFFNESS_ANKLE_WAIST,

                'head_pitch_joint': STIFFNESS_HEAD_WRIST,
                'head_yaw_joint': STIFFNESS_HEAD_WRIST,

                '.*_shoulder_pitch_joint': STIFFNESS_SHOULDER_ELBOW,
                '.*_shoulder_roll_joint': STIFFNESS_SHOULDER_ELBOW,
                '.*_shoulder_yaw_joint': STIFFNESS_SHOULDER_ELBOW,
                '.*_elbow_joint': STIFFNESS_SHOULDER_ELBOW,

                '.*_wrist_yaw_joint': STIFFNESS_HEAD_WRIST,
                '.*_wrist_pitch_joint': STIFFNESS_HEAD_WRIST,
                '.*_wrist_roll_joint': STIFFNESS_HEAD_WRIST,
            },
            damping={
                '.*_hip_pitch_joint': DAMPING_LEG,
                '.*_hip_roll_joint': DAMPING_LEG,
                '.*_hip_yaw_joint': DAMPING_LEG,
                '.*_knee_joint': DAMPING_LEG,

                ".*_ankle_pitch_joint": DAMPING_ANKLE_WAIST,
                ".*_ankle_roll_joint": DAMPING_ANKLE_WAIST,

                'waist_yaw_joint': DAMPING_ANKLE_WAIST,
                'waist_roll_joint': DAMPING_ANKLE_WAIST,
                'waist_pitch_joint': DAMPING_ANKLE_WAIST,

                'head_pitch_joint': DAMPING_HEAD_WRIST,
                'head_yaw_joint': DAMPING_HEAD_WRIST,

                '.*_shoulder_pitch_joint': DAMPING_SHOULDER_ELBOW,
                '.*_shoulder_roll_joint': DAMPING_SHOULDER_ELBOW,
                '.*_shoulder_yaw_joint': DAMPING_SHOULDER_ELBOW,
                '.*_elbow_joint': DAMPING_SHOULDER_ELBOW,

                '.*_wrist_yaw_joint': DAMPING_HEAD_WRIST,
                '.*_wrist_pitch_joint': DAMPING_HEAD_WRIST,
                '.*_wrist_roll_joint': DAMPING_HEAD_WRIST,
            },
            effort_limit={
                '.*_hip_pitch_joint': 140.,
                '.*_hip_roll_joint': 140.,
                '.*_hip_yaw_joint': 140.,
                '.*_knee_joint': 140.,

                ".*_ankle_pitch_joint": 80,
                ".*_ankle_roll_joint": 80,

                'waist_yaw_joint': 42,
                'waist_roll_joint': 80,
                'waist_pitch_joint': 80,

                'head_pitch_joint': 19.0,
                'head_yaw_joint': 19.0,

                '.*_shoulder_pitch_joint': 42,
                '.*_shoulder_roll_joint': 42,
                '.*_shoulder_yaw_joint': 42,
                '.*_elbow_joint': 42,

                '.*_wrist_yaw_joint': 19,
                '.*_wrist_pitch_joint': 19,
                '.*_wrist_roll_joint': 19,
            },
            velocity_limit={
                '.*_hip_pitch_joint': 12,
                '.*_hip_roll_joint': 12,
                '.*_hip_yaw_joint': 12,
                '.*_knee_joint': 12,

                ".*_ankle_pitch_joint": 13.6,
                ".*_ankle_roll_joint": 13.6,

                'waist_yaw_joint': 13.6,
                'waist_roll_joint': 13.6,
                'waist_pitch_joint': 13.6,

                'head_pitch_joint': 13,
                'head_yaw_joint': 13,

                '.*_shoulder_pitch_joint': 19.6,
                '.*_shoulder_roll_joint': 19.6,
                '.*_shoulder_yaw_joint': 19.6,
                '.*_elbow_joint': 19.6,

                '.*_wrist_yaw_joint': 13,
                '.*_wrist_pitch_joint': 13,
                '.*_wrist_roll_joint': 13,
            },
            armature={
                '.*_hip_pitch_joint': ARMATURE_LEG,
                '.*_hip_roll_joint': ARMATURE_LEG,
                '.*_hip_yaw_joint': ARMATURE_LEG,
                '.*_knee_joint': ARMATURE_LEG,

                ".*_ankle_pitch_joint": ARMATURE_ANKLE_WAIST,
                ".*_ankle_roll_joint": ARMATURE_ANKLE_WAIST,

                'waist_yaw_joint': ARMATURE_ANKLE_WAIST,
                'waist_roll_joint': ARMATURE_ANKLE_WAIST,
                'waist_pitch_joint': ARMATURE_ANKLE_WAIST,

                'head_pitch_joint': ARMATURE_HEAD_WRIST,
                'head_yaw_joint': ARMATURE_HEAD_WRIST,

                '.*_shoulder_pitch_joint': ARMATURE_SHOULDER_ELBOW,
                '.*_shoulder_roll_joint': ARMATURE_SHOULDER_ELBOW,
                '.*_shoulder_yaw_joint': ARMATURE_SHOULDER_ELBOW,
                '.*_elbow_joint': ARMATURE_SHOULDER_ELBOW,

                '.*_wrist_yaw_joint': ARMATURE_HEAD_WRIST,
                '.*_wrist_pitch_joint': ARMATURE_HEAD_WRIST,
                '.*_wrist_roll_joint': ARMATURE_HEAD_WRIST,
            },
            friction={
                '.*hip_pitch_joint': 2.0,
                '.*hip_roll_joint': 2.0,
                '.*hip_yaw_joint': 1.6,
                '.*knee_joint': 2.6,
                ".*ankle_pitch_joint": 1.0,
                ".*ankle_roll_joint": 1.0,

                'waist_yaw_joint': 0.48, 
                'waist_roll_joint': 1.1,
                'waist_pitch_joint': 4.89,

                'head_pitch_joint': 0.,
                'head_yaw_joint': 0.,

                '.*shoulder_pitch_joint': 0.60,
                '.*shoulder_roll_joint': 0.6,
                '.*shoulder_yaw_joint': 0.45,
                '.*elbow_joint': 0.35,
                '.*wrist_yaw_joint': 0.3,
                '.*wrist_pitch_joint': 0.3,
                '.*wrist_roll_joint': 0.3,
            },
            # dynamic_friction={
            #     '.*hip_pitch_joint': 1.2,
            #     '.*hip_roll_joint': 1.2,
            #     '.*hip_yaw_joint': 1.4,
            #     '.*knee_joint': 2.57,
            #     ".*ankle_pitch_joint": 0.95,
            #     ".*ankle_roll_joint": 0.86,

            #     'waist_yaw_joint': 0.48,
            #     'waist_roll_joint': 1.0, # !!
            #     'waist_pitch_joint': 4.06,

            #     'head_pitch_joint': 0.,
            #     'head_yaw_joint': 0.,

            #     '.*shoulder_pitch_joint': 0.4,
            #     '.*shoulder_roll_joint': 0.54,
            #     '.*shoulder_yaw_joint': 0.25,
            #     '.*elbow_joint': 0.28,
            #     '.*wrist_yaw_joint': 0.24,
            #     '.*wrist_pitch_joint': 0.30,
            #     '.*wrist_roll_joint': 0.28,
            # },
            # viscous_friction={
            #     '.*hip_pitch_joint': 2.54,
            #     '.*hip_roll_joint': 2.55,
            #     '.*hip_yaw_joint': 0.44,
            #     '.*knee_joint': 0.63,
            #     ".*ankle_pitch_joint": 0.07,
            #     ".*ankle_roll_joint": 0.09,

            #     'waist_yaw_joint': 0.28,
            #     'waist_roll_joint': 2.0,
            #     'waist_pitch_joint': 1.52,

            #     'head_pitch_joint': 0.,
            #     'head_yaw_joint': 0.,

            #     '.*shoulder_pitch_joint': 0.03,
            #     '.*shoulder_roll_joint': 0.01,
            #     '.*shoulder_yaw_joint': 0.06,
            #     '.*elbow_joint': 0.02,
            #     '.*wrist_yaw_joint': 0.01,
            #     '.*wrist_pitch_joint': 0.03,
            #     '.*wrist_roll_joint': 0.02,
            # },
            # min_delay=0,  # physics time steps (min: 1.0*0=0.0ms)
            # max_delay=0,  # physics time steps (max: 1.0*5=5.0ms)
        ),
    },
)