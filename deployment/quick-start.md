# Chainlit RAG知识库系统 - 快速启动指南

## 🚀 5分钟快速部署

### 第一步：环境准备
```bash
# 1. 检查Python版本（需要3.9+）
python --version

# 2. 检查AWS CLI
aws --version
aws sts get-caller-identity  # 确保AWS凭证已配置

# 3. 准备OpenAI API Key
echo "OpenAI API Key: sk-..."
```

### 第二步：克隆和安装
```bash
# 克隆项目（替换为实际地址）
git clone <your-repo>
cd chainlit-rag

# 安装依赖
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 第三步：一键部署
```bash
# 运行部署脚本
chmod +x deployment/deploy.sh
./deployment/deploy.sh
```

部署脚本会提示输入：
- OpenAI API Key
- AWS Region (默认: us-east-1)
- Environment (默认: dev)

### 第四步：启动应用
```bash
# 加载生成的环境配置
source .env.dev

# 启动Chainlit
chainlit run frontend/app.py
```

### 第五步：开始使用
1. 打开浏览器访问 `http://localhost:8000`
2. 注册新账户或登录
3. 上传您的第一个文档
4. 开始智能问答！

## 🎯 功能测试清单

### ✅ 用户认证测试
- [ ] 注册新账户
- [ ] 登录/登出
- [ ] 令牌验证

### ✅ 文档管理测试
- [ ] 上传PDF文档
- [ ] 上传文本文件
- [ ] 查看文档列表
- [ ] 删除文档

### ✅ 智能问答测试
- [ ] 基于文档内容提问
- [ ] 查看引用文档
- [ ] 测试不同Agent工作流

### ✅ 聊天功能测试
- [ ] 多轮对话
- [ ] 查看聊天历史
- [ ] 切换对话会话

## 🔧 配置说明

### 环境变量配置
```bash
# .env.dev 文件内容示例
AWS_REGION=us-east-1
ENVIRONMENT=dev
API_GATEWAY_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/dev
OPENAI_API_KEY=sk-your-openai-key

# DynamoDB表名
DYNAMODB_USERS_TABLE=chainlit-rag-kb-users-dev
DYNAMODB_CHAT_HISTORY_TABLE=chainlit-rag-kb-chat-history-dev
DYNAMODB_DOCUMENTS_TABLE=chainlit-rag-kb-documents-dev

# S3存储桶
S3_BUCKET_NAME=chainlit-rag-kb-documents-dev-123456789
```

### Agent工作流配置
在 `configs/agent_config.yaml` 中可以自定义Agent行为：

```yaml
agent_workflows:
  my_custom_agent:
    name: "我的自定义助手"
    description: "专门用于特定领域的问答"
    steps:
      - name: "预处理"
        type: "preprocessing"
        config:
          max_length: 800  # 调整最大输入长度
      - name: "检索"
        type: "retrieval"
        config:
          top_k: 3  # 检索文档数量
          similarity_threshold: 0.8  # 相似度阈值
      - name: "生成"
        type: "generation"
        config:
          model: "gpt-4"  # 使用更强的模型
          temperature: 0.3  # 降低随机性
```

## 🐛 常见问题解决

### 问题1：Lambda函数部署失败
```bash
# 检查IAM权限
aws iam get-user
aws iam list-attached-user-policies --user-name your-username

# 解决方案：确保用户有Lambda、CloudFormation、IAM权限
```

### 问题2：API Gateway无法访问
```bash
# 检查API Gateway部署状态
aws apigateway get-rest-apis
aws apigateway get-deployments --rest-api-id your-api-id

# 解决方案：重新部署API
aws apigateway create-deployment --rest-api-id your-api-id --stage-name dev
```

### 问题3：DynamoDB权限错误
```bash
# 检查表是否存在
aws dynamodb list-tables

# 检查Lambda函数的IAM角色权限
aws iam get-role-policy --role-name chainlit-rag-kb-lambda-execution-role-dev --policy-name DynamoDBAccess
```

