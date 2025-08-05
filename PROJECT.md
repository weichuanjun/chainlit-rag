# Chainlit RAG 知识库系统

## 项目概述

这是一个基于 Chainlit 和 RAG (Retrieval-Augmented Generation) 技术的智能知识库系统，支持文档上传、向量化搜索和智能问答。

## 项目结构

```
chainlit-rag/
├── .gitignore              # Git忽略文件配置
├── README.md               # 项目说明文档
├── PROJECT.md              # 项目结构说明（本文件）
├── requirements.txt        # Python依赖包
├── config.py              # 配置文件
├── Dockerfile             # Docker镜像构建文件
├── docker-compose.yml     # Docker生产环境配置
├── docker-compose.dev.yml # Docker开发环境配置
├── docker-manage-dev.sh   # Docker开发环境管理脚本
├── backend/               # 后端服务
│   ├── models/           # 数据模型
│   └── services/         # 业务服务
├── frontend/             # 前端界面
│   ├── app.py           # Chainlit应用
│   └── chainlit.md      # Chainlit配置
├── docker/               # Docker相关文件
│   ├── integrated_server.py  # 整合服务器
│   ├── init_db.py           # 数据库初始化
│   └── init.sql             # 数据库结构
├── configs/              # 配置文件
├── deployment/           # 部署相关
├── cloudformation/       # AWS CloudFormation模板
├── lambda_functions/     # AWS Lambda函数
├── fix-log/             # 修复日志和文档
├── data/                # 数据目录（git忽略）
├── uploads/             # 上传文件目录（git忽略）
└── logs/                # 日志目录（git忽略）
```

## 核心功能

### ✅ 已实现功能
- **文档上传**：支持 txt、pdf、docx、md、csv、json 格式
- **智能向量化**：使用 OpenAI Embedding API 生成文档向量
- **RAG搜索**：基于余弦相似度的智能文档检索
- **智能问答**：基于检索到的文档内容生成准确回答
- **用户认证**：完整的用户注册、登录、验证系统
- **Docker支持**：完整的容器化部署方案
- **热重载开发**：开发环境支持代码修改自动重载

### 🚀 技术栈
- **前端**：Chainlit (Python Web UI框架)
- **后端**：Flask (Python Web框架)
- **数据库**：PostgreSQL
- **缓存**：Redis
- **向量搜索**：OpenAI Embedding API
- **容器化**：Docker + Docker Compose
- **云部署**：AWS Lambda + CloudFormation

## 快速开始

### 开发环境启动

```bash
# 1. 克隆项目
git clone <repository-url>
cd chainlit-rag

# 2. 设置环境变量
export OPENAI_API_KEY="your-openai-api-key"

# 3. 启动开发环境
./docker-manage-dev.sh start

# 4. 访问应用
# Chainlit界面: http://localhost:8000
# API接口: http://localhost:5001
```

### 开发环境管理

```bash
# 查看服务状态
./docker-manage-dev.sh status

# 查看日志
./docker-manage-dev.sh logs

# 重启服务
./docker-manage-dev.sh restart

# 停止服务
./docker-manage-dev.sh stop

# 清理环境
./docker-manage-dev.sh clean
```

## 使用说明

### 1. 用户注册/登录
- 访问 http://localhost:8000
- 点击"登录"按钮
- 注册新用户或使用现有账户登录

### 2. 上传文档
- 登录后点击"上传文档"
- 选择支持的文件格式
- 等待文档处理和向量化完成

### 3. 智能问答
- 在聊天界面输入问题
- 系统会自动检索相关文档
- 基于文档内容生成准确回答

## 开发指南

### 代码结构
- `frontend/app.py`：Chainlit前端应用
- `docker/integrated_server.py`：Flask后端API
- `backend/services/`：业务逻辑服务
- `backend/models/`：数据模型定义

### 添加新功能
1. 在 `backend/services/` 中添加业务逻辑
2. 在 `docker/integrated_server.py` 中添加API路由
3. 在 `frontend/app.py` 中添加前端交互
4. 更新 `requirements.txt` 添加新依赖

### 调试技巧
- 使用 `./docker-manage-dev.sh logs` 查看实时日志
- 代码修改后会自动重载
- 数据库数据持久化在 `./data/` 目录

## 部署说明

### 生产环境
```bash
# 使用生产环境配置
docker-compose up -d
```

### AWS云部署
- 参考 `cloudformation/` 目录中的模板
- 使用 `deployment/deploy.sh` 脚本部署

## 注意事项

1. **API密钥**：确保设置正确的 OpenAI API 密钥
2. **文件大小**：建议上传文件不超过 50MB
3. **数据备份**：重要数据请定期备份 `./data/` 目录
4. **安全配置**：生产环境请修改默认密码和JWT密钥

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交代码变更
4. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证。

---

**最后更新**：2025-01-27  
**版本**：v1.0.0  
**状态**：✅ 生产就绪 