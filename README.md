# Chainlit RAG 知识库系统

一个基于AWS Serverless架构的智能知识库系统，使用Chainlit构建用户界面，支持文档上传、向量化存储、智能问答和可配置的Agent工作流。

## 🚀 功能特性

### 🔐 用户管理
- 用户注册和登录
- JWT令牌认证
- 用户个人资料管理
- 安全的密码存储

### 📄 文档管理
- 支持多种文件格式（PDF、TXT、MD、DOCX）
- 文件上传到S3
- 自动文本提取和分块
- 文档状态跟踪

### 🧠 智能问答
- 基于向量相似度的文档检索
- OpenAI GPT模型生成回答
- 可配置的Agent工作流
- 聊天历史记录

### 🤖 Agent系统
- **默认RAG助手**: 基础问答功能
- **分析型助手**: 深度分析和结构化回答
- **对话型助手**: 多轮对话支持
- 可扩展的Agent配置

### 💬 聊天界面
- 现代化的Chainlit Web界面
- 实时聊天体验
- 文档引用显示
- 聊天历史管理

## 🏗️ 系统架构

### 🐳 Docker容器化架构（推荐）
```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Chainlit   │  │ PostgreSQL  │  │    Redis    │         │
│  │   + API     │  │  Database   │  │    Cache    │         │
│  │   :8000     │  │   :5432     │  │   :6379     │         │
│  │   :5000     │  │             │  │             │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ File Storage│  │Vector Index │  │   Nginx     │         │
│  │ (uploads/)  │  │ (FAISS)     │  │ (生产模式)   │         │
│  │             │  │ (data/)     │  │   :80       │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### ☁️ AWS Serverless架构（可选）
详见 [cloudformation/](cloudformation/) 目录的Serverless部署方案

### 技术栈
- **前端**: Chainlit (Python)
- **后端**: Flask API (Python)
- **数据库**: PostgreSQL / DynamoDB
- **缓存**: Redis
- **文件存储**: 本地存储 / S3
- **向量数据库**: FAISS (本地)
- **AI服务**: OpenAI GPT + Embeddings
- **容器化**: Docker + Docker Compose
- **代理**: Nginx (可选)

## 📦 快速开始

### 🐳 Docker部署（推荐）

#### 前置要求
- Docker & Docker Compose
- OpenAI API Key

#### 一键部署
```bash
# 1. 克隆项目
git clone <your-repo-url>
cd chainlit-rag

# 2. 运行部署脚本
chmod +x docker-deploy.sh
./docker-deploy.sh
```

#### 访问应用
- **主界面**: http://localhost:8000
- **API接口**: http://localhost:5000
- **默认账户**: admin@example.com / admin123

详细说明请参考 [DOCKER-README.md](DOCKER-README.md)

---

### ☁️ AWS Serverless部署（可选）

#### 前置要求
- Python 3.9+
- AWS CLI 配置
- OpenAI API Key

#### 部署步骤
```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env 设置 OPENAI_API_KEY

# 2. 部署到AWS
chmod +x deployment/deploy.sh
./deployment/deploy.sh

# 3. 启动前端
source .env.dev
chainlit run frontend/app.py
```

---

### 💻 本地开发

#### 前置要求
- Python 3.9+
- OpenAI API Key

#### 启动开发环境
```bash
# 1. 启动本地服务
chmod +x start_local.sh
./start_local.sh

# 2. 访问应用
# 浏览器自动打开 http://localhost:8000
```

## 💰 部署方案对比

### 🐳 Docker部署（推荐）

| 优势 | 描述 |
|------|------|
| **低成本** | 单台EC2 t3.medium ($25/月) 即可运行 |
| **易管理** | 一键部署，简单维护 |
| **高性能** | 无冷启动，响应速度快 |
| **完全控制** | 自由定制，数据私有 |
| **可扩展** | 支持水平扩展和负载均衡 |

**适用场景**: 中小企业、个人项目、需要数据私有的场景

### ☁️ AWS Serverless

| 优势 | 描述 |
|------|------|
| **弹性扩容** | 自动扩缩容，按需付费 |
| **免运维** | AWS托管，无需维护服务器 |
| **高可用** | 多可用区，自动故障转移 |
| **快速启动** | 无需管理基础设施 |

**适用场景**: 大型企业、不稳定流量、需要高可用的场景

## 🛠️ 开发指南

### 项目结构
```
chainlit-rag/
├── backend/                    # 后端服务代码
│   ├── models/                # 数据模型
│   ├── services/              # 业务服务
│   └── utils/                 # 工具函数
├── lambda_functions/          # Lambda函数
│   ├── auth/                  # 用户认证
│   ├── chat/                  # 聊天处理
│   ├── document_processing/   # 文档处理
│   └── vector_search/         # 向量搜索
├── frontend/                  # Chainlit前端
├── configs/                   # 配置文件
├── cloudformation/            # CloudFormation模板
├── deployment/                # 部署脚本
└── docs/                      # 文档
```

### Agent配置
Agent工作流在 `configs/agent_config.yaml` 中定义：

```yaml
agent_workflows:
  custom_agent:
    name: "自定义助手"
    description: "您的自定义Agent描述"
    steps:
      - name: "预处理"
        type: "preprocessing"
        config:
          max_length: 500
      - name: "检索"
        type: "retrieval" 
        config:
          top_k: 5
      - name: "生成"
        type: "generation"
        config:
          model: "gpt-3.5-turbo"
          temperature: 0.7
