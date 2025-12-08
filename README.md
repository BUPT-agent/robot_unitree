# 🤖 Human-Centric Agent System for Unitree Robots

## `robot_unitree`

<p align="center">
  <img src="https://img.shields.io/badge/Language-Python-blue" alt="Python Badge">
  <img src="https://img.shields.io/badge/Architecture-Client%2FServer-green" alt="Client/Server Badge">
  <img src="https://img.shields.io/badge/Framework-Intelligent%20Agent-red" alt="Agent Framework Badge">
  <img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License Badge">
</p>

---

## ✨ 项目简介 (Introduction)

本项目是 **我们团队** 开发的一个 **全栈 Python 智能体系统**，旨在为 **Unitree** 系列机器人（如 G1）提供一个 **高层级的、基于指令的控制与交互接口**。

它采用经典的 **客户端-服务器（Client-Server）** 架构，将机器人的 **感知、决策与执行** 逻辑抽象为一系列智能体模块（如 `Brain`、`Ears`），使得用户能够通过简洁的指令或交互界面，远程驱动复杂的机器人任务。

**核心目标：** 建立一个灵活、可扩展的智能体控制平台，简化 Unitree 机器人的高级功能开发和人机交互。

---

## 🚀 核心功能 (Key Features)

- **客户端/服务器通信架构**：机器人端运行 **Server**，负责接收指令并执行运动控制；用户端运行 **Client**，负责发送指令和接收状态信息。  
- **模块化智能体设计**：
  - `brain.py` (大脑)：核心决策模块，负责解析高层指令、规划任务步骤，并调度低层运动。  
  - `ears.py` (耳朵)：感知模块，负责处理输入数据，可能包括语音识别、环境感知或指令解析。  
- **高层控制接口**：提供抽象接口，允许研究人员专注智能体算法开发，而无需直接处理复杂的 Unitree 底层运动学和动力学。  
- **语音交互支持**：包含 `wav.py`，用于处理音频数据（语音识别或语音合成），支持更自然的人机交互方式。  
- **Web 接口**：项目包含 `templates/` 文件夹和 HTML 模板，提供基于 Web 的可视化控制面板。

---

## 📦 文件结构解析 (File Structure)

| 文件/文件夹 | 描述 |
| :--- | :--- |
| `main.py` | 项目的入口文件，负责初始化并启动整个智能体系统。 |
| `robot_server.py` | 运行在机器人（或中继计算机）上的服务器端逻辑，接收客户端指令，调用 `brain.py` 执行动作。 |
| `robot_client.py` | 运行在用户计算机上的客户端逻辑，负责发送控制指令和与用户界面交互。 |
| `brain.py` | 智能体的**决策核心**，处理任务逻辑和运动规划。 |
| `ears.py` | 智能体的**感知输入模块**，负责处理外部信号（如用户输入、传感器数据）。 |
| `wav.py` | 用于处理 `.wav` 格式音频文件，可能与语音识别或指令输入相关。 |
| `tool.py` | 包含系统通用的辅助函数、工具类或常量定义。 |
| `config.py` | 存储系统配置参数，如网络端口、机器人型号、控制参数等。 |
| `requirements.txt` | Python 依赖库列表。 |
| `templates/` | 可能包含 Web 界面所需的 HTML 模板文件。 |

---

## 🛠️ 安装指南 (Installation Guide)

### 环境依赖

- **操作系统：** Windows 11。  
- **Python 版本：** 推荐 Python 3.10。

### 步骤一：克隆仓库

```bash
git clone https://github.com/BUPT-agent/robot_unitree.git
cd robot_unitree
```

### 步骤二：安装依赖

所有必需的 Python 依赖项都列在 `requirements.txt` 中：

```bash
pip install -r requirements.txt
```

> 注意：可能还需要安装特定于 Unitree SDK 的依赖，请参考 Unitree 官方文档与 SDK 指南。

---

## ⚙️ 使用方法 (Usage)

### 1. 启动服务器（机器人端）

在连接到 Unitree 机器人的计算机或机器人本体上，启动服务器：

```bash
python robot_server.py eth0
```

服务器启动后将监听来自客户端的连接和控制指令。

### 2. 启动客户端（控制端）

在用户的控制计算机上，启动客户端：

```bash
python main.py
```


### 3. 配置修改

在运行之前，请务必检查并修改 `config.py` 文件中的网络地址、端口和机器人特定参数，以确保客户端和服务器能够正确通信。

---

## 贡献（Contributing）

欢迎提交 issue 和 pull request。请遵循仓库的贡献指南与代码风格约定。

---
