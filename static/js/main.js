// --- 1. 获取并设置 Canvas ---
const canvas = document.getElementById('world-canvas');
const ctx = canvas.getContext('2d');
canvas.style.cursor = 'grab';

// --- 2. 定义常量与状态 ---
const TERRAIN_COLORS = { '0': '#F0E68C', '1': '#228B22', '2': '#1E90FF' };
const BASE_TILE_SIZE = 16;
let dpr = window.devicePixelRatio || 1;

// --- 3. 核心：虚拟摄像头与交互状态 ---
const camera = {
    x: 0, y: 0, zoom: 1, minZoom: 0.1, maxZoom: 5, maxVisiblePixels: 500000
};
const interaction = {
    isDragging: false, isPinching: false, lastX: 0, lastY: 0,
    initialPinchDistance: 0, lastZoom: 1
};
let worldData = null;

// --- 4. 摄像头约束函数 (无变化) ---
function constrainCamera() {
    if (!worldData) return;
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

// --- 5. 核心绘图函数 (已移除约束调用) ---
function draw() {
    if (!worldData) return;
    // 不再在这里调用 constrainCamera()
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
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
            if (!isFinite(screenX) || !isFinite(screenY)) continue;
            ctx.fillStyle = color;
            ctx.fillRect(screenX, screenY, currentTileSize + 1, currentTileSize + 1);
        }
    }
    ctx.restore();
}

function gameLoop() { try { draw(); requestAnimationFrame(gameLoop); } catch (error) { console.error("游戏循环中发生严重错误:", error); } }

// --- 6. 事件处理 (核心修改点) ---
function setupCanvas() { dpr = window.devicePixelRatio || 1; canvas.width = Math.round(window.innerWidth * dpr); canvas.height = Math.round(window.innerHeight * dpr); canvas.style.width = `${window.innerWidth}px`; canvas.style.height = `${window.innerHeight}px`; }
function updateMinZoom() { const canvasLogicalArea = window.innerWidth * window.innerHeight; const tileScreenArea = canvasLogicalArea / camera.maxVisiblePixels; const minTileSize = Math.sqrt(tileScreenArea); camera.minZoom = minTileSize / BASE_TILE_SIZE; }
function getDistance(p1, p2) { return Math.sqrt(Math.pow(p2.clientX - p1.clientX, 2) + Math.pow(p2.clientY - p1.clientY, 2)); }
function zoomAtPoint(mouseX, mouseY, zoomChange) { const worldX = (mouseX + camera.x) / camera.zoom; const worldY = (mouseY + camera.y) / camera.zoom; camera.zoom = Math.max(camera.minZoom, Math.min(camera.maxZoom, camera.zoom * zoomChange)); const newZoom = camera.zoom; camera.x = worldX * newZoom - mouseX; camera.y = worldY * newZoom - mouseY; }

canvas.addEventListener('mousedown', (e) => { interaction.isDragging = true; interaction.lastX = e.clientX; interaction.lastY = e.clientY; canvas.style.cursor = 'grabbing'; });
canvas.addEventListener('mousemove', (e) => {
    if (!interaction.isDragging) return;
    const dx = e.clientX - interaction.lastX;
    const dy = e.clientY - interaction.lastY;
    camera.x -= dx;
    camera.y -= dy;
    constrainCamera(); // 在操作后立刻约束
    interaction.lastX = e.clientX;
    interaction.lastY = e.clientY;
});
canvas.addEventListener('mouseup', () => { interaction.isDragging = false; canvas.style.cursor = 'grab'; });
canvas.addEventListener('mouseleave', () => { interaction.isDragging = false; canvas.style.cursor = 'grab'; });
canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomAmount = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    zoomAtPoint(e.clientX, e.clientY, zoomAmount);
    constrainCamera(); // 在操作后立刻约束
});
canvas.addEventListener('touchstart', (e) => { e.preventDefault(); if (e.touches.length === 1) { interaction.isDragging = true; interaction.lastX = e.touches[0].clientX; interaction.lastY = e.touches[0].clientY; } else if (e.touches.length === 2) { interaction.isDragging = false; interaction.isPinching = true; interaction.initialPinchDistance = getDistance(e.touches[0], e.touches[1]); interaction.lastZoom = camera.zoom; } });
canvas.addEventListener('touchmove', (e) => {
    e.preventDefault();
    if (interaction.isDragging && e.touches.length === 1) {
        const dx = e.touches[0].clientX - interaction.lastX;
        const dy = e.touches[0].clientY - interaction.lastY;
        camera.x -= dx;
        camera.y -= dy;
        interaction.lastX = e.touches[0].clientX;
        interaction.lastY = e.touches[0].clientY;
    } else if (interaction.isPinching && e.touches.length === 2) {
        if (interaction.initialPinchDistance <= 0) return;
        const currentPinchDistance = getDistance(e.touches[0], e.touches[1]);
        const zoomFactor = currentPinchDistance / interaction.initialPinchDistance;
        let newZoom = interaction.lastZoom * zoomFactor;
        newZoom = Math.max(camera.minZoom, Math.min(camera.maxZoom, newZoom));
        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const worldX = (midX + camera.x) / camera.zoom;
        const worldY = (midY + camera.y) / camera.zoom;
        camera.zoom = newZoom;
        camera.x = worldX * camera.zoom - midX;
        camera.y = worldY * camera.zoom - midY;
    }
    // 无论触摸操作是拖动还是缩放，都在操作结束后统一进行一次约束
    constrainCamera();
});
canvas.addEventListener('touchend', (e) => { interaction.isDragging = false; interaction.isPinching = false; });
function handleResize() { setupCanvas(); updateMinZoom(); }
window.addEventListener('resize', handleResize);

// --- 7. 初始化函数 ---
async function initialize() { try { setupCanvas(); const response = await fetch('/api/world'); if (!response.ok) throw new Error(`网络请求失败! 状态码: ${response.status}`); worldData = await response.json(); camera.maxVisiblePixels = worldData.max_visible_pixels || 500000; updateMinZoom(); const initialTileSize = BASE_TILE_SIZE * camera.zoom; camera.x = (worldData.width * initialTileSize - window.innerWidth) / 2; camera.y = (worldData.height * initialTileSize - window.innerHeight) / 2; constrainCamera(); gameLoop(); } catch (error) { console.error("初始化失败:", error); document.body.innerHTML = `<h1>加载世界失败</h1><p style='color:red;'>${error.message}</p>`; } }

initialize();