# Game Mechanics & Systems Design

## 1. Core Philosophy: A Needs-Driven Simulation

The world of TickTock Tribe is a persistent simulation driven by the actions of autonomous agents called **Villagers**. Every action a Villager takes is motivated by a hierarchical set of needs. This "Needs-Driven AI" forms the core of the simulation, creating emergent behavior and a dynamic, evolving world.

The simulation progresses in discrete time steps called **Ticks**. All world updates and agent decisions occur synchronously within these Ticks.

## 2. The World & Time

### 2.1. Terrain

The world is a 2D grid composed of various terrain tiles. The primary terrain types include:
*   **PLAIN**: Buildable land, can be converted to Farmland.
*   **FOREST**: Source of `Wood` and `Seeds`. Can be cleared to Plain.
*   **WATER**: Essential for farming. Cannot be modified.
*   **FARMLAND**: A multi-stage tile for food production.

### 2.2. Time
-   Time is measured in **Ticks**.
-   A configurable number of Ticks constitute a **Day** (`time.ticks_per_day`).
-   A configurable number of Days constitute a **Year** (`time.ticks_per_year`).
-   Time progression is universal and affects all systems, including aging, crop growth, and resource consumption.

## 3. Villagers: The Agents of Change

Villagers are the central agents of the simulation. Each Villager is a unique entity with a distinct set of attributes.

### 3.1. Attributes
-   **Gender**: `male` or `female`.
-   **Age**: Measured in Ticks (`age_in_ticks`) and translated to Years for game logic (e.g., reproduction, work capability).
-   **Hunger**: A value from `100` (full) to `0` (starvation). Decreases over time.
-   **Status**: The Villager's current state (`idle`, `working`, `eating`, etc.).
-   **Task**: The specific long-running action the Villager is performing.

### 3.2. Lifespan & Aging
-   Villagers age linearly with the passage of Ticks.
-   **Work Capability**:
    -   Children (`< 6` years) and extreme elders (`> 80` years) do not work.
    -   Youths (`6-18`) and elders (`65-80`) work at reduced efficiency.
-   **Death**:
    -   **Starvation**: Hunger reaching `0`.
    -   **Old Age**: The probability of death increases significantly after age `65`, peaking around age `80`.

### 3.3. Needs Hierarchy
A Villager's primary goal is to satisfy their needs, prioritized as follows:
1.  **Urgent Needs (Survival)**: Avoid starvation. If `hunger` drops below a critical threshold (`ai.hunger_threshold_urgent`), finding food becomes the absolute priority, overriding all other tasks.
2.  **Important Needs (Security)**: Secure shelter. A Villager without a home will prioritize finding or building one.
3.  **Opportunistic Needs (Growth & Legacy)**: When survival and security are met:
    -   **Reproduction**: If conditions are met, Villagers will attempt to reproduce.
    -   **Development**: Gather resources (`Wood`, `Seeds`) to improve the settlement and build a surplus.

### 3.4. Reproduction
-   **Conditions**:
    -   Two Villagers of opposite gender, sharing the same House.
    -   Both must be within the reproductive age range (`18-45` years).
    -   Their age gap must not exceed a configured limit (`reproduction_age_gap`).
    -   The House must have an available slot (`capacity`).
    -   The House's shared `storage` must contain a sufficient food reserve (`ai.food_reserve_for_reproduction`).
-   **Process**: Reproduction is a task that consumes a significant amount of food and initiates a cooldown period (`reproduction_cooldown_ticks`) for the parents.

## 4. Resources & Storage

### 4.1. Resource Types
-   **Food**: Essential for survival and reproduction. Produced by Farmland.
-   **Wood**: Primary building material. Harvested from Forests.
-   **Seeds**: Used for planting new trees. Harvested from Forests.

### 4.2. The Unified Storage System (Houses)
-   The `houses` table serves as the universal model for all inventories.
-   **Real House**: A physical structure on the map with `x, y` coordinates, a capacity of `4`, and shared storage for all residents.
-   **Virtual House**: An abstract concept for a Villager's personal inventory when they are not part of a Real House. It has `NULL` coordinates and a capacity of `1`.
-   Every Villager is **always** associated with a House (real or virtual), ensuring they always have access to a personal or shared inventory.

## 5. Structures

### 5.1. Houses
-   **Function**: Provide shelter and shared storage. A prerequisite for reproduction.
-   **Lifecycle**:
    -   **Build**: A task consuming `Wood` (`house_build_cost_wood`).
    -   **Decay**: Have an `integrity` value that can decrease over time.
    -   **Collapse**: If `integrity` reaches `0`, the structure is destroyed. All residents are rendered "homeless" (reverting to a new Virtual House) and the stored resources are divided among them.

### 5.2. Farmland
-   **Lifecycle**:
    1.  **Build**: A Villager converts a `PLAIN` tile next to `WATER` into `FARM_UNTILLED`.
    2.  **Growth**: The tile automatically transitions to `FARM_GROWING`. Over a set duration (`world.farmland_growth_ticks`), it matures.
    3.  **Mature**: Becomes `FARM_MATURE`, ready for harvest.
    4.  **Harvest**: A Villager performs a task to gather `Food` from the tile, which reverts to `FARM_UNTILLED`.

## 6. AI & Task System

### 6.1. Decision Making
-   The AI logic runs for every `idle` Villager at each decision point.
-   It evaluates actions based on the Needs Hierarchy. For example, the utility of "Harvest Food" is extremely high for a hungry Villager but low for a well-fed one.
-   The Villager commits to the highest-utility action available.

### 6.2. Task Execution
-   Most actions are not instantaneous and are modeled as **Tasks** (e.g., `build_house`, `chop_tree`).
-   When a Villager starts a task, their `status` becomes `working`, and their `current_task` and `task_progress` are set.
-   Each Tick, the `WorldUpdater` increments the `task_progress` for all working Villagers.
-   When `task_progress` reaches the required duration for the task, the task is completed, its effects are applied (e.g., resources are gained, terrain is changed), and the Villager's `status` returns to `idle`.
-   Urgent needs can interrupt and override current tasks.