# TickTock Tribe

A backend simulation engine for a large-scale, grid-based world, driven by a time-based "Tick" system. The project focuses on efficient map generation, storage, and state updates.

> **Note**: This repository contains the core simulation engine. It provides APIs to create, manage, and simulate large grid worlds, visualized through a web browser. Full gameplay features like villagers, resources, and building are not yet implemented in this version. However, the core architecture (Tick-driven loop, C++ acceleration, 3-bit compression storage) is in place, laying a solid foundation for future expansion.

## 🌍 What is this project?

This engine allows you to:

1.  **Generate** large (1000x1000 by default) random world maps featuring plains, forests, and rivers.
2.  **View** these maps with pan and zoom capabilities.
3.  **Start a simulation**: A background process updates the map state at a fixed interval (a "Tick"). The update logic is currently a placeholder, but the framework is fully functional.
4.  **Store efficiently**: Map data is stored using a 3-bit compression technique, significantly reducing database size.

This project is an excellent case study for learning Tick-based system design, web frontend-backend interaction, hybrid C++/Python programming, and SQLite performance optimization.

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+**
- **uv** (Recommended Python package and project manager)
- **G++** (For compiling the C++ map generation library)

### Installation & Execution

1.  **Clone or download this repository.**
2.  **Install dependencies and run the application**:
    ```bash
    uv run -- python app.py
    ```
3.  **Access**: Open `http://localhost:16151` in your browser.

## ⚙️ Tech Stack

- **Backend**: Python (Flask)
- **Frontend**: HTML5, Vanilla JavaScript (with Canvas API), Tailwind CSS (via CDN)
- **Database**: SQLite
- **Performance-Critical Code**: C++ (compiled to a shared library, called from Python via ctypes)
- **Configuration**: TOML
- **Dependency Management**: `uv`

## 🎮 Game Mechanics

For a detailed explanation of the core gameplay, system design, and numerical parameters, please refer to the documents below:

- **[Game Mechanics Design (English)](./Game_Mechanics.md)**
- **[游戏机制设计 (Chinese Version)](./Game_Mechanics.zh.md)**

## 📜 License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](https://github.com/git/git-scm.com/blob/main/MIT-LICENSE.txt) file for details.
