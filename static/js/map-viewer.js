class MapViewer {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.canvas.style.cursor = 'grab';

    // 常量定义
    this.TERRAIN_COLORS = { '0': '#F0E68C', '1': '#228B22', '2': '#1E90FF' };
    this.BASE_TILE_SIZE = 16;
    this.dpr = window.devicePixelRatio || 1;

    // 状态
    this.camera = { x: 0, y: 0, zoom: 1, minZoom: 0.1, maxZoom: 5, maxVisiblePixels: 500000 };
    this.interaction = {
      isDragging: false, isPinching: false, lastX: 0, lastY: 0,
      initialPinchDistance: 0, lastZoom: 1
    };
    this.worldData = null;

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
        const color = this.TERRAIN_COLORS[tileType] || '#FF00FF';
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
        const currentPinchDistance = this.getDistance(e.touches[0], e.touches[1]);
        const zoomFactor = currentPinchDistance / this.interaction.initialPinchDistance;
        const newZoom = Math.max(
          this.camera.minZoom,
          Math.min(this.camera.maxZoom, this.interaction.lastZoom * zoomFactor)
        );
        this.camera.zoom = newZoom;
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
    const canvasLogicalArea = window.innerWidth * window.innerHeight;
    const tileScreenArea = canvasLogicalArea / this.camera.maxVisiblePixels;
    const minTileSize = Math.sqrt(tileScreenArea);
    this.camera.minZoom = minTileSize / this.BASE_TILE_SIZE;
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

  async initialize() {
    this.setupCanvas();
    
    // 从URL获取地图ID
    const mapId = window.location.pathname.split('/').pop();
    try {
      const response = await fetch(`/api/maps/${mapId}`);
      if (!response.ok) throw new Error(`Failed to load map: ${response.status}`);
      
      const data = await response.json();
      this.worldData = {
        width: data.width,
        height: data.height,
        grid: data.tiles
      };
      
      if (!this.worldData.grid || !this.worldData.grid.length) {
        throw new Error('Invalid map data structure');
      }

      this.updateMinZoom();
      const initialTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
      this.camera.x = (this.worldData.width * initialTileSize - window.innerWidth) / 2;
      this.camera.y = (this.worldData.height * initialTileSize - window.innerHeight) / 2;
      
      this.constrainCamera();
      this.startGameLoop();
    } catch (error) {
      console.error("初始化失败:", error);
      document.body.innerHTML = `<h1>加载地图失败</h1><p style="color:red;">${error.message}</p>`;
    }
  }
}
