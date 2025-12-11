# 中文 | [English](README.md)

# humanoid-rl-isaaclab

<img src="https://img.shields.io/badge/IsaacLab-2.0.0-green"> <img src="https://img.shields.io/badge/IsaacSim-4.5.0-silver"> <img src="https://img.shields.io/badge/PyTorch-2.5.1-orange"> <img src="https://img.shields.io/badge/License-Apache 2.0-yellow">

## 概述
本项目提供了逐际动力 **Oli** 人形机器人的强化学习环境与训练脚本。

<div align="center">

| <div align="center"> Isaac Lab </div> | <div align="center"> Mujoco </div> | <div align="center"> Physical </div> |
|--- | --- | --- |
| <img src="./source/limx_rl_forge/docs/isaaclab.gif" style="width: 200px; height: 200px;"> | <img src="./source/limx_rl_forge/docs/mujoco.gif" style="width: 200px; height: 200px;"> | <img src="./source/limx_rl_forge/docs/physical.gif" style="width: 200px; height: 200px;"> |
</div>

## 快速开始

### 安装
- 创建 **Python 3.10** 虚拟环境:
``` sh
conda create -n limx python=3.10
conda activate limx
```

- 根据您系统上的 CUDA 版本安装 ​​ **PyTorch 2.5.1**:
``` sh
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

- 安装 ​​**IsaacSim 4.5.0**​​ 软件包:
``` sh
pip install isaacsim[all,extscache]==4.5.0 --extra-index-url https://pypi.nvidia.com
```

- 从 [IsaacLab官网](https://github.com/isaac-sim/IsaacLab/releases) 下载**2.0.0**版本并安装:
``` sh
./isaaclab.sh -i none
```

- 下载项目代码:
``` sh
git clone https://github.com/limxdynamics/humanoid-rl-isaaclab.git
pip install -r requirements.txt
```

- 下载机器人资产文件：
``` sh
git clone https://github.com/limxdynamics/humanoid-description.git
```

- 验证安装并列出所有可用训练环境:
``` sh
python scripts/list_envs.py
```
Then you will see the following output:
<img src="./source/limx_rl_forge/docs/list_envs.png">

### 训练

- 训练模型
``` sh
python scripts/rsl_rl/train.py --headless --task LimX-Oli-31dof-Velocity
```

- 模型推理
``` sh
python scripts/rsl_rl/play.py --task LimX-Oli-31dof-Velocity
```


## 模型部署

请参照以下工程代码进行 `sim2sim` 以及 `sim2real` 部署:
- [使用Python部署](https://github.com/limxdynamics/humanoid-rl-deploy-python)
- [使用C++部署](https://github.com/limxdynamics/humanoid-rl-deploy-cpp)