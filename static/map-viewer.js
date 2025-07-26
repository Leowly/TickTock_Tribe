// static/map-viewer.js

class MapViewer {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.canvas.style.cursor = 'grab';
    
    // --- 更新 TERRAIN_COLORS 以支持新的耕地状态 ---
    // 0: PLAIN, 1: FOREST, 2: WATER, 3: FARM_UNTILLED, 4: FARM_TILLED
    this.TERRAIN_COLORS = { 
      '0': '#F0E68C', // 浅绿黄色 (Khaki) - 平原
      '1': '#228B22', // 森林绿 (ForestGreen) - 森林
      '2': '#1E90FF', // 道奇蓝 (DodgerBlue) - 水源
      '3': '#9ACD32', // 黄绿色 (YellowGreen) - 未耕种/未成熟耕地
      '4': '#32CD32'  // 酸橙绿 (LimeGreen) - 已耕种/已成熟耕地
    };
    
    this.BASE_TILE_SIZE = 16;
    this.dpr = window.devicePixelRatio || 1;
    // 状态
    this.camera = { 
      x: 0, 
      y: 0, 
      zoom: 1, 
      minZoom: 0.1, 
      maxZoom: 5, 
      maxVisiblePixels: null  
    };
    this.interaction = {
      isDragging: false, isPinching: false, lastX: 0, lastY: 0,
      initialPinchDistance: 0, lastZoom: 1
    };
    this.worldData = null;
    this.mapId = null; // 存储当前地图ID
    this.dataRefreshIntervalId = null; // 存储数据刷新定时器ID

