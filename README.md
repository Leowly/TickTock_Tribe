[English](./docs/README.en.md)

# TickTock Tribe

一个基于时间刻（Tick）驱动的大型网格世界模拟后端，专注于高效的地图生成、存储和更新。

> **注意**: 此仓库是项目的核心模拟引擎部分。它提供 API 用于创建、管理和模拟大型网格世界，并通过浏览器进行可视化。完整的可玩性“部落”功能（如村民、资源、建造等）尚未在此版本中实现，但核心架构（如 Tick 驱动、C++ 加速、3-bit 压缩存储）已就绪，为未来扩展奠定了基础。

## 🌍 这个项目是干什么的？

它能让你：

1.  **生成** 大型（默认 1000x1000）的随机世界地图，包含平原、森林和河流。
2.  **查看** 这些地图，支持平移和缩放。
3.  **启动模拟**：后台会按固定时间间隔（Tick）更新地图状态（当前更新逻辑为无变化，但框架已搭建）。
4.  **高效存储**：使用 3-bit 压缩技术存储地图数据，显著减少数据库体积。

非常适合学习基于 Tick 的系统设计、Web 前后端交互、C++ 与 Python 混合编程以及 SQLite 性能优化。

## 🚀 快速开始

### 环境要求

- **Python 3.8 或更高版本**
- **uv** (推荐的 Python 包和项目管理器)
- **G++** (用于编译 C++ 地图生成库)

### 安装与运行

1.  **克隆或下载此仓库**
2.  **安装依赖并启动**:
    ```bash
    uv run -- python app.py
    ```
3.  **访问**: 在浏览器中打开 `http://localhost:16151`。

## ⚙️ 技术栈

- **后端**: Python (Flask)
- **前端**: HTML5, JavaScript (原生 + Canvas), Tailwind CSS (通过 CDN)
- **数据库**: SQLite
- **性能关键部分**: C++ (编译为共享库，由 Python 通过 ctypes 调用)
- **配置**: TOML
- **依赖管理**: `uv`

## 📁 项目结构

- `app.py`: Flask 应用主入口。
- `config.toml`: 项目配置文件（地图尺寸、地形参数等）。
- `core/`: 核心 Python 模块（配置、数据库、Tick 管理器、世界更新器）。
- `generator/`: C++ 地图生成器 (`generator.cpp`) 及其 Python 封装 (`c_world_generator.py`)。
- `templates/`: Flask HTML 模板。
- `static/`: 静态资源（JavaScript, CSS）。
- `database/`: SQLite 数据库存放目录。
- `docs/`: 包含项目文档（READMEs, 游戏机制设计等）。 <!-- 已经更新 -->

## 🎮 游戏机制 (Game Mechanics) <!-- 图标已更换 -->

关于游戏核心玩法、系统设计和数值的详细说明，请参阅以下文档：

- **[游戏机制设计 (中文版)](./docs/游戏机制设计.md)**
- **[Game Mechanics Design (English)](./docs/Game_Mechanics.md)** 

## 📜 许可证

本项目采用 **GNU General Public License v3.0**。详情请见 [LICENSE](LICENSE) 文件。
