// API 基础地址
const API_BASE = 'http://localhost:8000';

// 状态更新间隔 (毫秒)
const UPDATE_INTERVAL = 1000;

// 日志 WebSocket 连接
let logWebSocket = null;
let currentLogLevel = 'all';
let maxLogEntries = 500; // 限制最大日志条数
const LOG_STORAGE_KEY = 'anima_bot_logs';
const MAX_STORED_LOGS = 1000; // localStorage 中保存的最大条数

// LLM Requests 存储
const LLM_REQUESTS_STORAGE_KEY = 'anima_bot_llm_requests';
const MAX_STORED_LLM_REQUESTS = 50; // localStorage 中保存的最大请求数
const EXPANDED_REQUESTS_KEY = 'anima_bot_expanded_requests'; // 记录展开的请求 ID

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    startPolling();
    setupEventListeners();
    loadLogsFromStorage();
    connectLogWebSocket();
    setupLogControls();
    setupPageCleanup();

    // 从 localStorage 加载 LLM requests（先显示缓存数据）
    const storedRequests = loadLLMRequestsFromStorage();
    if (storedRequests) {
        renderLLMRequests(storedRequests);
    }
    

    // 启动轮询（会从 API 获取最新数据并覆盖缓存）
    startLLMPolling();
});

// 页面卸载时清理
function setupPageCleanup() {
    // 页面刷新或关闭时正确关闭 WebSocket
    window.addEventListener('beforeunload', () => {
        if (logWebSocket && logWebSocket.readyState === WebSocket.OPEN) {
            console.log('[Log WS] Closing connection on page unload');
            logWebSocket.close(1000, 'Page unload');
        }
    });

    // 页面隐藏时（如切换标签页）可以选择性地处理
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            console.log('[Log WS] Page hidden');
        } else {
            console.log('[Log WS] Page visible');
            // 如果连接断开了，重新连接
            if (!logWebSocket || logWebSocket.readyState === WebSocket.CLOSED) {
                connectLogWebSocket();
            }
        }
    });
}

// 事件监听
function setupEventListeners() {
    // 聊天输入框回车发送
    const chatInput = document.getElementById('chat-input');
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendChat();
        }
    });
}

// 设置日志控制
function setupLogControls() {
    const levelFilter = document.getElementById('log-level-filter');
    levelFilter.addEventListener('change', (e) => {
        currentLogLevel = e.target.value;
        filterLogs();
    });
}

// 连接日志 WebSocket
function connectLogWebSocket() {
    // 如果已有连接，先关闭
    if (logWebSocket && logWebSocket.readyState !== WebSocket.CLOSED) {
        console.log('[Log WS] Closing existing connection...');
        logWebSocket.onclose = null; // 移除旧的 onclose，避免触发重连
        logWebSocket.close();
    }

    const wsUrl = `ws://localhost:8000/ws/logs`;
    console.log('[Log WS] Connecting to:', wsUrl);
    logWebSocket = new WebSocket(wsUrl);

    logWebSocket.onopen = () => {
        console.log('[Log WS] Connected successfully');
    };

    logWebSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // 忽略心跳消息
        if (data.type === 'heartbeat') {
            return;
        }

        addLogEntry(data);
        saveLogToStorage(data);
    };

    logWebSocket.onclose = (event) => {
        console.log('[Log WS] Disconnected, code:', event.code, 'reason:', event.reason);

        // 只有在非正常关闭时才重连（页面刷新时 code 会是 1000）
        if (event.code !== 1000) {
            console.log('[Log WS] Reconnecting in 3s...');
            setTimeout(connectLogWebSocket, 3000);
        }
    };

    logWebSocket.onerror = (error) => {
        console.error('[Log WS] Error:', error);
    };
}

// 从 localStorage 加载日志
function loadLogsFromStorage() {
    try {
        const stored = localStorage.getItem(LOG_STORAGE_KEY);
        if (stored) {
            const logs = JSON.parse(stored);
            console.log(`[Storage] Loaded ${logs.length} logs from storage`);
            logs.forEach(logEntry => addLogEntry(logEntry, false)); // false = 不保存到 storage
        }
    } catch (error) {
        console.error('[Storage] Error loading logs:', error);
    }
}