    // 绑定事件处理器
    this.setupEventListeners();
    window.addEventListener('resize', () => this.handleResize());
  }

  constrainCamera() {
    if (!this.worldData) return;
    const currentTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
    const worldPixelWidth = this.worldData.width * currentTileSize;
    const worldPixelHeight = this.worldData.height * currentTileSize;
    const viewWidth = window.innerWidth;
    const viewHeight = window.innerHeight;
    if (worldPixelWidth < viewWidth) {
      this.camera.x = (worldPixelWidth - viewWidth) / 2;
    } else {
      this.camera.x = Math.max(0, Math.min(this.camera.x, worldPixelWidth - viewWidth));
    }
    if (worldPixelHeight < viewHeight) {
      this.camera.y = (worldPixelHeight - viewHeight) / 2;
    } else {
      this.camera.y = Math.max(0, Math.min(this.camera.y, worldPixelHeight - viewHeight));
    }
  }

  draw() {
    if (!this.worldData || !this.worldData.grid || !this.worldData.grid.length) return;
    this.ctx.fillStyle = '#000000';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.save();
    this.ctx.scale(this.dpr, this.dpr);
    const currentTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
    const startX = Math.floor(this.camera.x / currentTileSize);
    const startY = Math.floor(this.camera.y / currentTileSize);
    const endX = Math.ceil((this.camera.x + window.innerWidth) / currentTileSize);
    const endY = Math.ceil((this.camera.y + window.innerHeight) / currentTileSize);
    for (let y = startY; y < endY; y++) {
      for (let x = startX; x < endX; x++) {
        if (x < 0 || y < 0 || x >= this.worldData.width || y >= this.worldData.height) continue;
        const tileType = this.worldData.grid[y]?.[x];
        if (tileType === undefined) continue;
        // --- 使用更新后的 TERRAIN_COLORS ---
        const color = this.TERRAIN_COLORS[tileType] || '#FF00FF'; // 默认洋红色表示未知类型
        const screenX = x * currentTileSize - this.camera.x;
        const screenY = y * currentTileSize - this.camera.y;
        if (!isFinite(screenX) || !isFinite(screenY)) continue;
        this.ctx.fillStyle = color;
        this.ctx.fillRect(screenX, screenY, currentTileSize + 1, currentTileSize + 1);
      }
    }
    this.ctx.restore();
  }

  setupEventListeners() {
    // 鼠标事件
    this.canvas.addEventListener('mousedown', (e) => {
      this.interaction.isDragging = true;
      this.interaction.lastX = e.clientX;
      this.interaction.lastY = e.clientY;
      this.canvas.style.cursor = 'grabbing';
    });
    this.canvas.addEventListener('mousemove', (e) => {
      if (!this.interaction.isDragging) return;
      const dx = e.clientX - this.interaction.lastX;
      const dy = e.clientY - this.interaction.lastY;
      this.camera.x -= dx;
      this.camera.y -= dy;
      this.constrainCamera();
      this.interaction.lastX = e.clientX;
      this.interaction.lastY = e.clientY;
    });
    this.canvas.addEventListener('mouseup', () => {
      this.interaction.isDragging = false;
      this.canvas.style.cursor = 'grab';
    });
    this.canvas.addEventListener('mouseleave', () => {
      this.interaction.isDragging = false;
      this.canvas.style.cursor = 'grab';
    });
    // 滚轮事件 - 添加 passive 标记
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomAmount = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      this.zoomAtPoint(e.clientX, e.clientY, zoomAmount);
      this.constrainCamera();
    }, { passive: false });
    // 触摸事件
    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.interaction.isDragging = true;
        this.interaction.lastX = e.touches[0].clientX;
        this.interaction.lastY = e.touches[0].clientY;
      } else if (e.touches.length === 2) {
        this.interaction.isDragging = false;
        this.interaction.isPinching = true;
        this.interaction.initialPinchDistance = this.getDistance(e.touches[0], e.touches[1]);
        this.interaction.lastZoom = this.camera.zoom;
      }
    }, { passive: true });
    this.canvas.addEventListener('touchmove', (e) => {
      if (this.interaction.isDragging && e.touches.length === 1) {
        const dx = e.touches[0].clientX - this.interaction.lastX;
        const dy = e.touches[0].clientY - this.interaction.lastY;
        this.camera.x -= dx;
        this.camera.y -= dy;
        this.interaction.lastX = e.touches[0].clientX;
        this.interaction.lastY = e.touches[0].clientY;
      } else if (this.interaction.isPinching && e.touches.length === 2) {
        const p1 = e.touches[0];
        const p2 = e.touches[1];
        const currentPinchDistance = this.getDistance(p1, p2);
        const zoomFactor = currentPinchDistance / this.interaction.initialPinchDistance;
        const newZoom = Math.max(
          this.camera.minZoom,
          Math.min(this.camera.maxZoom, this.interaction.lastZoom * zoomFactor)
        );
        // 计算两指中心点
        const centerX = (p1.clientX + p2.clientX) / 2;
        const centerY = (p1.clientY + p2.clientY) / 2;
        // 应用“缩放 + 平移”逻辑（复用 zoomAtPoint）
        const zoomChange = newZoom / this.camera.zoom;
        this.zoomAtPoint(centerX, centerY, zoomChange);
      }
      this.constrainCamera();
    }, { passive: true });
  }

  getDistance(p1, p2) {
    return Math.sqrt(
      Math.pow(p2.clientX - p1.clientX, 2) + 
      Math.pow(p2.clientY - p1.clientY, 2)
    );
  }

  handleResize() {
    this.setupCanvas();
    this.updateMinZoom();
  }

  setupCanvas() {
    this.canvas.width = Math.round(window.innerWidth * this.dpr);
    this.canvas.height = Math.round(window.innerHeight * this.dpr);
    this.canvas.style.width = `${window.innerWidth}px`;
    this.canvas.style.height = `${window.innerHeight}px`;
  }

  updateMinZoom() {
    // 计算屏幕面积
    const screenArea = window.innerWidth * window.innerHeight;
    // 计算单个瓦片的最小面积
    const minTileArea = screenArea / this.camera.maxVisiblePixels;
    // 计算瓦片的最小边长
    const minTileSize = Math.sqrt(minTileArea);
    // 设置最小缩放比例
    this.camera.minZoom = Math.max(0.1, minTileSize / this.BASE_TILE_SIZE);
    // 确保当前缩放不小于最小缩放
    if (this.camera.zoom < this.camera.minZoom) {
      this.camera.zoom = this.camera.minZoom;
      this.constrainCamera();
    }
  }

  zoomAtPoint(mouseX, mouseY, zoomChange) {
    const worldX = (mouseX + this.camera.x) / this.camera.zoom;
    const worldY = (mouseY + this.camera.y) / this.camera.zoom;
    this.camera.zoom = Math.max(this.camera.minZoom, Math.min(this.camera.maxZoom, this.camera.zoom * zoomChange));
    const newZoom = this.camera.zoom;
    this.camera.x = worldX * newZoom - mouseX;
    this.camera.y = worldY * newZoom - mouseY;
  }

  startGameLoop() {
    const loop = () => {
      this.draw();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  // --- 新增方法：启动模拟 ---
  async startSimulation() {
      if (this.mapId === null) {
          console.error("Cannot start simulation: mapId is not set.");
          return;
      }
      try {
          const response = await fetch(`/api/maps/${this.mapId}/start_simulation`, {
              method: 'POST'
          });
          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
          }
          const data = await response.json();
          console.log("Simulation started:", data.message);
      } catch (error) {
          console.error("Error starting simulation:", error);
          // 可以在这里添加用户提示
          alert(`启动模拟失败: ${error.message}`);
      }
  }

  // --- 新增方法：停止模拟 ---
  async stopSimulation() {
      if (this.mapId === null) {
          // 如果 mapId 未设置，说明可能未初始化完成就离开了，可以不处理或记录日志
          console.log("stopSimulation called, but mapId is not set.");
          return;
      }
      try {
          // 发送停止模拟的请求
          const response = await fetch(`/api/maps/${this.mapId}/stop_simulation`, {
              method: 'POST'
          });
          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
          }
          const data = await response.json();
          console.log("Simulation stopped:", data.message);
      } catch (error) {
          // 停止失败通常不是严重错误，可以只记录日志
          console.warn("Error stopping simulation (might be expected on page close):", error);
          // 不弹窗警告用户，因为页面可能正在卸载
      }
  }

  // --- 新增方法：加载地图数据 ---
  async loadMapData() {
      if (this.mapId === null) {
          throw new Error("Map ID is not set");
      }
      // console.log(`Refreshing data for map ${this.mapId}`); // 调试用
      const response = await fetch(`/api/maps/${this.mapId}`);
      if (!response.ok) {
          if (response.status === 404) {
              throw new Error("地图未找到 (404)");
          }
          throw new Error(`Failed to load map: ${response.status} ${response.statusText}`);
      }
      const data = await response.json();
      if (this.worldData) {
          this.worldData.grid = data.tiles;
      } else {
          this.worldData = {
              width: data.width,
              height: data.height,
              grid: data.tiles
          };
      }
      if (!this.worldData.grid || !this.worldData.grid.length) {
          throw new Error('Invalid map data structure received from server');
      }
  }

  // --- 修改 initialize 方法 ---
  async initialize() {
    this.setupCanvas();
    try {
      // --- 获取 mapId ---
      const pathParts = window.location.pathname.split('/');
      this.mapId = parseInt(pathParts[pathParts.length - 1], 10);
      if (isNaN(this.mapId)) {
        throw new Error('Invalid map ID in URL');
      }

      // 先加载配置
      const configRes = await fetch('/api/config');
      const config = await configRes.json();
      this.camera.maxVisiblePixels = config.view.max_visible_pixels;
      this.updateMinZoom();

      // --- 启动模拟 ---
      await this.startSimulation();

      // --- 加载初始地图数据 ---
      await this.loadMapData();

      // --- 设置定期数据刷新 ---
      // 每 1000 毫秒 (1秒) 刷新一次数据
      this.dataRefreshIntervalId = setInterval(async () => {
          try {
              await this.loadMapData();
              // draw 循环会自动使用更新后的数据
          } catch (err) {
              console.error("Error refreshing map data:", err);
              // 可以添加更健壮的错误处理
          }
      }, 1000); 

      // --- 相机和循环设置 ---
      this.updateMinZoom();
      const initialTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
      this.camera.x = (this.worldData.width * initialTileSize - window.innerWidth) / 2;
      this.camera.y = (this.worldData.height * initialTileSize - window.innerHeight) / 2;
      this.constrainCamera();
      this.startGameLoop();

    } catch (error) {
      console.error("初始化失败:", error);
      // 停止任何可能已启动的刷新循环
      if (this.dataRefreshIntervalId) {
          clearInterval(this.dataRefreshIntervalId);
      }
      // 显示错误信息给用户
      document.body.innerHTML = `<h1>加载地图失败</h1><p style="color:red;">${error.message}</p>`;
    }
  }

  // --- 新增方法：清理资源 ---
  destroy() {
      // 停止数据刷新循环
      if (this.dataRefreshIntervalId) {
          clearInterval(this.dataRefreshIntervalId);
          this.dataRefreshIntervalId = null;
          console.log("Data refresh interval cleared.");
      }
      // 停止模拟
      this.stopSimulation(); // 这会发送异步请求，可能在页面完全卸载前完成
  }
}