// static/map-viewer.js

class MapViewer {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.canvas.style.cursor = 'crosshair';

    this.TERRAIN_COLORS = { 
      '0': '#F0E68C', // 平原
      '1': '#228B22', // 森林
      '2': '#1E90FF', // 水源
      '3': '#9ACD32', // 未成熟耕地
      '4': '#32CD32'  // 已成熟耕地
    };
    this.VILLAGER_COLORS = {
      'male': '#FF6B6B',   // 男性
      'female': '#4ECDC4', // 女性
      'child': '#FFE66D',  // 儿童
      'elderly': '#95A5A6' // 老年
    };
    this.HOUSE_COLOR = '#8B4513';
    this.BASE_TILE_SIZE = 16;
    this.dpr = window.devicePixelRatio || 1;

    this.camera = { x: 0, y: 0, zoom: 1, minZoom: 0.1, maxZoom: 5, maxVisiblePixels: null };
    this.interaction = { isDragging: false, isPinching: false, lastX: 0, lastY: 0, initialPinchDistance: 0, lastZoom: 1 };
    this.worldData = null;
    this.villagers = [];
    this.houses = [];
    this.mapId = null;
    this.dataRefreshIntervalId = null;
    this.mapRefreshIntervalId = null;

    this.tooltip = { active: false, type: null, id: null, data: null, screenX: 0, screenY: 0 };
    this.hoverDebounceTimer = null;

    // 速度控制相关属性
    this.speed = 1; // 当前速度倍率
    this.speedTiers = [1, 5, 10, 50, 100, 500, 1000]; // 预设档位
    this.maxFrontendRefreshRate = 10; // 前端最大请求频率 (Hz)
    this.minSpeed = 1;
    this.maxSpeed = 1000;

