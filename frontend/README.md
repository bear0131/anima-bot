# Anima Bot Frontend

简单的 Web 控制面板，用于显示 agent 状态和发送命令。

## 使用方法

### 方法 1: 直接用浏览器打开
```
frontend/index.html
```
直接在浏览器中打开即可。

### 方法 2: 使用 HTTP 服务器
```bash
# 在项目根目录运行
python -m http.server 8080 --directory frontend
```
然后访问: http://localhost:8080

## 功能

- **状态显示**: 位置、血量、饥饿、生物群系、时间
- **背包**: 显示所有物品及数量
- **环境**: 附近方块和实体
- **截图**: 实时游戏画面
- **快捷操作**: 开关摄像头、刷新状态
- **聊天**: 发送聊天消息
- **执行代码**: 运行 JavaScript 代码

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/status` | GET | 获取 agent 状态 |
| `/api/screenshot` | GET | 获取最新截图 |
| `/api/inventory` | GET | 获取背包 |
| `/api/command` | POST | 发送命令 |

## 命令格式

```json
{
  "type": "chat",
  "content": "Hello!"
}
```

或

```json
{
  "type": "code_run_request",
  "content": "bot.chat('test');"
}
```
