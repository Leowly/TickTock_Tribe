const { createApp, ref, reactive, onMounted } = Vue;

createApp({
  setup() {
    const mapName = ref('');
    const world = reactive({ width: 50, height: 50 });
    const forest = reactive({ seed_prob: 0.1, iterations: 3, birth_threshold: 4 });
    const water = reactive({ density: 0.02, turn_prob: 0.3, stop_prob: 0.1, height_influence: 2.0 });

    const canvas = ref(null);
    let ctx = null;
    const TERRAIN_COLORS = { '0': '#F0E68C', '1': '#228B22', '2': '#1E90FF' };
    const BASE_TILE_SIZE = 16;
    let dpr = window.devicePixelRatio || 1;

    let camera = reactive({ x: 0, y: 0, zoom: 1, minZoom: 0.1, maxZoom: 5, maxVisiblePixels: 500000 });
    let interaction = reactive({ isDragging: false, lastX: 0, lastY: 0 });
    let worldData = reactive({ width: 0, height: 0, grid: [] });

    function constrainCamera() {
      const currentTileSize = BASE_TILE_SIZE * camera.zoom;
      const worldPixelWidth = worldData.width * currentTileSize;
      const worldPixelHeight = worldData.height * currentTileSize;
      const viewWidth = window.innerWidth;
      const viewHeight = window.innerHeight;
      if (worldPixelWidth < viewWidth) {
          camera.x = (worldPixelWidth - viewWidth) / 2;
      } else {
          camera.x = Math.max(0, Math.min(camera.x, worldPixelWidth - viewWidth));
      }
      if (worldPixelHeight < viewHeight) {
          camera.y = (worldPixelHeight - viewHeight) / 2;
      } else {
          camera.y = Math.max(0, Math.min(camera.y, worldPixelHeight - viewHeight));
      }
    }

    function draw() {
      if (!worldData.grid.length) return;
      ctx.clearRect(0, 0, canvas.value.width, canvas.value.height);
      ctx.save();
      ctx.scale(dpr, dpr);
      const currentTileSize = BASE_TILE_SIZE * camera.zoom;
      const startX = Math.floor(camera.x / currentTileSize);
      const startY = Math.floor(camera.y / currentTileSize);
      const endX = Math.ceil((camera.x + window.innerWidth) / currentTileSize);
      const endY = Math.ceil((camera.y + window.innerHeight) / currentTileSize);

      for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
          if (x < 0 || y < 0 || x >= worldData.width || y >= worldData.height) continue;
          const tileType = worldData.grid[y][x];
          const color = TERRAIN_COLORS[tileType] || '#FF00FF';
          const screenX = x * currentTileSize - camera.x;
          const screenY = y * currentTileSize - camera.y;
          ctx.fillStyle = color;
          ctx.fillRect(screenX, screenY, currentTileSize + 1, currentTileSize + 1);
        }
      }
      ctx.restore();
    }

    function gameLoop() {
      draw();
      requestAnimationFrame(gameLoop);
    }

    function setupCanvas() {
      dpr = window.devicePixelRatio || 1;
      canvas.value.width = Math.round(window.innerWidth * dpr);
      canvas.value.height = Math.round(window.innerHeight * dpr);
      canvas.value.style.width = window.innerWidth + 'px';
      canvas.value.style.height = window.innerHeight + 'px';
      ctx = canvas.value.getContext('2d');
    }

    async function createMap() {
      if (world.width > 2000 || world.height > 2000) {
        alert('宽度和高度最大不能超过2000');
        return;
      }
      const params = {
        world: { ...world },
        forest: { ...forest },
        water: { ...water },
        name: mapName.value || '默认地图'
      };
      try {
        const res = await fetch('/api/generate_map', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        });
        const data = await res.json();
        if (data.success) {
          worldData.width = data.tiles[0].length;
          worldData.height = data.tiles.length;
          worldData.grid = data.tiles;
          camera.x = 0;
          camera.y = 0;
          camera.zoom = 1;
          constrainCamera();
        } else {
          alert('生成地图失败');
        }
      } catch (err) {
        alert('请求失败: ' + err.message);
      }
    }

    async function loadMap() {
      alert('暂未实现加载地图');
    }

    onMounted(() => {
      setupCanvas();
      gameLoop();
      window.addEventListener('resize', () => {
        setupCanvas();
        constrainCamera();
      });
    });

    return {
      mapName,
      world,
      forest,
      water,
      createMap,
      loadMap,
      canvas
    };
  }
}).mount('#app');