    this.setupEventListeners();
    window.addEventListener('resize', () => this.handleResize());
  }

  constrainCamera() {
    if (!this.worldData) return;

    const currentTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
    const worldPixelWidth = this.worldData.width * currentTileSize;
    const worldPixelHeight = this.worldData.height * currentTileSize;
    const viewWidth = window.innerWidth * this.dpr;
    const viewHeight = window.innerHeight * this.dpr;

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

  unpack3BitBytes(packedBytes, width, height) {
    const totalTiles = width * height;
    const flatGrid = new Uint8Array(totalTiles);
    const packedData = packedBytes;

    for (let i = 0; i < totalTiles; i++) {
        const bitIndex = i * 3;
        const byteIndex = Math.floor(bitIndex / 8);
        const bitOffset = bitIndex % 8;
        let value = 0;
        if (bitOffset <= 5) {
            const mask = 0b111;
            value = (packedData[byteIndex] >> (5 - bitOffset)) & mask;
        } else {
            const bitsInFirstByte = 8 - bitOffset;
            const bitsInSecondByte = 3 - bitsInFirstByte;
            const part1 = (packedData[byteIndex] & ((1 << bitsInFirstByte) - 1)) << bitsInSecondByte;
            let part2 = 0;
            if (byteIndex + 1 < packedData.length) {
                part2 = (packedData[byteIndex + 1] >> (8 - bitsInSecondByte));
            }
            value = part1 | part2;
        }
        flatGrid[i] = value;
    }
    return flatGrid;
  }

  draw() {
    if (!this.worldData || !this.worldData.flatGrid || this.worldData.flatGrid.length === 0) return;

    this.ctx.fillStyle = '#000000';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.save();
    this.ctx.scale(this.dpr, this.dpr);

    const currentTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
    const startX = Math.floor(this.camera.x / currentTileSize);
    const startY = Math.floor(this.camera.y / currentTileSize);
    const endX = Math.ceil((this.camera.x + window.innerWidth * this.dpr) / currentTileSize);
    const endY = Math.ceil((this.camera.y + window.innerHeight * this.dpr) / currentTileSize);

    for (let y = startY; y < endY; y++) {
      for (let x = startX; x < endX; x++) {
        if (x < 0 || y < 0 || x >= this.worldData.width || y >= this.worldData.height) continue;
        const index = y * this.worldData.width + x;
        const tileType = this.worldData.flatGrid[index];
        if (tileType === undefined) continue;
        const color = this.TERRAIN_COLORS[tileType] || '#FF00FF';
        const screenX = x * currentTileSize - this.camera.x;
        const screenY = y * currentTileSize - this.camera.y;
        if (!isFinite(screenX) || !isFinite(screenY)) continue;
        this.ctx.fillStyle = color;
        this.ctx.fillRect(screenX, screenY, currentTileSize + 1, currentTileSize + 1);
      }
    }

    this.drawHouses(currentTileSize);
    this.drawVillagers(currentTileSize);
    this.drawTooltip();

    this.ctx.restore();
  }
  
  drawTooltip() {
      if (!this.tooltip.active || !this.tooltip.data) return;
      this.ctx.font = '14px Arial';
      this.ctx.textBaseline = 'top';
      const lines = [];
      if (this.tooltip.type === 'villager') {
          const v = this.tooltip.data;
          lines.push(`村民: ${v.name} (ID: ${v.id})`);
          if (v.house_id) { lines.push(`  房屋ID: ${v.house_id}`); }
          lines.push(`  食物: ${v.food}`);
          lines.push(`  木材: ${v.wood}`);
          lines.push(`  种子: ${v.seeds}`);
      } else if (this.tooltip.type === 'house') {
          const h = this.tooltip.data;
          lines.push(`房屋 (ID: ${h.id})`);
          lines.push(`  居住: ${h.current_occupants.length} / ${h.capacity}`);
          lines.push(`  食物库存: ${h.food_storage}`);
          lines.push(`  木材库存: ${h.wood_storage}`);
          lines.push(`  种子库存: ${h.seeds_storage}`);
      }
      const padding = 10;
      let maxWidth = 0;
      for (const line of lines) { maxWidth = Math.max(maxWidth, this.ctx.measureText(line).width); }
      const lineHeight = 18;
      const boxWidth = maxWidth + padding * 2;
      const boxHeight = lines.length * lineHeight + padding * 2;
      let boxX = this.tooltip.screenX + 15;
      let boxY = this.tooltip.screenY + 15;
      if (boxX + boxWidth > window.innerWidth) { boxX = this.tooltip.screenX - boxWidth - 15; }
      if (boxY + boxHeight > window.innerHeight) { boxY = this.tooltip.screenY - boxHeight - 15; }
      this.ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
      this.ctx.strokeStyle = '#FFFFFF';
      this.ctx.lineWidth = 1;
      this.ctx.beginPath();
      this.ctx.roundRect(boxX, boxY, boxWidth, boxHeight, 5);
      this.ctx.fill();
      this.ctx.stroke();
      this.ctx.fillStyle = '#FFFFFF';
      for (let i = 0; i < lines.length; i++) {
          this.ctx.fillText(lines[i], boxX + padding, boxY + padding + i * lineHeight);
      }
  }

  drawHouses(currentTileSize) {
    if (!this.houses || this.houses.length === 0) return;
    this.ctx.fillStyle = this.HOUSE_COLOR;
    this.ctx.strokeStyle = '#000000';
    this.ctx.lineWidth = 1;
    for (const house of this.houses) {
      if (!house.is_standing) continue;
      const screenX = house.x * currentTileSize - this.camera.x;
      const screenY = house.y * currentTileSize - this.camera.y;
      if (screenX + currentTileSize < 0 || screenX > window.innerWidth * this.dpr ||
          screenY + currentTileSize < 0 || screenY > window.innerHeight * this.dpr) continue;
      const houseSize = currentTileSize * 1.2;
      this.ctx.fillRect(screenX - houseSize/4, screenY - houseSize/4, houseSize, houseSize);
      this.ctx.strokeRect(screenX - houseSize/4, screenY - houseSize/4, houseSize, houseSize);
      if (currentTileSize > 20) {
        this.ctx.fillStyle = '#FFFFFF';
        this.ctx.font = `${Math.max(8, currentTileSize/4)}px Arial`;
        this.ctx.textAlign = 'center';
        this.ctx.fillText(`${house.occupants}/${house.capacity}`, screenX + houseSize/4, screenY + houseSize/4);
      }
    }
  }

  drawVillagers(currentTileSize) {
    if (!this.villagers || this.villagers.length === 0) return;
    for (const villager of this.villagers) {
      const screenX = villager.x * currentTileSize - this.camera.x;
      const screenY = villager.y * currentTileSize - this.camera.y;
      if (screenX + currentTileSize < 0 || screenX > window.innerWidth * this.dpr ||
          screenY + currentTileSize < 0 || screenY > window.innerHeight * this.dpr) continue;
      let color = this.VILLAGER_COLORS[villager.gender];
      if (villager.age < 6) { color = this.VILLAGER_COLORS.child; }
      else if (villager.age >= 65) { color = this.VILLAGER_COLORS.elderly; }
      const villagerSize = currentTileSize * 0.6;
      this.ctx.fillStyle = color;
      this.ctx.beginPath();
      this.ctx.arc(screenX + currentTileSize/2, screenY + currentTileSize/2, villagerSize/2, 0, 2 * Math.PI);
      this.ctx.fill();
      this.ctx.strokeStyle = '#000000';
      this.ctx.lineWidth = 1;
      this.ctx.stroke();
    }
  }

  setupEventListeners() {
    this.canvas.addEventListener('mousedown', (e) => {
      this.interaction.isDragging = true;
      this.interaction.lastX = e.clientX;
      this.interaction.lastY = e.clientY;
      this.canvas.style.cursor = 'grabbing';
      this.hideTooltip();
    });
    this.canvas.addEventListener('mousemove', (e) => {
      if (this.interaction.isDragging) {
        const dx = e.clientX - this.interaction.lastX;
        const dy = e.clientY - this.interaction.lastY;
        this.camera.x -= dx * this.dpr;
        this.camera.y -= dy * this.dpr;
        this.constrainCamera();
        this.interaction.lastX = e.clientX;
        this.interaction.lastY = e.clientY;
      } else {
        this.handleMouseMoveForTooltip(e);
      }
    });
    this.canvas.addEventListener('mouseup', () => {
      this.interaction.isDragging = false;
      this.canvas.style.cursor = 'crosshair';
    });
    this.canvas.addEventListener('mouseleave', () => {
      this.interaction.isDragging = false;
      this.canvas.style.cursor = 'crosshair';
      this.hideTooltip();
    });
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomAmount = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      this.zoomAtPoint(e.clientX, e.clientY, zoomAmount);
      this.constrainCamera();
      this.hideTooltip();
    }, { passive: false });
    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.interaction.isDragging = true;
        this.interaction.lastX = e.touches[0].clientX;
        this.interaction.lastY = e.touches[0].clientY;
        this.hideTooltip();
      } else if (e.touches.length === 2) {
        this.interaction.isDragging = false;
        this.interaction.isPinching = true;
        this.interaction.initialPinchDistance = this.getDistance(e.touches[0], e.touches[1]);
        this.interaction.lastZoom = this.camera.zoom;
        this.hideTooltip();
      }
    }, { passive: true });
    this.canvas.addEventListener('touchmove', (e) => {
      e.preventDefault();
      if (this.interaction.isDragging && e.touches.length === 1) {
        const dx = e.touches[0].clientX - this.interaction.lastX;
        const dy = e.touches[0].clientY - this.interaction.lastY;
        this.camera.x -= dx * this.dpr;
        this.camera.y -= dy * this.dpr;
        this.interaction.lastX = e.touches[0].clientX;
        this.interaction.lastY = e.touches[0].clientY;
      } else if (this.interaction.isPinching && e.touches.length === 2) {
        const p1 = e.touches[0];
        const p2 = e.touches[1];
        const currentPinchDistance = this.getDistance(p1, p2);
        const zoomFactor = currentPinchDistance / this.interaction.initialPinchDistance;
        const newZoom = Math.max(this.camera.minZoom, Math.min(this.camera.maxZoom, this.interaction.lastZoom * zoomFactor));
        const centerX = (p1.clientX + p2.clientX) / 2;
        const centerY = (p1.clientY + p2.clientY) / 2;
        const zoomChange = newZoom / this.camera.zoom;
        this.zoomAtPoint(centerX, centerY, zoomChange);
      }
      this.constrainCamera();
    }, { passive: false });
    this.canvas.addEventListener('touchend', (e) => {
        this.interaction.isDragging = false;
        this.interaction.isPinching = false;
    });
  }
  
  handleMouseMoveForTooltip(e) {
      const worldX = (e.clientX * this.dpr + this.camera.x) / this.camera.zoom;
      const worldY = (e.clientY * this.dpr + this.camera.y) / this.camera.zoom;
      const gridX = Math.floor(worldX / this.BASE_TILE_SIZE);
      const gridY = Math.floor(worldY / this.BASE_TILE_SIZE);
      let foundEntity = null;
      for (const villager of this.villagers) {
          if (villager.x === gridX && villager.y === gridY) {
              foundEntity = { type: 'villager', id: villager.id };
              break;
          }
      }
      if (!foundEntity) {
          for (const house of this.houses) {
              if (house.x === gridX && house.y === gridY) {
                  foundEntity = { type: 'house', id: house.id };
                  break;
              }
          }
      }
      this.tooltip.screenX = e.clientX;
      this.tooltip.screenY = e.clientY;
      if (foundEntity) {
          if (this.tooltip.id === foundEntity.id && this.tooltip.type === foundEntity.type) { return; }
          clearTimeout(this.hoverDebounceTimer);
          this.hoverDebounceTimer = setTimeout(() => {
              this.fetchTooltipData(foundEntity.type, foundEntity.id);
          }, 200);
      } else {
          this.hideTooltip();
      }
  }

  async fetchTooltipData(type, id) {
      try {
          const response = await fetch(`/api/${type}s/${id}`);
          if (!response.ok) { throw new Error(`Failed to fetch ${type} data (ID: ${id})`); }
          const data = await response.json();
          this.tooltip.active = true;
          this.tooltip.type = type;
          this.tooltip.id = id;
          this.tooltip.data = data;
      } catch (error) {
          console.error(error);
          this.hideTooltip();
      }
  }

  hideTooltip() {
      clearTimeout(this.hoverDebounceTimer);
      if (this.tooltip.active) {
        this.tooltip.active = false;
        this.tooltip.id = null;
        this.tooltip.type = null;
        this.tooltip.data = null;
      }
  }

  getDistance(p1, p2) {
    return Math.sqrt(Math.pow(p2.clientX - p1.clientX, 2) + Math.pow(p2.clientY - p1.clientY, 2));
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
    if (!this.camera.maxVisiblePixels) return;
    const screenArea = window.innerWidth * window.innerHeight;
    const minTileArea = screenArea / this.camera.maxVisiblePixels;
    const minTileSize = Math.sqrt(minTileArea);
    this.camera.minZoom = Math.max(0.1, minTileSize / this.BASE_TILE_SIZE);
    if (this.camera.zoom < this.camera.minZoom) {
      this.camera.zoom = this.camera.minZoom;
      this.constrainCamera();
    }
  }

  zoomAtPoint(mouseX, mouseY, zoomChange) {
    const worldX = (mouseX * this.dpr + this.camera.x) / this.camera.zoom;
    const worldY = (mouseY * this.dpr + this.camera.y) / this.camera.zoom;
    this.camera.zoom = Math.max(this.camera.minZoom, Math.min(this.camera.maxZoom, this.camera.zoom * zoomChange));
    const newZoom = this.camera.zoom;
    this.camera.x = worldX * newZoom - mouseX * this.dpr;
    this.camera.y = worldY * newZoom - mouseY * this.dpr;
  }

  startGameLoop() {
    const loop = () => {
      this.draw();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  async startSimulation() {
      if (this.mapId === null) { console.error("mapId is not set."); return; }
      try {
          const response = await fetch(`/api/maps/${this.mapId}/start_simulation`, { method: 'POST' });
          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
          }
          console.log("Simulation started:", (await response.json()).message);
      } catch (error) {
          console.error("Error starting simulation:", error);
          alert(`启动模拟失败: ${error.message}`);
      }
  }

  async stopSimulation() {
      if (this.mapId === null) { console.log("stopSimulation called, but mapId is not set."); return; }
      try {
          const response = await fetch(`/api/maps/${this.mapId}/stop_simulation`, { method: 'POST' });
          if (!response.ok) {
              const errorData = await response.json().catch(() => ({}));
              throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
          }
          console.log("Simulation stopped:", (await response.json()).message);
      } catch (error) {
          console.warn("Error stopping simulation:", error);
      }
  }

  async loadMapData() {
    if (this.mapId === null) { throw new Error("Map ID is not set"); }
    const response = await fetch(`/api/maps/${this.mapId}`);
    if (!response.ok) {
        if (response.status === 404) { throw new Error("地图未找到 (404)"); }
        let errorMsg = `Failed to load map: ${response.status} ${response.statusText}`;
        try { errorMsg = (await response.json()).error || errorMsg; } catch (e) {}
        throw new Error(errorMsg);
    }
    const contentType = response.headers.get('Content-Type');
    if (contentType && contentType.includes('application/json')) {
        const data = await response.json();
        if (data.error) { throw new Error(data.error); }
        if (data.tiles_base64) {
            try {
                const binaryString = atob(data.tiles_base64);
                const len = binaryString.length;
                const packedBytes = new Uint8Array(len);
                for (let i = 0; i < len; i++) { packedBytes[i] = binaryString.charCodeAt(i); }
                const flatGrid = this.unpack3BitBytes(packedBytes, data.width, data.height);
                if (this.worldData) {
                    this.worldData.flatGrid = flatGrid; 
                    this.worldData.width = data.width;
                    this.worldData.height = data.height;
                } else {
                    this.worldData = { width: data.width, height: data.height, flatGrid: flatGrid };
                }
            } catch (e) {
                 console.error("Error decoding or unpacking map data:", e);
                 throw new Error("Failed to process map data from server.");
            }
        } else { throw new Error('Invalid map data structure: missing tiles_base64'); }
        if (!this.worldData || !this.worldData.flatGrid || this.worldData.flatGrid.length === 0) {
            throw new Error('Invalid or empty unpacked map data structure');
        }
    } else { throw new Error(`Unexpected Content-Type: ${contentType}`); }
  }

  async loadVillagerData() {
    if (this.mapId === null) { throw new Error("Map ID is not set"); }
    try {
      const response = await fetch(`/api/maps/${this.mapId}/villagers`);
      if (!response.ok) { console.warn("Failed to load villager data:", response.status); return; }
      const data = await response.json();
      this.villagers = data.villagers || [];
      this.houses = data.houses || [];
    } catch (error) { console.warn("Error loading villager data:", error); }
  }

  setupSpeedControls() {
    this.speedDownBtn = document.getElementById('speed-down');
    this.speedUpBtn = document.getElementById('speed-up');
    this.speedInput = document.getElementById('speed-input');

    this.speedDownBtn.addEventListener('click', () => {
        let currentIndex = -1;
        for (let i = this.speedTiers.length - 1; i >= 0; i--) {
            if (this.speedTiers[i] < this.speed) {
                currentIndex = i;
                break;
            }
        }
        const newSpeed = (currentIndex !== -1) ? this.speedTiers[currentIndex] : this.minSpeed;
        this.updateSpeed(newSpeed);
    });

    this.speedUpBtn.addEventListener('click', () => {
        let currentIndex = -1;
        for (let i = 0; i < this.speedTiers.length; i++) {
            if (this.speedTiers[i] > this.speed) {
                currentIndex = i;
                break;
            }
        }
        const newSpeed = (currentIndex !== -1) ? this.speedTiers[currentIndex] : this.maxSpeed;
        this.updateSpeed(newSpeed);
    });

    this.speedInput.addEventListener('change', (e) => {
        let newSpeed = parseInt(e.target.value, 10);
        if (isNaN(newSpeed)) { newSpeed = this.minSpeed; }
        newSpeed = Math.max(this.minSpeed, Math.min(this.maxSpeed, newSpeed));
        this.updateSpeed(newSpeed);
    });
    
    this.speedInput.addEventListener('input', (e) => {
        if (parseInt(e.target.value, 10) > this.maxSpeed) {
            e.target.value = this.maxSpeed;
        }
    });

    this.speedInput.addEventListener('wheel', (e) => e.preventDefault());
    
    this.updateSpeedUI();
  }

  updateSpeed(newSpeed) {
    if (newSpeed === this.speed) return;
    this.speed = newSpeed;
    this.updateSpeedUI();
    this.setBackendSimulationSpeed(this.speed);
    this.adjustFrontendRefreshRate();
  }
  
  updateSpeedUI() {
      this.speedInput.value = this.speed;
      this.speedDownBtn.disabled = this.speed <= this.minSpeed;
      this.speedUpBtn.disabled = this.speed >= this.maxSpeed;
  }

  async setBackendSimulationSpeed(speed) {
    console.log(`Setting backend simulation speed to: ${speed}x`);
    try {
        await fetch('/api/simulation_speed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ speed: speed })
        });
    } catch (error) {
        console.error("Error setting backend simulation speed:", error);
    }
  }

  adjustFrontendRefreshRate() {
    // 停止旧的定时器
    if (this.dataRefreshIntervalId) { clearInterval(this.dataRefreshIntervalId); }
    if (this.mapRefreshIntervalId) { clearInterval(this.mapRefreshIntervalId); } // 【新增】停止旧的地图定时器

    // 设置实体（村民、房屋）的刷新率，这个可以快一些
    const entityRefreshRate = Math.min(this.speed, this.maxFrontendRefreshRate);
    const entityInterval = 1000 / entityRefreshRate;
    console.log(`Adjusting entity refresh rate. Speed: ${this.speed}x, Rate: ${entityRefreshRate}Hz, Interval: ${entityInterval.toFixed(0)}ms`);
    this.dataRefreshIntervalId = setInterval(async () => {
      try { await this.loadVillagerData(); }
      catch (err) { console.error("Error refreshing entity data:", err); }
    }, entityInterval);

    // 【新增】设置地图地形的刷新率，这个可以慢一些，避免不必要的性能开销
    const mapRefreshInterval = 2000; // 每2秒刷新一次地图
    console.log(`Setting map terrain refresh interval to ${mapRefreshInterval}ms`);
    this.mapRefreshIntervalId = setInterval(async () => {
        try {
            await this.loadMapData();
        } catch(err) {
            console.error("Error refreshing map data:", err);
        }
    }, mapRefreshInterval);
  }

  async initialize() {
    // 1. 设置画布尺寸以匹配窗口
    this.setupCanvas();

    // 2. 使用 try...catch 块来处理任何初始化过程中可能发生的错误
    try {
      // 3. 从URL路径中解析出地图ID
      const pathParts = window.location.pathname.split('/');
      this.mapId = parseInt(pathParts[pathParts.length - 1], 10);
      if (isNaN(this.mapId)) {
        throw new Error('URL中的地图ID无效 (Invalid map ID in URL)');
      }
      
      // 4. 获取全局配置信息（例如视图参数）
      const configRes = await fetch('/api/config');
      const config = await configRes.json();
      this.camera.maxVisiblePixels = config.view.max_visible_pixels;
      
      // 5. 通知后端启动此地图的模拟
      await this.startSimulation();
      
      // 6. 设置后端的初始模拟速度为前端的默认速度 (1x)
      await this.setBackendSimulationSpeed(this.speed); 
      
      // 7. 加载初始世界状态
      await this.loadMapData();      // 加载地形数据
      await this.loadVillagerData(); // 加载村民和房屋数据
      
      // 8. 启动前端的定时刷新机制
      // 这会创建两个定时器：一个用于高频刷新村民/房屋，一个用于低频刷新地形
      this.adjustFrontendRefreshRate();
      
      // 9. 绑定速度控制面板的UI事件
      this.setupSpeedControls();
      
      // 10. 设置相机初始位置和缩放
      this.updateMinZoom(); // 根据配置计算最小缩放级别
      const initialTileSize = this.BASE_TILE_SIZE * this.camera.zoom;
      // 将相机定位到地图中心
      this.camera.x = (this.worldData.width * initialTileSize - window.innerWidth * this.dpr) / 2;
      this.camera.y = (this.worldData.height * initialTileSize - window.innerHeight * this.dpr) / 2;
      this.constrainCamera(); // 确保相机不超出地图边界

      // 11. 启动渲染循环
      this.startGameLoop();

    } catch (error) {
      // 12. 如果初始化过程中任何步骤失败，则执行以下操作
      console.error("初始化失败:", error);
      
      // 关键：清除可能已创建的任何定时器，防止内存泄漏
      if (this.dataRefreshIntervalId) { clearInterval(this.dataRefreshIntervalId); }
      if (this.mapRefreshIntervalId) { clearInterval(this.mapRefreshIntervalId); }
      
      // 在页面上向用户显示清晰的错误信息
      document.body.innerHTML = `<h1>加载地图失败</h1><p style="color:red;">${error.message}</p><p>请尝试返回主页或刷新。</p>`;
    }
  }

  async destroy() {
      if (this.dataRefreshIntervalId) {
          clearInterval(this.dataRefreshIntervalId);
          this.dataRefreshIntervalId = null;
      }
      // 【新增】清理地图刷新定时器
      if (this.mapRefreshIntervalId) {
          clearInterval(this.mapRefreshIntervalId);
          this.mapRefreshIntervalId = null;
      }
      console.log("All refresh intervals cleared.");
      
      await this.setBackendSimulationSpeed(1);
      await this.stopSimulation();
  }
}