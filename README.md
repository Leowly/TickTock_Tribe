# 🌍 TickTock_Tribe

一个基于 Tick 驱动的模拟生存游戏：观察虚拟部落在二维格子世界中如何采集资源、建造房屋、繁衍生息，并与不断变化的环境互动。

---

## 🎯 项目目标

- ✅ **可玩性**：设计紧凑、资源循环、发展演化
- ✅ **可扩展性**：模块化架构，支持规则与行为扩展
- ✅ **性能优化**：部分核心逻辑使用 C++ 语言加速

---

## 🧩 技术栈

| 类别         | 技术                     |
|--------------|--------------------------|
| 后端         | Python + Flask           |
| 配置管理     | TOML 配置文件            |
| 前端         | HTML5 + CSS + JS + Canvas |
| 数据存储     | SQLite                   |
| 性能模块     | C++ 语言地图生成器         |
| 包管理       | [uv](https://github.com/astral-sh/uv)（推荐代替 pip） |

---

## 🚀 快速开始

> ✅ 本项目使用 [`uv`](https://github.com/astral-sh/uv) 进行依赖管理。

### 1. 克隆项目

```bash
git clone https://github.com/leowly/TickTock_Tribe.git
cd TickTock_Tribe
