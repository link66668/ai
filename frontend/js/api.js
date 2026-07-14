/**
 * API请求封装
 */
const API_BASE = '/api';

class ApiClient {
    constructor() {
        this.baseURL = API_BASE;
    }

    getToken() {
        return localStorage.getItem('token');
    }

    setToken(token) {
        localStorage.setItem('token', token);
    }

    removeToken() {
        localStorage.removeItem('token');
    }

    getUser() {
        const user = localStorage.getItem('user');
        return user ? JSON.parse(user) : null;
    }

    setUser(user) {
        localStorage.setItem('user', JSON.stringify(user));
    }

    removeUser() {
        localStorage.removeItem('user');
    }

    async request(url, options = {}) {
        const token = this.getToken();
        const headers = {
            ...options.headers,
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        if (!(options.body instanceof FormData) && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }

        try {
            const response = await fetch(`${this.baseURL}${url}`, {
                ...options,
                headers,
            });

            // 安全解析JSON，防止非JSON响应导致崩溃
            let data;
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                try {
                    data = JSON.parse(text);
                } catch {
                    throw new Error(`服务器返回非JSON响应 (${response.status})`);
                }
            }

            if (response.status === 401) {
                this.removeToken();
                this.removeUser();
                window.location.href = '/';
                throw new Error('登录已过期，请重新登录');
            }

            if (!response.ok) {
                throw new Error(data.msg || '请求失败');
            }

            return data;
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    get(url, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        return this.request(fullUrl, { method: 'GET' });
    }

    post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: data instanceof FormData ? data : JSON.stringify(data),
        });
    }

    put(url, data) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    }

    // 认证相关
    async login(username, password) {
        const data = await this.post('/auth/login', { username, password });
        if (data.code === 200) {
            this.setToken(data.data.token);
            this.setUser(data.data.user);
        }
        return data;
    }

    async register(username, password, email) {
        return this.post('/auth/register', { username, password, email });
    }

    async getCurrentUser() {
        return this.get('/auth/me');
    }

    async updateUser(data) {
        return this.put('/auth/me', data);
    }

    logout() {
        this.removeToken();
        this.removeUser();
        window.location.href = '/';
    }

    // 课程相关
    getCourses(status = 'active') {
        return this.get('/courses/', { status });
    }

    getCourse(id) {
        return this.get(`/courses/${id}`);
    }

    createCourse(data) {
        return this.post('/courses/', data);
    }

    updateCourse(id, data) {
        return this.put(`/courses/${id}`, data);
    }

    deleteCourse(id) {
        return this.delete(`/courses/${id}`);
    }

    archiveCourse(id) {
        return this.post(`/courses/${id}/archive`);
    }

    // 知识库开关
    toggleKbEnabled(courseId) {
        return this.post(`/courses/${courseId}/kb-toggle`);
    }

    // 知识库
    getKnowledgeBase(courseId) {
        return this.get(`/courses/${courseId}/knowledge-base`);
    }

    getDocumentMarkdown(docId) {
        return this.get(`/documents/${docId}/markdown`);
    }

    importCoursesCSV(formData) {
        return this.request('/courses/import-csv', {
            method: 'POST',
            body: formData,
        });
    }

    // 资料相关
    getDocuments(courseId) {
        const params = courseId ? { course_id: courseId } : {};
        return this.get('/documents/', params);
    }

    uploadDocument(formData) {
        return this.request('/documents/', {
            method: 'POST',
            body: formData,
        });
    }

    deleteDocument(id) {
        return this.delete(`/documents/${id}`);
    }

    searchDocuments(keyword, courseId) {
        const params = { q: keyword };
        if (courseId) params.course_id = courseId;
        return this.get('/documents/search', params);
    }

    // 对话相关
    getConversations(courseId) {
        const params = courseId ? { course_id: courseId } : {};
        return this.get('/conversations/', params);
    }

    createConversation(courseId, title) {
        return this.post('/conversations/', { course_id: courseId, title });
    }

    deleteConversation(id) {
        return this.delete(`/conversations/${id}`);
    }

    renameConversation(id, title) {
        return this.request(`/conversations/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ title }),
        });
    }

    getMessages(convId) {
        return this.get(`/conversations/${convId}/messages`);
    }

    // 任务相关
    getTasks(status, courseId) {
        const params = {};
        if (status) params.status = status;
        if (courseId) params.course_id = courseId;
        return this.get('/tasks/', params);
    }

    createTask(data) {
        return this.post('/tasks/', data);
    }

    updateTask(id, data) {
        return this.put(`/tasks/${id}`, data);
    }

    deleteTask(id) {
        return this.delete(`/tasks/${id}`);
    }

    completeTask(id) {
        return this.post(`/tasks/${id}/complete`);
    }

    decomposeTask(id) {
        return this.post(`/tasks/decompose/${id}`);
    }

    // Agent相关
    agentChat(message, courseId) {
        return this.post('/agent/chat', { message, course_id: courseId });
    }

    agentSummarize(text) {
        return this.post('/agent/summarize', { text });
    }

    agentExtractKnowledge(text) {
        return this.post('/agent/extract-knowledge', { text });
    }

    // 知识点整理
    organizeKnowledge(courseId, type = 'points') {
        return this.post('/agent/knowledge-organize', { course_id: courseId, type });
    }
    getStoredKnowledge(courseId, type = 'points') {
        return this.get('/agent/knowledge-organize', { course_id: courseId, type });
    }

    // ========== 流式 + 临时文件 + 中断 ==========

    /**
     * SSE 流式消息发送
     * @param {number} convId - 对话ID
     * @param {string} content - 消息内容
     * @param {string} tempFileSessionId - 临时文件会话ID（可选）
     * @param {string|null} kbCourseId - 引用知识库的课程ID（可选，null=不引用）
     * @param {function} onChunk - 每收到一个token的回调 (delta, fullText)
     * @param {function} onDone - 流结束回调 (fullText, citations)
     * @param {function} onError - 错误回调 (error)
     * @param {object} callbacks - 附加回调
     * @param {function} [callbacks.onToolCallStart] - 工具调用开始 (toolName, args)
     * @param {function} [callbacks.onToolCallEnd] - 工具调用结束 (toolName, resultCount)
     * @returns {AbortController} 用于中断的控制器
     */
    streamMessage(convId, content, tempFileSessionId, kbCourseId, onChunk, onDone, onError, callbacks = {}) {
        const token = this.getToken();
        const controller = new AbortController();

        fetch(`${this.baseURL}/conversations/${convId}/messages/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                content: content,
                temp_file_session_id: tempFileSessionId,
                kb_course_id: kbCourseId
            }),
            signal: controller.signal
        }).then(async (response) => {
            if (!response.ok) {
                const text = await response.text();
                throw new Error(text || '流式请求失败');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullText = '';
            let citations = [];

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // 解析 SSE 事件
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // 保留未完成的部分

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            const type = data.type || '';

                            if (type === 'tool_call_start') {
                                // LLM 决定搜索知识库
                                if (callbacks.onToolCallStart) {
                                    callbacks.onToolCallStart(
                                        data.function || 'kb_search',
                                        data.arguments || {}
                                    );
                                }
                                continue;
                            }

                            if (type === 'tool_call_end') {
                                // 搜索结果已返回
                                if (callbacks.onToolCallEnd) {
                                    callbacks.onToolCallEnd(
                                        data.function || 'kb_search',
                                        data.result_count || 0
                                    );
                                }
                                continue;
                            }

                            // 普通文本事件（兼容旧格式无 type 字段）
                            const isDone = data.done || (type === 'text' && data.done);
                            if (isDone) {
                                if (data.interrupted) {
                                    onDone(fullText, citations, true);
                                    return;
                                }
                                citations = data.citations || [];
                                if (data.full_response) {
                                    fullText = data.full_response;
                                }
                                onDone(fullText, citations, false);
                                return;
                            } else if (data.content) {
                                fullText += data.content;
                                onChunk(data.content, fullText);
                            }
                        } catch (e) {
                            // 跳过解析失败的行
                        }
                    }
                }
            }
            // 流正常结束但没有 done 标记
            onDone(fullText, citations, false);
        }).catch((err) => {
            if (err.name === 'AbortError') {
                onDone('', [], true);
            } else {
                onError(err);
            }
        });

        return controller;
    }

    /**
     * 上传临时文件到对话（后端异步处理，立即返回）
     */
    async uploadTempFile(convId, file) {
        const formData = new FormData();
        formData.append('file', file);
        // 注意：不能用 keepalive，因为文件可能超过 64KB 限制
        // 改为后端异步处理：上传立即返回，后台线程解析/OCR
        return this.request(`/conversations/${convId}/upload-temp`, {
            method: 'POST',
            body: formData,
        });
    }

    /**
     * 查询临时文件处理状态
     */
    async getTempFileStatus(convId, fileId) {
        return this.get(`/conversations/${convId}/temp-file-status/${fileId}`);
    }

    /**
     * 中断流式生成
     */
    async interruptStream(convId) {
        return this.post(`/conversations/${convId}/interrupt`);
    }

    /**
     * 查询文档处理进度
     */
    async getDocumentProcessing(docId) {
        return this.get(`/documents/${docId}/processing`);
    }

    /**
     * 重新处理文档
     */
    async reprocessDocument(docId) {
        return this.post(`/documents/${docId}/reprocess`);
    }

    // ========== AI 配置 ==========

    /**
     * 获取当前用户的AI配置
     */
    async getAiConfig() {
        return this.get('/ai-config/');
    }

    /**
     * 更新AI配置
     */
    async updateAiConfig(data) {
        return this.put('/ai-config/', data);
    }

    /**
     * 重置为系统默认配置
     */
    async resetAiConfig() {
        return this.delete('/ai-config/');
    }

    /**
     * 测试AI配置连接
     * @param {string} type - 模型类型: 'chat' | 'embedding' | 'vision' | 'doc'
     */
    async testAiConfig(type = 'chat') {
        return this.post('/ai-config/test', { type });
    }
}

const api = new ApiClient();
