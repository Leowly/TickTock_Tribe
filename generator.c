// generator.c

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// 地块类型定义
#define PLAIN 0
#define FOREST 1
#define WATER 2

// 参数结构体
typedef struct
{
    double seed_prob;
    int iterations;
    int birth_threshold;
} ForestParams;

typedef struct
{
    double density;
    double turn_prob;
    double stop_prob;
} WaterParams;

// 检查坐标是否在边界内
int is_within_bounds(int x, int y, int width, int height)
{
    return x >= 0 && x < width && y >= 0 && y < height;
}

// 导出宏定义（兼容 Windows / Linux / macOS）
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

#ifdef __cplusplus
extern "C"
{
#endif

    // 主地图生成函数
    EXPORT int *generate_map(int width, int height, ForestParams f_params, WaterParams w_params)
    {
        srand((unsigned int)time(NULL));

        int *grid = (int *)malloc(width * height * sizeof(int));
        if (!grid)
            return NULL;

        for (int i = 0; i < width * height; ++i)
            grid[i] = PLAIN;

        // 森林初始种子
        for (int y = 0; y < height; ++y)
        {
            for (int x = 0; x < width; ++x)
            {
                if ((double)rand() / RAND_MAX < f_params.seed_prob)
                {
                    grid[y * width + x] = FOREST;
                }
            }
        }

        // 森林扩张迭代
        int *new_grid = (int *)malloc(width * height * sizeof(int));
        for (int i = 0; i < f_params.iterations; ++i)
        {
            memcpy(new_grid, grid, width * height * sizeof(int));
            for (int y = 0; y < height; ++y)
            {
                for (int x = 0; x < width; ++x)
                {
                    int count = 0;
                    for (int dy = -1; dy <= 1; ++dy)
                    {
                        for (int dx = -1; dx <= 1; ++dx)
                        {
                            if (dx == 0 && dy == 0)
                                continue;
                            int nx = x + dx, ny = y + dy;
                            if (is_within_bounds(nx, ny, width, height) &&
                                grid[ny * width + nx] == FOREST)
                            {
                                count++;
                            }
                        }
                    }
                    if (grid[y * width + x] == PLAIN && count >= f_params.birth_threshold)
                    {
                        new_grid[y * width + x] = FOREST;
                    }
                }
            }
            memcpy(grid, new_grid, width * height * sizeof(int));
        }
        free(new_grid);

        // 水源密度计算
        int num_sources = (int)(width * height * w_params.density);
        if (num_sources < 1)
            num_sources = 1;

        int directions[4][2] = {{0, 1}, {0, -1}, {1, 0}, {-1, 0}};

        for (int i = 0; i < num_sources; ++i)
        {
            int sx = rand() % width;
            int sy = rand() % height;
            if (grid[sy * width + sx] == WATER)
                continue;
            grid[sy * width + sx] = WATER;

            // 打乱方向数组
            for (int k = 3; k > 0; --k)
            {
                int j = rand() % (k + 1);
                int tmpx = directions[k][0], tmpy = directions[k][1];
                directions[k][0] = directions[j][0];
                directions[k][1] = directions[j][1];
                directions[j][0] = tmpx;
                directions[j][1] = tmpy;
            }

            // 生成两条水流分支
            for (int b = 0; b < 2; ++b)
            {
                int cx = sx, cy = sy;
                int dx = directions[b][0], dy = directions[b][1];
                while (1)
                {
                    if ((double)rand() / RAND_MAX < w_params.stop_prob)
                        break;

                    double rv = (double)rand() / RAND_MAX;
                    if (rv < w_params.turn_prob)
                    {
                        int tmp = dx;
                        dx = -dy;
                        dy = tmp; // 左转
                    }
                    else if (rv < 2 * w_params.turn_prob)
                    {
                        int tmp = dx;
                        dx = dy;
                        dy = -tmp; // 右转
                    }

                    int nx = cx + dx, ny = cy + dy;
                    if (!is_within_bounds(nx, ny, width, height))
                        break;

                    cx = nx;
                    cy = ny;
                    grid[cy * width + cx] = WATER;
                }
            }
        }

        return grid;
    }

    // 内存释放函数
    EXPORT void free_map_memory(int *map_ptr)
    {
        if (map_ptr)
        {
            free(map_ptr);
        }
    }

#ifdef __cplusplus
}
#endif
