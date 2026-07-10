/**
 * 工具函数
 */

// 显示提示消息
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 格式化日期
function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// 格式化日期时间
function formatDateTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hour}:${minute}`;
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes.toFixed(1)} ${units[i]}`;
}

// 获取文件图标类名
function getFileIcon(fileType) {
    const iconMap = {
        'txt': 'txt',
        'pdf': 'pdf',
        'doc': 'doc',
        'docx': 'doc',
        'ppt': 'doc',
        'pptx': 'doc',
        'xls': 'doc',
        'xlsx': 'doc',
        'png': 'img',
        'jpg': 'img',
        'jpeg': 'img',
        'gif': 'img',
    };
    return iconMap[fileType] || 'other';
}

// 获取文件图标emoji
function getFileEmoji(fileType) {
    const emojiMap = {
        'txt': '📄',
        'pdf': '📕',
        'doc': '📘',
        'docx': '📘',
        'ppt': '📙',
        'pptx': '📙',
        'xls': '📗',
        'xlsx': '📗',
        'png': '🖼️',
        'jpg': '🖼️',
        'jpeg': '🖼️',
        'gif': '🖼️',
    };
    return emojiMap[fileType] || '📎';
}

// 确认对话框
function confirmDialog(message) {
    return new Promise((resolve) => {
        const result = confirm(message);
        resolve(result);
    });
}

// HTML 转义
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 检查登录状态
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '/';
        return false;
    }
    return true;
}

// 获取当前用户
function getCurrentUser() {
    const user = localStorage.getItem('user');
    return user ? JSON.parse(user) : null;
}

// 退出登录
function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/';
}

// URL参数获取
function getUrlParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

// 防抖函数
function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// 节流函数
function throttle(fn, delay = 300) {
    let last = 0;
    return function (...args) {
        const now = Date.now();
        if (now - last >= delay) {
            last = now;
            fn.apply(this, args);
        }
    };
}

// Markdown增强渲染（用于AI回答）
function renderMarkdown(text) {
    if (!text) return '';

    let html = text;

    // 1. 先保护代码块（避免内部内容被后续正则处理）
    const codeBlocks = [];
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
        const idx = codeBlocks.length;
        codeBlocks.push({ lang, code: code.trim() });
        return `%%CODEBLOCK_${idx}%%`;
    });

    // 2. 保护行内代码
    const inlineCodes = [];
    html = html.replace(/`([^`]+)`/g, (match, code) => {
        const idx = inlineCodes.length;
        inlineCodes.push(code);
        return `%%INLINECODE_${idx}%%`;
    });

    // 3. 转义HTML
    html = html
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // 4. 表格
    html = html.replace(/(\|[^\n]+\|\n\|[\s\-:\|]+\|\n(?:\|[^\n]+\|\n?)*)/g, (match) => {
        const lines = match.trim().split('\n');
        if (lines.length < 2) return match;

        let tableHtml = '<table>';
        // 表头
        const headers = lines[0].split('|').filter(c => c.trim());
        tableHtml += '<thead><tr>' + headers.map(h => `<th>${h.trim()}</th>`).join('') + '</tr></thead>';

        // 数据行（跳过分隔行）
        tableHtml += '<tbody>';
        for (let i = 2; i < lines.length; i++) {
            const cells = lines[i].split('|').filter(c => c.trim());
            if (cells.length > 0) {
                tableHtml += '<tr>' + cells.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>';
            }
        }
        tableHtml += '</tbody></table>';
        return tableHtml;
    });

    // 5. 标题
    html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // 6. 引用块
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');
    // 合并连续引用块
    html = html.replace(/<\/blockquote>\n<blockquote>/g, '<br>');

    // 7. 分割线
    html = html.replace(/^(---|\*\*\*)$/gm, '<hr>');

    // 8. 无序列表
    html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
    // 将连续li包裹在ul中
    html = html.replace(/((?:<li>[^<]*<\/li>\n?)+)/g, '<ul>$1</ul>');

    // 9. 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // 注意：有序列表和无序列表都用li标记，这里简化处理，统一用ul

    // 10. 链接
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // 11. 图片
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');

    // 12. 引用标记 [1], [2] → 可点击上标
    html = html.replace(/\[(\d+)\]/g, '<sup class="citation" data-cite="$1">[$1]</sup>');

    // 13. 临时文件标记
    html = html.replace(/\(临时文件\)/g, '<span class="temp-file-badge">临时文件</span>');

    // 14. 粗体
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // 15. 斜体
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 16. 还原行内代码
    html = html.replace(/%%INLINECODE_(\d+)%%/g, (match, idx) => {
        return '<code>' + inlineCodes[parseInt(idx)] + '</code>';
    });

    // 17. 还原代码块
    html = html.replace(/%%CODEBLOCK_(\d+)%%/g, (match, idx) => {
        const block = codeBlocks[parseInt(idx)];
        const langLabel = block.lang ? `<span class="code-lang">${block.lang}</span>` : '';
        return `<pre>${langLabel}<code>${block.code}</code></pre>`;
    });

    // 18. 换行（放在最后，避免影响块级元素）
    html = html.replace(/\n/g, '<br>');

    // 19. 清理空ul
    html = html.replace(/<ul>\s*<\/ul>/g, '');
    html = html.replace(/<ul>\s*<br>\s*<\/ul>/g, '');

    return html;
}

// 获取优先级样式类
function getPriorityClass(priority) {
    const map = {
        '高': 'priority-high',
        '中': 'priority-medium',
        '低': 'priority-low',
    };
    return map[priority] || 'priority-medium';
}

// 获取状态样式
function getStatusText(status) {
    const map = {
        '待办': '待处理',
        '进行中': '进行中',
        '已完成': '已完成',
    };
    return map[status] || status;
}
