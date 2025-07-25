#include <stdio.h>
#include <stdlib.h>
#include <string.h> // 需要包含 string.h 用于 memcpy
#include <time.h>

// 地块类型定义
#define PLAIN 0
#define FOREST 1
#define WATER 2

// 参数结构体保持不变
typedef struct {
    double seed_prob;
    int iterations;
    int birth_threshold;
} ForestParams;

typedef struct {
    double density;
    double turn_prob;
    double stop_prob;
} WaterParams;

// 辅助函数保持不变
int is_within_bounds(int x, int y, int width, int height) {
    return x >= 0 && x < width && y >= 0 && y < height;
}

#ifdef __cplusplus
extern "C" {
#endif

// 主生成函数
int* generate_map(int width, int height, ForestParams f_params, WaterParams w_params) {
    srand(time(NULL));

    int* grid = (int*)malloc(width * height * sizeof(int));
    if (grid == NULL) return NULL;

    for (int i = 0; i < width * height; ++i) grid[i] = PLAIN;

    // --- 森林生成部分 (无改动) ---
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            if ((double)rand() / RAND_MAX < f_params.seed_prob) {
                grid[y * width + x] = FOREST;
            }
        }
    }
    int* new_grid = (int*)malloc(width * height * sizeof(int));
    for (int i = 0; i < f_params.iterations; ++i) {
        memcpy(new_grid, grid, width * height * sizeof(int));
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                int forest_neighbors = 0;
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        if (dx == 0 && dy == 0) continue;
                        int nx = x + dx, ny = y + dy;
                        if (is_within_bounds(nx, ny, width, height) && grid[ny * width + nx] == FOREST) {
                            forest_neighbors++;
                        }
                    }
                }
                if (grid[y * width + x] == PLAIN && forest_neighbors >= f_params.birth_threshold) {
                    new_grid[y * width + x] = FOREST;
                }
            }
        }
        memcpy(grid, new_grid, width * height * sizeof(int));
    }
    free(new_grid);

    // --- 水系生成部分 (核心修正) ---
    int num_sources = (int)(width * height * w_params.density);
    if (num_sources < 1) num_sources = 1;

    // 1. 定义一个包含四个基本方向的数组
    int directions[4][2] = {{0, 1}, {0, -1}, {1, 0}, {-1, 0}};

    for (int i = 0; i < num_sources; ++i) {
        int sx = rand() % width;
        int sy = rand() % height;
        if (grid[sy * width + sx] == WATER) continue;
        grid[sy * width + sx] = WATER;

        // 2. 随机打乱方向数组 (Fisher-Yates shuffle)，以确保两个分支方向不同
        for (int k = 3; k > 0; --k) {
            int j = rand() % (k + 1);
            int temp_dx = directions[k][0]; int temp_dy = directions[k][1];
            directions[k][0] = directions[j][0]; directions[k][1] = directions[j][1];
            directions[j][0] = temp_dx; directions[j][1] = temp_dy;
        }

        // 从打乱后的数组中为两个分支选择初始方向
        for (int b = 0; b < 2; ++b) {
            int cx = sx, cy = sy;
            // 3. 从预定义的、正确的方向数组中获取初始方向
            int dx = directions[b][0];
            int dy = directions[b][1];

            while (1) {
                if ((double)rand() / RAND_MAX < w_params.stop_prob) break;
                
                double rand_val = (double)rand() / RAND_MAX;
                if (rand_val < w_params.turn_prob) { // 左转
                    int temp = dx; dx = -dy; dy = temp;
                } else if (rand_val < w_params.turn_prob * 2) { // 右转
                    int temp = dx; dx = dy; dy = -temp;
                }

                int nx = cx + dx;
                int ny = cy + dy;
                if (!is_within_bounds(nx, ny, width, height)) break;

                cx = nx; cy = ny;
                grid[cy * width + cx] = WATER;
            }
        }
    }

    return grid;
}

void free_map_memory(int* map_ptr) {
    if (map_ptr != NULL) {
        free(map_ptr);
    }
}

#ifdef __cplusplus
}
#endif