// 保存单条日志到 localStorage
function saveLogToStorage(logEntry) {
    try {
        const stored = localStorage.getItem(LOG_STORAGE_KEY);
        let logs = stored ? JSON.parse(stored) : [];

        logs.push(logEntry);

        // 限制存储的日志数量
        if (logs.length > MAX_STORED_LOGS) {
            logs = logs.slice(-MAX_STORED_LOGS);
        }

        localStorage.setItem(LOG_STORAGE_KEY, JSON.stringify(logs));
    } catch (error) {
        console.error('[Storage] Error saving log:', error);
        // 如果存储失败，可能是容量满了，清空旧数据
        if (error.name === 'QuotaExceededError') {
            console.warn('[Storage] Storage full, clearing old logs');
            clearLogStorage();
            saveLogToStorage(logEntry); // 重试保存当前日志
        }
    }
}

// 清空 localStorage 中的日志
function clearLogStorage() {
    localStorage.removeItem(LOG_STORAGE_KEY);
}

// 添加日志条目
function addLogEntry(logEntry, saveToStorage = true) {
    const container = document.getElementById('log-container');

    // 过滤日志级别
    if (!shouldShowLog(logEntry.level)) {
        return;
    }

    const logDiv = document.createElement('div');
    logDiv.className = `log-entry log-${logEntry.level.toLowerCase()}`;
    logDiv.dataset.level = logEntry.level;

    const time = new Date(logEntry.timestamp).toLocaleTimeString();
    logDiv.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-level">${logEntry.level}</span>
        <span class="log-source">${logEntry.source}</span>
        <span class="log-message">${escapeHtml(logEntry.message)}</span>
    `;

    container.appendChild(logDiv);

    // 限制日志条数
    while (container.children.length > maxLogEntries) {
        container.removeChild(container.firstChild);
    }

    // 自动滚动
    const autoScroll = document.getElementById('auto-scroll');
    if (autoScroll.checked) {
        container.scrollTop = container.scrollHeight;
    }
}

// 判断是否应该显示日志
function shouldShowLog(level) {
    if (currentLogLevel === 'all') return true;
    if (currentLogLevel === 'ERROR') return level === 'ERROR';
    if (currentLogLevel === 'INFO') return ['ERROR', 'INFO', 'WARNING'].includes(level);
    if (currentLogLevel === 'DEBUG') return true;
    return true;
}

// 过滤现有日志
function filterLogs() {
    const container = document.getElementById('log-container');
    const entries = container.querySelectorAll('.log-entry');

    entries.forEach(entry => {
        if (shouldShowLog(entry.dataset.level)) {
            entry.style.display = 'block';
        } else {
            entry.style.display = 'none';
        }
    });
}

// 清空日志
function clearLogs() {
    document.getElementById('log-container').innerHTML = '';
    clearLogStorage();
    console.log('[Logs] Cleared all logs (display and storage)');
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 开始轮询状态
function startPolling() {
    updateStatus();
    setInterval(updateStatus, UPDATE_INTERVAL);
}

// 更新状态
async function updateStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        if (!response.ok) {
            throw new Error('Failed to fetch status');
        }
        const data = await response.json();

        // 调试：打印收到的数据
        console.log('Status data:', data);

        // 检查 agent 是否已初始化
        if (!data.initialized) {
            updateConnectionStatus(false);
            setText('agent-status', 'Initializing...');
            return;
        }

        updateConnectionStatus(data.connected);
        updateBasicInfo(data);
        updateHealthHunger(data);
        updateInventory(data);
        updateEnvironment(data);
        updateScreenshot(data);

    } catch (error) {
        console.error('Error updating status:', error);
        updateConnectionStatus(false);
    }
}

// 更新连接状态
function updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('status-text');

    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Disconnected';
    }
}

// 更新基本信息
function updateBasicInfo(data) {
    setText('agent-status', data.status || '-');

    if (data.mc_state?.position) {
        const pos = data.mc_state.position;
        setText('position', `X: ${pos.x?.toFixed(1) || 0}, Y: ${pos.y?.toFixed(1) || 0}, Z: ${pos.z?.toFixed(1) || 0}`);
    } else {
        setText('position', '-');
    }

    setText('biome', data.mc_state?.biome || '-');
    setText('time-of-day', data.mc_state?.time_of_day || '-');
}

// 更新血量和饥饿值
function updateHealthHunger(data) {
    const health = data.mc_state?.health;
    const hunger = data.mc_state?.hunger;

    updateBar('health-bar', 'health-value', health, 20);
    updateBar('hunger-bar', 'hunger-value', hunger, 20);
}

// 更新进度条
function updateBar(barId, valueId, value, max) {
    const bar = document.getElementById(barId);
    const valueSpan = document.getElementById(valueId);

    if (value !== null && value !== undefined) {
        const percentage = Math.min(100, Math.max(0, (value / max) * 100));
        bar.style.width = `${percentage}%`;
        valueSpan.textContent = value.toFixed(1);
    } else {
        bar.style.width = '0%';
        valueSpan.textContent = '-';
    }
}

// 更新背包
function updateInventory(data) {
    const container = document.getElementById('inventory-list');
    const inventory = data.mc_state?.inventory;

    if (!inventory || Object.keys(inventory).length === 0) {
        container.innerHTML = '<p class="empty-state">No items</p>';
        return;
    }

    const items = Object.entries(inventory)
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => `<div class="inventory-item"><span class="item-name">${name}</span><span class="item-count">${count}</span></div>`)
        .join('');

    container.innerHTML = items;
}

// 更新环境信息
function updateEnvironment(data) {
    const blocksContainer = document.getElementById('nearby-blocks');
    const entitiesContainer = document.getElementById('nearby-entities');

    // 方块
    const blocks = data.mc_state?.nearby_blocks;
    if (blocks && blocks.length > 0) {
        blocksContainer.innerHTML = blocks.slice(0, 20).map(b => `<span class="tag">${b}</span>`).join('');
    } else {
        blocksContainer.textContent = '-';
    }

    // 实体
    const entities = data.mc_state?.entities;
    if (entities && Object.keys(entities).length > 0) {
        entitiesContainer.innerHTML = Object.entries(entities)
            .slice(0, 10)
            .map(([name, dist]) => `<span class="tag">${name} (${dist.toFixed(1)}m)</span>`)
            .join('');
    } else {
        entitiesContainer.textContent = '-';
    }
}

// 更新截图
async function updateScreenshot(data) {
    const img = document.getElementById('screenshot');
    if (data.last_screenshot) {
        img.src = `data:image/png;base64,${data.last_screenshot}`;
    }
}

// 发送聊天消息
async function sendChat() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    try {
        const response = await fetch(`${API_BASE}/api/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'chat',
                content: message
            })
        });

        if (response.ok) {
            input.value = '';
            console.log('Chat sent:', message);
        }
    } catch (error) {
        console.error('Error sending chat:', error);
    }
}

