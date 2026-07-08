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

    getMessages(convId) {
        return this.get(`/conversations/${convId}/messages`);
    }

    sendMessage(convId, content) {
        return this.post(`/conversations/${convId}/messages`, { content });
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

    // 学习计划相关
    getPlans() {
        return this.get('/plans/');
    }

    createPlan(data) {
        return this.post('/plans/', data);
    }

    getPlan(id) {
        return this.get(`/plans/${id}`);
    }

    updatePlan(id, data) {
        return this.put(`/plans/${id}`, data);
    }

    deletePlan(id) {
        return this.delete(`/plans/${id}`);
    }

    generatePlan(data) {
        return this.post('/plans/generate', data);
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
}

const api = new ApiClient();
