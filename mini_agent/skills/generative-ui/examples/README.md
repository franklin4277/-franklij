# Generative UI 示例应用

这个目录包含了使用 Generative UI Expert skill 可以创建的示例应用。

## 📦 示例列表

### 1. 冒泡排序可视化 (bubble-sort-visualizer)
- **文件**: `bubble-sort-visualizer.html` (在 SKILL.md 中)
- **类型**: 交互式学习工具
- **功能**:
  - 可视化冒泡排序算法过程
  - 实时显示比较和交换次数
  - 可调速度控制
  - 动画效果展示

### 2. 2048 游戏 (game-2048.html)
- **文件**: `game-2048.html`
- **类型**: 实时游戏
- **功能**:
  - 经典 2048 游戏机制
  - 得分和最高分记录
  - 键盘和触摸操作支持
  - 优美的动画效果
  - 本地存储最佳成绩

### 3. 番茄工作法计时器 (pomodoro-timer.html)
- **文件**: `pomodoro-timer.html`
- **类型**: 实用工具应用
- **功能**:
  - 25/5/15 分钟标准番茄钟
  - 自定义时长设置
  - 统计今日完成的番茄数
  - 浏览器通知提醒
  - 自动切换工作/休息模式
  - 数据持久化

## 🚀 如何使用

### 方法 1: 直接打开
双击任意 `.html` 文件，在浏览器中直接打开即可使用。

### 方法 2: 本地服务器
如果需要更完整的功能（如某些浏览器 API），可以使用本地服务器：

```bash
# 使用 Python
python3 -m http.server 8000

# 或使用 Node.js
npx serve

# 然后访问 http://localhost:8000
```

## 💡 学习要点

### 从这些示例中你可以学到：

#### 1. **状态管理**
```javascript
// 游戏状态管理示例 (2048)
let grid = [];
let score = 0;

function updateState() {
    // 更新逻辑
    renderGrid();
}
```

#### 2. **动画实现**
```css
/* CSS 过渡动画 */
.tile {
    transition: all 0.15s ease-in-out;
}

/* CSS 关键帧动画 */
@keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.05); }
}
```

#### 3. **事件处理**
```javascript
// 键盘事件
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
        move('left');
    }
});

// 触摸事件
document.addEventListener('touchstart', handleTouchStart);
document.addEventListener('touchend', handleTouchEnd);
```

#### 4. **数据持久化**
```javascript
// localStorage 使用
localStorage.setItem('bestScore', score);
const bestScore = localStorage.getItem('bestScore') || 0;
```

#### 5. **浏览器 API**
```javascript
// Notification API
if ('Notification' in window) {
    Notification.requestPermission();
    new Notification('标题', { body: '内容' });
}

// Web Audio API
const audioContext = new AudioContext();
const oscillator = audioContext.createOscillator();
```

## 🎨 设计模式

### 1. **模块化设计**
每个功能都封装在独立的函数中，便于维护和扩展。

### 2. **响应式布局**
使用 Flexbox 和 Grid 实现自适应布局。

### 3. **渐进增强**
从基础功能开始，逐步添加高级特性。

### 4. **用户体验优先**
- 即时反馈
- 流畅动画
- 清晰的视觉层次
- 直观的交互

## 🔧 自定义指南

### 修改样式
所有样式都在 `<style>` 标签内，可以轻松修改：
- 颜色主题
- 字体大小
- 布局间距
- 动画效果

### 调整功能
JavaScript 代码模块化良好，可以：
- 修改游戏规则
- 调整计时器时长
- 改变算法可视化效果
- 添加新功能

### 添加新特性
示例提供了良好的扩展基础：
- 添加音效
- 集成排行榜
- 实现数据导出
- 添加主题切换

## 📚 更多示例想法

基于这些模板，你可以创建：

### 学习工具
- 其他排序算法可视化（快排、归并、堆排序）
- 数据结构演示（栈、队列、树、图）
- 数学概念可视化（函数图像、几何变换）
- 编程概念演示（递归、动态规划）

### 游戏
- 贪吃蛇
- 俄罗斯方块
- 扫雷
- 打地鼠
- 记忆翻牌

### 工具应用
- Markdown 编辑器
- 颜色选择器
- 单位转换器
- JSON 格式化工具
- 正则表达式测试器

### 可视化
- 图表生成器（柱状图、折线图、饼图）
- 思维导图工具
- 流程图编辑器
- 时间线生成器

## 🌟 最佳实践

### 性能优化
1. **避免不必要的重绘**
   - 使用 `requestAnimationFrame`
   - 批量 DOM 操作
   - CSS transform 代替 position

2. **事件优化**
   - 使用事件委托
   - 防抖和节流
   - 移除不需要的监听器

3. **内存管理**
   - 清理定时器
   - 避免内存泄漏
   - 合理使用闭包

### 代码质量
1. **可读性**
   - 清晰的命名
   - 适当的注释
   - 一致的代码风格

2. **可维护性**
   - 模块化设计
   - 单一职责原则
   - 避免重复代码

3. **健壮性**
   - 输入验证
   - 错误处理
   - 边界条件检查

## 🎓 学习路径

### 初级
1. 理解 HTML 结构
2. 掌握 CSS 样式
3. 学习基础 JavaScript

### 中级
1. DOM 操作
2. 事件处理
3. 状态管理
4. 动画实现

### 高级
1. 性能优化
2. 设计模式
3. 浏览器 API
4. 架构设计

## 🤝 贡献

如果你创建了有趣的应用示例，欢迎分享！

## 📝 许可证

所有示例代码采用 MIT 许可证，可自由使用和修改。

---

**探索更多可能，创造无限精彩！** 🚀
