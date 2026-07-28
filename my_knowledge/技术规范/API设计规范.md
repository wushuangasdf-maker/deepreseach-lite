# API 设计规范

## RESTful API 设计原则

### 资源命名

使用名词复数形式命名资源，URL 路径使用小写字母和连字符：

```
GET    /research          # 列出研究任务
POST   /research          # 创建研究任务
GET    /research/{id}     # 查询单个任务
DELETE /research/{id}     # 删除任务
```

### 状态码规范

- 200：成功获取资源
- 201：资源创建成功
- 202：请求已接受，处理中（异步任务）
- 400：请求参数错误
- 404：资源不存在
- 500：服务器内部错误

### 分页设计

列表接口统一使用以下查询参数：

- limit：每页条数，默认 20，最大 100
- offset：偏移量，默认 0

## 异步任务模式

长时间运行的研究任务采用异步模式：

1. POST /research 立即返回 task_id（201 Created）
2. 客户端轮询 GET /research/{task_id} 或订阅 SSE 流
3. 任务完成后通过 GET /research/{task_id}/report 获取结果

## SSE 实时推送

使用 Server-Sent Events 推送研究进度：

```
event: log
data: {"type": "log", "content": "正在搜索..."}

event: done
data: {"type": "done", "status": "completed", "result": "..."}
```

## 错误处理

所有错误响应包含统一格式：

```json
{
  "detail": "错误描述信息"
}
```

对于参数校验错误（422），FastAPI 自动生成包含具体字段错误信息的响应。