```

### 自定义Agent步骤
在 `backend/services/agent_engine.py` 中添加新的步骤类：

```python
class CustomStep(AgentStep):
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 您的自定义逻辑
        return context
```

### API文档
- `POST /auth/login` - 用户登录
- `POST /auth/register` - 用户注册
- `POST /documents/upload` - 文档上传
- `GET /documents` - 获取文档列表
- `POST /chat` - 发送聊天消息
- `GET /chat/history` - 获取聊天历史

## 🔧 配置说明

### 环境变量
```bash
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key

# AWS配置
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# 应用配置
JWT_SECRET=your_jwt_secret
APP_NAME=chainlit-rag-kb

# 向量数据库选择
VECTOR_DB_TYPE=faiss  # 或 pinecone

# Pinecone配置（如果使用）
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_environment
PINECONE_INDEX_NAME=your_index_name
```

### CloudFormation参数
```yaml
Parameters:
  ProjectName: chainlit-rag-kb
  Environment: dev
  OpenAIApiKey: your_openai_api_key
```

## 📊 监控和日志

### CloudWatch日志
- Lambda函数日志自动发送到CloudWatch
- 日志组：`/aws/lambda/{function-name}`

### 性能监控
```bash
# 查看Lambda函数指标
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/chainlit-rag"

# 查看API Gateway访问日志
aws logs describe-log-groups --log-group-name-prefix "API-Gateway"
```

## 🚀 部署选项

### 开发环境
```bash
./deployment/deploy.sh
# 选择 Environment: dev
```

### 生产环境
```bash
./deployment/deploy.sh
# 选择 Environment: prod
# 建议配置更高的Lambda内存和超时时间
```

### 自定义部署
```bash
# 直接使用CloudFormation
aws cloudformation create-stack \
  --stack-name chainlit-rag-prod \
  --template-body file://cloudformation/main-stack.yaml \
  --parameters ParameterKey=Environment,ParameterValue=prod
```

## 🔐 安全注意事项

1. **API密钥安全**: 使用AWS Secrets Manager存储OpenAI API密钥
2. **JWT密钥**: 生产环境使用强密钥
3. **CORS配置**: 根据需要限制允许的源
4. **IAM权限**: 使用最小权限原则
5. **数据加密**: DynamoDB和S3启用静态加密

## 🐛 故障排除

### 常见问题

**1. Lambda函数超时**
```bash
# 增加超时时间
aws lambda update-function-configuration \
  --function-name your-function-name \
  --timeout 300
```

**2. 内存不足**
```bash
# 增加内存配置
aws lambda update-function-configuration \
  --function-name your-function-name \
  --memory-size 1024
```

**3. DynamoDB读写限制**
- 检查表的读写容量单位
- 考虑使用按需计费模式

**4. OpenAI API限制**
- 检查API配额和限制
- 实现重试机制

### 日志查看
```bash
# 查看Lambda函数日志
aws logs tail /aws/lambda/chainlit-rag-chat-dev --follow

# 查看CloudFormation事件
aws cloudformation describe-stack-events --stack-name chainlit-rag-dev
```

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交变更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目基于 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Chainlit](https://chainlit.io/) - 优秀的聊天界面框架
- [OpenAI](https://openai.com/) - 强大的AI API服务
- [AWS](https://aws.amazon.com/) - 可靠的云服务平台

## 📞 支持

如果您遇到问题或有疑问：

1. 查看 [故障排除](#-故障排除) 部分
2. 搜索现有的 [Issues](../../issues)
3. 创建新的 Issue 描述您的问题
4. 联系维护团队

---

**快乐编程！** 🎉