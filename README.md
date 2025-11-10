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

### Sim2Sim

- Run the inference code and export the model, you will find a generated `policy.onnx` in the checkpoint folder:
``` sh
python scripts/rsl_rl/play.py --task LimX-Oli-31dof-Velocity --checkpoint path-to-model
```

- Install the `humanoid-rl-deploy-python` and `humanoid-mujoco-sim` toolkits by
``` sh
mkdir limx_ws
# Download the Mujoco simulator
git clone --recurse git@github.com:limxdynamics/humanoid-mujoco-sim.git
pip install humanoid-mujoco-sim/limxsdk-lowlevel/python3/amd64/limxsdk-*-py3-none-any.whl
# Download the motion control algorithm
git clone git@github.com:limxdynamics/humanoid-rl-deploy-python.git
# Set the robot model
cd ~/limx_ws
tree -L 1 humanoid-rl-deploy-python/controllers
echo 'export ROBOT_TYPE=HU_D03_03' >> ~/.bashrc && source ~/.bashrc # depends on your robot type
```

- Open a Bash terminal and start the simulator by
``` sh
python humanoid-mujoco-sim/simulator.py
```

- Put the `policy.onnx` in the folder `limx_ws/humanoid-rl-deploy-python/controllers/HU_D03_03/walking_controller/policy/default`. Then, open another Bash terminal and run the algorithm by
``` sh
python humanoid-rl-deploy-python/main.py
```

- Finally, use the virtual joystick to control the robot. Open another Bash terminal and run
``` sh
./humanoid-mujoco-sim/robot-joystick/robot-joystick
```

- Available commands are as follows:

|**Button**	| **Mode**	| **Description** |
|:-|:-|:-|
|L1+Y|	Switch to Stand Mode|	If the robot cannot stand, click "Reset (Backspace)" in the MuJoCo interface to reset it.
|L1+B|	Switch to Greeting Mode	|  |
|R2+X| Switch to Walking Mode | **This mode will use your model!!!** |
|L1+A| Switch to Damping Mode| |
|L1+X| Exit| |


### Sim2Real
- Make sure your model runs perfectly in the `sim2sim`!!!
- Start the robot and complete the calibration.
- Ensure your computer is connected to the robot's external network port. Set your computer's IP address to `10.192.1.200` and verify connectivity with the Shell command ping `10.192.1.2`.
- Press `L1 + START` on the remote control to switch to developer mode (This mode setting persists after rebooting. To exit developer mode, press `L1 + L2 + START`).
- Stop the internal controller by
``` sh
ssh limx@10.192.1.2
ps -ef | grep "ability"
sudo kill -9 PID
```
- Start the control algorithm by
``` sh
python humanoid-rl-deploy-python/main.py 10.192.1.2
```
- Press `L1+Y` to make the robot stand up.
- Press `R1+X` to activate the walking controller.


## Acknowledgments
This project is built upon several excellent projects:
- [IsaacLab](https://github.com/isaac-sim/IsaacLab)
- [Mujoco](https://github.com/google-deepmind/mujoco.git)
- [rsl_rl](https://github.com/leggedrobotics/rsl_rl)