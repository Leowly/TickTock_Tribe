#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

#include <cstdlib>
#include <ctime>
#include <cstring>
#include <random>
#include <algorithm>
#include <cstdint>

using namespace std;

// 参数结构体
struct ForestParams
{
    double seed_prob;
    int iterations;
    int birth_threshold;
};

struct WaterParams
{
    double density;
    double turn_prob;
    double stop_prob;
    double height_influence;
};

static bool is_within_bounds(int x, int y, int width, int height)
{
    return x >= 0 && x < width && y >= 0 && y < height;
}

static double *generate_height_field(int width, int height)
{
    double *height_arr = new double[width * height];
    random_device rd;
    mt19937 gen(rd());
    uniform_real_distribution<> dis(0.0, 1.0);

    for (int i = 0; i < width * height; i++)
    {
        height_arr[i] = dis(gen);
    }

    double *temp = new double[width * height];

    for (int iter = 0; iter < 3; iter++)
    {
        for (int y = 1; y < height - 1; y++)
        {
            for (int x = 1; x < width - 1; x++)
            {
                temp[y * width + x] = (height_arr[(y - 1) * width + x] +
                                       height_arr[(y + 1) * width + x] +
                                       height_arr[y * width + (x - 1)] +
                                       height_arr[y * width + (x + 1)]) *
                                      0.25;
            }
        }
        memcpy(height_arr, temp, width * height * sizeof(double));
    }

    delete[] temp;
    return height_arr;
}

extern "C"
{

    EXPORT uint8_t *generate_map(int width, int height, ForestParams f_params, WaterParams w_params)
    {
        srand((unsigned int)time(nullptr));
        uint8_t *grid = new uint8_t[width * height];
        memset(grid, 0, width * height); // 0 = PLAIN

        // 森林初始种子
        for (int y = 0; y < height; y++)
        {
            for (int x = 0; x < width; x++)
            {
                double p = (double)rand() / RAND_MAX;
                if (p < f_params.seed_prob)
                {
                    grid[y * width + x] = 1; // FOREST
                }
            }
        }

        // 森林扩张迭代
        uint8_t *new_grid = new uint8_t[width * height];
        for (int iter = 0; iter < f_params.iterations; iter++)
        {
            memcpy(new_grid, grid, width * height);
            for (int y = 0; y < height; y++)
            {
                for (int x = 0; x < width; x++)
                {
                    int count = 0;
                    for (int dy = -1; dy <= 1; dy++)
                    {
                        for (int dx = -1; dx <= 1; dx++)
                        {
                            if (dx == 0 && dy == 0)
                                continue;
                            int nx = x + dx;
                            int ny = y + dy;
                            if (is_within_bounds(nx, ny, width, height) && grid[ny * width + nx] == 1)
                            {
                                count++;
                            }
                        }
                    }
                    if (grid[y * width + x] == 0 && count >= f_params.birth_threshold)
                    {
                        new_grid[y * width + x] = 1;
                    }
                }
            }
            memcpy(grid, new_grid, width * height);
        }
        delete[] new_grid;

        // 生成高度场
        double *height_field = generate_height_field(width, height);

        // 水源密度计算
        int num_sources = (int)(width * height * w_params.density);
        if (num_sources < 1)
            num_sources = 1;

        int directions[4][2] = {{0, 1}, {0, -1}, {1, 0}, {-1, 0}};
        random_device rd2;
        mt19937 gen(rd2());
        uniform_real_distribution<> dist01(0.0, 1.0);

        for (int i = 0; i < num_sources; i++)
        {
            int sx = rand() % width;
            int sy = rand() % height;
            if (grid[sy * width + sx] == 2)
                continue;
            grid[sy * width + sx] = 2; // WATER

            // 打乱方向
            for (int k = 3; k > 0; k--)
            {
                int j = rand() % (k + 1);
                swap(directions[k][0], directions[j][0]);
                swap(directions[k][1], directions[j][1]);
            }

            for (int b = 0; b < 2; b++)
            {
                int cx = sx;
                int cy = sy;
                int dx = directions[b][0];
                int dy = directions[b][1];

                while (true)
                {
                    if (dist01(gen) < w_params.stop_prob)
                        break;

                    double best_score = -1.0;
                    int best_dx = dx, best_dy = dy;

                    int possible_dirs[3][2] = {
                        {dx, dy},
                        {-dy, dx},
                        {dy, -dx}};

                    bool found = false;

                    for (int dir = 0; dir < 3; dir++)
                    {
                        int test_dx = possible_dirs[dir][0];
                        int test_dy = possible_dirs[dir][1];
                        int nx = cx + test_dx;
                        int ny = cy + test_dy;

                        if (!is_within_bounds(nx, ny, width, height))
                            continue;

                        double current_height = height_field[cy * width + cx];
                        double next_height = height_field[ny * width + nx];
                        double height_diff = current_height - next_height;
                        double score = 1.0 + height_diff * w_params.height_influence;
                        score += (dist01(gen) - 0.5) * 0.2;

                        if (score > best_score)
                        {
                            best_score = score;
                            best_dx = test_dx;
                            best_dy = test_dy;
                            found = true;
                        }
                    }

                    if (!found)
                        break;

                    dx = best_dx;
                    dy = best_dy;
                    cx += dx;
                    cy += dy;
                    grid[cy * width + cx] = 2;
                }
            }
        }

        delete[] height_field;
        return grid;
    }

    EXPORT void free_map(uint8_t *map)
    {
        delete[] map;
    }

} // extern "C"