// 执行代码
async function executeCode() {
    const input = document.getElementById('code-input');
    const code = input.value.trim();

    if (!code) return;

    try {
        const response = await fetch(`${API_BASE}/api/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'code_run_request',
                content: code
            })
        });

        if (response.ok) {
            input.value = '';
            console.log('Code executed');
        }
    } catch (error) {
        console.error('Error executing code:', error);
    }
}

// 切换摄像头 (需要实现)
async function toggleCamera() {
    // 发送代码请求截图/视角切换
    await executeCodeByContent(`
        // bot 对象已存在，直接使用
        bot.chat("Camera toggle requested");
    `);
}

// 请求观察更新 - 直接刷新状态
async function requestObservation() {
    await updateStatus();
}

// 执行预设代码
async function executeCodeByContent(code) {
    try {
        const response = await fetch(`${API_BASE}/api/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'code_run_request',
                content: code.trim()
            })
        });
    } catch (error) {
        console.error('Error executing code:', error);
    }
}

// 辅助函数：设置文本
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ==================== LLM Requests ====================

const LLM_POLL_INTERVAL = 2000; // 2秒轮询一次

function startLLMPolling() {
    refreshLLMRequests();
    setInterval(refreshLLMRequests, LLM_POLL_INTERVAL);
}

// 从 localStorage 加载 LLM requests
function loadLLMRequestsFromStorage() {
    try {
        const stored = localStorage.getItem(LLM_REQUESTS_STORAGE_KEY);
        if (stored) {
            return JSON.parse(stored);
        }
    } catch (error) {
        console.error('[LLM Storage] Error loading requests:', error);
    }
    return null;
}

// 保存 LLM requests 到 localStorage
function saveLLMRequestsToStorage(requests) {
    try {
        // 只保存最近的请求数量
        const toSave = requests.slice(0, MAX_STORED_LLM_REQUESTS);
        localStorage.setItem(LLM_REQUESTS_STORAGE_KEY, JSON.stringify(toSave));
    } catch (error) {
        console.error('[LLM Storage] Error saving requests:', error);
        if (error.name === 'QuotaExceededError') {
            console.warn('[LLM Storage] Storage full, clearing old requests');
            localStorage.removeItem(LLM_REQUESTS_STORAGE_KEY);
            saveLLMRequestsToStorage(requests.slice(0, MAX_STORED_LLM_REQUESTS / 2));
        }
    }
}

