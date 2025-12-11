# English | [中文](README_cn.md)

# humanoid-rl-isaaclab

<img src="https://img.shields.io/badge/IsaacLab-2.0.0-green"> <img src="https://img.shields.io/badge/IsaacSim-4.5.0-silver"> <img src="https://img.shields.io/badge/PyTorch-2.5.1-orange"> <img src="https://img.shields.io/badge/License-Apache 2.0-yellow">

## Overview
This project provides the reinforcement learning environments and training scripts for LimX Dynamics **Oli (Humanoid)** robots.

<div align="center">

| <div align="center"> Isaac Lab </div> | <div align="center"> Mujoco </div> | <div align="center"> Physical </div> |
|--- | --- | --- |
| <img src="./source/limx_rl_forge/docs/isaaclab.gif" style="width: 200px; height: 200px;"> | <img src="./source/limx_rl_forge/docs/mujoco.gif" style="width: 200px; height: 200px;"> | <img src="./source/limx_rl_forge/docs/physical.gif" style="width: 200px; height: 200px;"> |
</div>

## Quickstart 

### Installation
- Create a virtual environment with **Python 3.10**:
``` sh
conda create -n limx python=3.10
conda activate limx
```

- Install **PyTorch 2.5.1** build based on the CUDA version available on your system:
``` sh
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

- Install **IsaacSim 4.5.0** packages:
``` sh
pip install isaacsim[all,extscache]==4.5.0 --extra-index-url https://pypi.nvidia.com
```

- Download **IsaacLab 2.0.0** from [Releases](https://github.com/isaac-sim/IsaacLab/releases), and install it by:
``` sh
./isaaclab.sh -i none
```

- Clone this repository and install the dependencies:
``` sh
git clone https://github.com/limxdynamics/humanoid-rl-isaaclab.git
pip install -r requirements.txt
```

- Download the robot description files:
``` sh
git clone https://github.com/limxdynamics/humanoid-description.git
```

- Verify that the installation and list all the available environments:
``` sh
python scripts/list_envs.py
```
Then you will see the following output:
<img src="./source/limx_rl_forge/docs/list_envs.png">

### Training

- Training your agent by
``` sh
python scripts/rsl_rl/train.py --headless --task LimX-Oli-31dof-Velocity
```

- Evaluate a trained agent by
``` sh
python scripts/rsl_rl/play.py --task LimX-Oli-31dof-Velocity
```


## Deployment

Please refer to the following projects for the `sim2sim` and `sim2real` instructions:
- [Deployment with Python](https://github.com/limxdynamics/humanoid-rl-deploy-python)
- [Deployment with C++](https://github.com/limxdynamics/humanoid-rl-deploy-cpp)

## Acknowledgments
This project is built upon several excellent projects:
- [IsaacLab](https://github.com/isaac-sim/IsaacLab)
- [Mujoco](https://github.com/google-deepmind/mujoco.git)
- [rsl_rl](https://github.com/leggedrobotics/rsl_rl)