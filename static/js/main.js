const { createApp, ref, reactive, onMounted } = Vue;

// 检查当前页面是否为index页面
if (window.location.pathname === '/' || window.location.pathname === '/index.html') {
  // 首页的Vue应用
  createApp({
    delimiters: window.vue_delimiters,
    data() {
      return {
        maps: [],
        showModal: false,
        newMap: null
      }
    },
    methods: {
      async loadConfig() {
        try {
          const res = await fetch('/api/config');
          const data = await res.json();
          this.newMap = {
            name: '',
            world: data.world,
            forest: data.forest,
            water: data.water
          };
        } catch (e) {
          alert('获取配置失败: ' + e.message);
        }
      },
      async fetchMaps() {
        const res = await fetch('/api/maps')
        this.maps = await res.json()
      },
      formatDate(ts) {
        return new Date(ts).toLocaleString()
      },
      async loadMap(id) {
        try {
          const res = await fetch(`/api/maps/${id}`);
          const data = await res.json();
          if (data.error) {
            alert('加载失败：' + data.error);
            return;
          }
          // 修改这里：使用新的路由路径
          window.location.href = `/view_map/${id}`;
        } catch (err) {
          alert('加载失败: ' + err.message);
        }
      },
      async confirmDelete(id) {
        if (confirm('确定删除这个地图吗？')) {
          try {
            await fetch(`/api/maps/${id}`, {
              method: 'DELETE'
            });
            await this.fetchMaps();
          } catch (err) {
            alert('删除失败: ' + err.message);
          }
        }
      },
      async createMap() {
        try {
          await fetch('/api/generate_map', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.newMap)
          });
          this.showModal = false;
          await this.loadConfig(); // 重置为默认配置
          await this.fetchMaps();
        } catch (err) {
          alert('创建失败: ' + err.message);
        }
      }
    },
    mounted() {
      this.fetchMaps();
      this.loadConfig();
    }
  }).mount('#app')
}