// 加载展开的请求 ID
function loadExpandedRequests() {
    try {
        const stored = localStorage.getItem(EXPANDED_REQUESTS_KEY);
        if (stored) {
            return new Set(JSON.parse(stored));
        }
    } catch (error) {
        console.error('[Expanded State] Error loading:', error);
    }
    return new Set();
}

// 保存展开的请求 ID
function saveExpandedRequests(expandedIds) {
    try {
        localStorage.setItem(EXPANDED_REQUESTS_KEY, JSON.stringify([...expandedIds]));
    } catch (error) {
        console.error('[Expanded State] Error saving:', error);
    }
}

async function refreshLLMRequests() {
    try {
        const response = await fetch(`${API_BASE}/api/llm-requests`);
        if (response.ok) {
            const requests = await response.json();
            // 保存到 localStorage
            saveLLMRequestsToStorage(requests);
            renderLLMRequests(requests);
        }
    } catch (error) {
        console.error('[LLM] Error fetching requests:', error);
        // 如果 API 请求失败，尝试从 localStorage 加载
        const storedRequests = loadLLMRequestsFromStorage();
        if (storedRequests) {
            renderLLMRequests(storedRequests);
        }
    }
}

function renderLLMRequests(requests) {
    const container = document.getElementById('llm-requests-container');

    if (!requests || requests.length === 0) {
        container.innerHTML = '<p class="empty-state">No requests yet</p>';
        return;
    }

    // 获取保存的展开状态
    const expandedIds = loadExpandedRequests();

    container.innerHTML = requests.map((req, index) => {
        const time = new Date(req.timestamp * 1000).toLocaleString();
        const messagesCount = req.messages.length;
        const hasContent = req.response.content ? '✓' : '✗';
        const hasToolCalls = req.response.tool_calls.length > 0 ? `✓ (${req.response.tool_calls.length})` : '✗';

        // 检查是否应该在展开状态
        const isOpen = expandedIds.has(req.id);
        const openAttr = isOpen ? 'open' : '';

        return `
            <details class="llm-request-item" data-request-id="${req.id}" ${openAttr}>
                <summary class="llm-request-summary">
                    <span class="llm-request-index">#${requests.length - index}</span>
                    <span class="llm-request-time">${time}</span>
                    <span class="llm-request-model">${req.model}</span>
                    <span class="llm-request-stats">
                        📝 ${messagesCount} messages |
                        💬 ${hasContent} |
                        🔧 ${hasToolCalls} |
                        ⏱️ ${req.latency.toFixed(2)}s
                    </span>
                </summary>
                <div class="llm-request-details">
                    <h4>Messages (${messagesCount})</h4>
                    <div class="llm-messages">
                        ${req.messages.map(msg => renderMessage(msg)).join('')}
                    </div>
                    <h4>Response</h4>
                    <div class="llm-response">
                        ${req.response.content ? `<pre><code>${escapeHtml(req.response.content)}</code></pre>` : '<p class="empty-state">No text content</p>'}
                        ${req.response.tool_calls.length > 0 ? `
                            <h5>Tool Calls:</h5>
                            ${req.response.tool_calls.map(tc => {
                                // 兼容新旧两种格式
                                const name = tc.name || (tc.function && tc.function.name) || 'unknown';
                                const args = tc.arguments || (tc.function && tc.function.arguments) || '';
                                return `
                                    <div class="tool-call">
                                        <strong>${escapeHtml(name)}</strong>
                                        <pre><code>${escapeHtml(args)}</code></pre>
                                    </div>
                                `;
                            }).join('')}
                        ` : ''}
                    </div>
                </div>
            </details>
        `;
    }).join('');

    // 添加事件监听器来追踪展开/折叠状态
    const detailsElements = container.querySelectorAll('details.llm-request-item');
    detailsElements.forEach(details => {
        details.addEventListener('toggle', (e) => {
            const requestId = e.target.dataset.requestId;
            const currentExpanded = loadExpandedRequests();

            if (e.target.open) {
                currentExpanded.add(requestId);
            } else {
                currentExpanded.delete(requestId);
            }

            saveExpandedRequests(currentExpanded);
        });
    });
}

function renderMessage(msg) {
    const role = msg.role;
    const content = msg.content || '';

    return `
        <div class="message-item message-${role}">
            <span class="message-role">${role}</span>
            <div class="message-content">
                ${typeof content === 'string' ? escapeHtml(content) : `<em>[${content.type}]</em>`}
            </div>
        </div>
    `;
}
