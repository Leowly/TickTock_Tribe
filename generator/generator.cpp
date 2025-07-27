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
#include <iostream> // For debugging print, can be removed

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

// --- 新增：用于返回打包数据的结构 ---
struct PackedMapResult {
    uint8_t* data;
    int size;
};
// --- 新增结束 ---

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
        for (int y = 1; y < height - 1; y++) // Keep smoothing away from edges
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

// --- 新增：位打包辅助函数 ---
// 将一个包含 tile 值 (0-7, fits in 3 bits) 的一维数组打包成字节数组
uint8_t* pack_bits(const uint8_t* flat_tiles, int num_tiles, int* out_packed_size) {
    // Calculate the required size for the packed data
    *out_packed_size = (num_tiles * 3 + 7) / 8; // Equivalent to ceil((num_tiles * 3) / 8.0)
    uint8_t* packed_data = new uint8_t[*out_packed_size](); // Initialize to 0

    for (int i = 0; i < num_tiles; ++i) {
        uint8_t value = flat_tiles[i] & 0x07; // Ensure only the lowest 3 bits are used
        int bit_index = i * 3;
        int byte_index = bit_index / 8;
        int bit_offset = bit_index % 8;

        // Place the 3-bit value into the packed data
        if (bit_offset <= 5) {
            // Value fits entirely within the current byte
            packed_data[byte_index] |= (value << (8 - 3 - bit_offset));
        } else {
            // Value spans two bytes
            int bits_in_first_byte = 8 - bit_offset;
            int bits_in_second_byte = 3 - bits_in_first_byte;
            packed_data[byte_index] |= (value >> bits_in_second_byte);
            // Check bounds before writing to the next byte
            if (byte_index + 1 < *out_packed_size) {
                packed_data[byte_index + 1] |= (value << (8 - bits_in_second_byte)) & 0xFF;
            }
        }
    }
    return packed_data;
}
// --- 新增结束 ---


extern "C"
{

    EXPORT void free_map(uint8_t *map);
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
                            // --- 修复：确保邻居在边界内 ---
                            if (is_within_bounds(nx, ny, width, height) && grid[ny * width + nx] == 1)
                            {
                                count++;
                            }
                        }
                    }
                    // --- 修复：确保当前格子在边界内 ---
                    if (is_within_bounds(x, y, width, height) && grid[y * width + x] == 0 && count >= f_params.birth_threshold)
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
            // --- 修复：确保源头在边界内 ---
            if (!is_within_bounds(sx, sy, width, height) || grid[sy * width + sx] == 2)
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

                        // --- 关键修复：检查下一个点是否在边界内 ---
                        if (!is_within_bounds(nx, ny, width, height))
                            continue; // 如果下一个点超出边界，则跳过这个方向

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
                    // --- 关键修复：再次检查要设置的点是否在边界内 ---
                    if (!is_within_bounds(cx, cy, width, height)) {
                        break; // 如果计算出的新点超出边界，则停止流线
                    }
                    grid[cy * width + cx] = 2; // 设置为水
                }
            }
        }

        delete[] height_field;
        return grid;
    }

    // --- 新增：生成并打包地图的函数 ---
    EXPORT PackedMapResult generate_map_packed(int width, int height, ForestParams f_params, WaterParams w_params) {
        // 1. 生成标准的 uint8_t 地图
        uint8_t* standard_grid = generate_map(width, height, f_params, w_params);
        if (!standard_grid) {
             PackedMapResult result = {nullptr, 0};
             return result; // Handle generation failure
        }

        // 2. 计算总格子数
        int num_tiles = width * height;

        // 3. 调用打包函数
        int packed_size = 0;
        uint8_t* packed_data = pack_bits(standard_grid, num_tiles, &packed_size);

        // 4. 释放原始的未打包地图内存
        free_map(standard_grid);

        // 5. 返回打包后的数据和大小
        PackedMapResult result;
        result.data = packed_data;
        result.size = packed_size;
        return result;
    }
    // --- 新增结束 ---


    EXPORT void free_map(uint8_t *map)
    {
        // This function can now free both standard grids and packed grids
        // as long as the caller treats the packed data as uint8_t*.
        // The PackedMapResult's size field is for informational purposes
        // or if a different freeing strategy was needed (it's not here).
        delete[] map;
    }

} // extern "C"