### 问题4：OpenAI API调用失败
```bash
# 验证API Key
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# 检查Secrets Manager中的密钥
aws secretsmanager get-secret-value --secret-id chainlit-rag-kb/openai-api-key/dev
```

### 问题5：Chainlit启动失败
```bash
# 检查环境变量
echo $API_GATEWAY_URL
echo $OPENAI_API_KEY

# 重新安装Chainlit
pip uninstall chainlit
pip install chainlit==1.0.200
```

## 📊 性能优化建议

### Lambda函数优化
```bash
# 增加内存以提高性能
aws lambda update-function-configuration \
  --function-name chainlit-rag-kb-chat-dev \
  --memory-size 1024

# 设置预配置并发（避免冷启动）
aws lambda put-provisioned-concurrency-config \
  --function-name chainlit-rag-kb-chat-dev \
  --qualifier '$LATEST' \
  --provisioned-concurrency-count 2
```

### DynamoDB优化
```bash
# 启用自动扩缩容
aws application-autoscaling register-scalable-target \
  --service-namespace dynamodb \
  --resource-id "table/chainlit-rag-kb-users-dev" \
  --scalable-dimension "dynamodb:table:ReadCapacityUnits" \
  --min-capacity 5 \
  --max-capacity 100
```

## 🔒 安全加固

### 1. API Gateway安全
```yaml
# 在CloudFormation中添加API Key要求
ApiKey:
  Type: AWS::ApiGateway::ApiKey
  Properties:
    Name: !Sub '${ProjectName}-api-key-${Environment}'
    Enabled: true
```

### 2. CORS设置
```javascript
// 限制允许的源
const corsOptions = {
  origin: ['https://yourdomain.com', 'http://localhost:8000'],
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization']
};
```

### 3. JWT密钥轮换
```bash
# 定期更新JWT密钥
aws secretsmanager update-secret \
  --secret-id chainlit-rag-kb/jwt-secret/dev \
  --secret-string '{"jwt_secret": "new-secret-key"}'
```

## 📈 监控和日志

### CloudWatch仪表板
```bash
# 创建自定义仪表板
aws cloudwatch put-dashboard \
  --dashboard-name "ChainlitRAG-${Environment}" \
  --dashboard-body file://monitoring/dashboard.json
```

### 日志查看
```bash
# 实时查看Lambda日志
aws logs tail /aws/lambda/chainlit-rag-kb-chat-dev --follow

# 查看错误日志
aws logs filter-log-events \
  --log-group-name "/aws/lambda/chainlit-rag-kb-chat-dev" \
  --filter-pattern "ERROR"
```

## 🚀 生产环境部署

### 生产环境配置差异
```bash
# 部署到生产环境
./deployment/deploy.sh
# 选择 Environment: prod

# 生产环境建议配置：
# - Lambda内存：1024MB+
# - Lambda超时：300秒
# - DynamoDB：按需计费模式
# - S3：启用版本控制和跨区域复制
```

### 备份策略
```bash
# 启用DynamoDB备份
aws dynamodb put-backup-policy \
  --table-name chainlit-rag-kb-users-prod \
  --backup-policy BackupEnabled=true

# S3生命周期策略
aws s3api put-bucket-lifecycle-configuration \
  --bucket chainlit-rag-kb-documents-prod \
  --lifecycle-configuration file://s3-lifecycle.json
```

---

## 🎉 部署完成！

恭喜！您已经成功部署了Chainlit RAG知识库系统。

**下一步建议：**
1. 上传一些示例文档测试系统
2. 尝试不同的Agent工作流
3. 根据使用情况调整配置参数
4. 考虑集成更多数据源

**获取帮助：**
- 查看 [README.md](../README.md) 了解详细功能
- 搜索 [Issues](../../issues) 寻找解决方案
- 提交新的Issue反馈问题

快乐使用！ 🎊