#!/bin/bash
# Chainlit RAG知识库系统部署脚本

set -e

# 配置参数
PROJECT_NAME="chainlit-rag-kb"
AWS_REGION="us-east-1"
ENVIRONMENT="dev"
STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查必要的工具
check_prerequisites() {
    log_info "检查部署环境..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI未安装，请先安装AWS CLI"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3未安装，请先安装Python 3"
        exit 1
    fi
    
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3未安装，请先安装pip3"
        exit 1
    fi
    
    # 检查AWS配置
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS CLI未配置，请运行 'aws configure' 配置凭证"
        exit 1
    fi
    
    log_info "环境检查通过"
}

# 读取用户输入
get_user_input() {
    echo "请输入部署配置："
    
    # OpenAI API Key
    read -p "OpenAI API Key: " -s OPENAI_API_KEY
    echo
    
    if [ -z "$OPENAI_API_KEY" ]; then
        log_error "OpenAI API Key不能为空"
        exit 1
    fi
    
    # AWS Region
    read -p "AWS Region [$AWS_REGION]: " input_region
    if [ ! -z "$input_region" ]; then
        AWS_REGION=$input_region
    fi
    
    # Environment
    read -p "Environment [$ENVIRONMENT]: " input_env
    if [ ! -z "$input_env" ]; then
        ENVIRONMENT=$input_env
        STACK_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
    fi
    
    log_info "配置信息："
    log_info "  AWS Region: $AWS_REGION"
    log_info "  Environment: $ENVIRONMENT"
    log_info "  Stack Name: $STACK_NAME"
    
    read -p "确认部署? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "部署已取消"
        exit 0
    fi
}

# 安装Python依赖
install_dependencies() {
    log_info "安装Python依赖..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -r requirements.txt
    
    log_info "依赖安装完成"
}

# 打包Lambda函数
package_lambda_functions() {
    log_info "打包Lambda函数..."
    
    # 创建打包目录
    mkdir -p dist/lambda_packages
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 打包认证函数
    log_info "打包认证函数..."
    cd lambda_functions/auth
    zip -r ../../dist/lambda_packages/auth.zip . -x "*.pyc" "__pycache__/*"
    cd ../..
    
    # 打包聊天函数
    log_info "打包聊天函数..."
    cd lambda_functions/chat
    zip -r ../../dist/lambda_packages/chat.zip . -x "*.pyc" "__pycache__/*"
    cd ../..
    
    # 打包文档处理函数
    log_info "打包文档处理函数..."
    cd lambda_functions/document_processing
    zip -r ../../dist/lambda_packages/document_processing.zip . -x "*.pyc" "__pycache__/*"
    cd ../..
    
    # 打包向量搜索函数
    log_info "打包向量搜索函数..."
    cd lambda_functions/vector_search
    zip -r ../../dist/lambda_packages/vector_search.zip . -x "*.pyc" "__pycache__/*"
    cd ../..
    
    log_info "Lambda函数打包完成"
}

# 创建S3存储桶用于部署
create_deployment_bucket() {
    DEPLOYMENT_BUCKET="${PROJECT_NAME}-deployment-${AWS_REGION}-$(date +%s)"
    
    log_info "创建部署存储桶: $DEPLOYMENT_BUCKET"
    
    aws s3 mb "s3://$DEPLOYMENT_BUCKET" --region "$AWS_REGION"
    
    # 上传Lambda包
    log_info "上传Lambda包..."
    aws s3 cp dist/lambda_packages/ "s3://$DEPLOYMENT_BUCKET/lambda/" --recursive
    
    # 上传CloudFormation模板
    aws s3 cp cloudformation/main-stack.yaml "s3://$DEPLOYMENT_BUCKET/templates/"
}

# 部署CloudFormation栈
deploy_cloudformation() {
    log_info "部署CloudFormation栈..."
    
    # 检查栈是否存在
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" &> /dev/null; then
        log_info "更新现有栈..."
        ACTION="update-stack"
    else
        log_info "创建新栈..."
        ACTION="create-stack"
    fi
    
    # 部署栈
    aws cloudformation $ACTION \
        --stack-name "$STACK_NAME" \
        --template-body file://cloudformation/main-stack.yaml \
        --parameters \
            ParameterKey=ProjectName,ParameterValue="$PROJECT_NAME" \
            ParameterKey=Environment,ParameterValue="$ENVIRONMENT" \
            ParameterKey=OpenAIApiKey,ParameterValue="$OPENAI_API_KEY" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION"
    
    log_info "等待栈部署完成..."
    aws cloudformation wait stack-${ACTION%-stack}-complete \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION"
    
    if [ $? -eq 0 ]; then
        log_info "CloudFormation栈部署成功"
    else
        log_error "CloudFormation栈部署失败"
        exit 1
    fi
}

# 更新Lambda函数代码
update_lambda_functions() {
    log_info "更新Lambda函数代码..."
    
    # 获取函数名
    AUTH_FUNCTION_NAME="${PROJECT_NAME}-auth-${ENVIRONMENT}"
    CHAT_FUNCTION_NAME="${PROJECT_NAME}-chat-${ENVIRONMENT}"
    DOC_PROCESSING_FUNCTION_NAME="${PROJECT_NAME}-document-processing-${ENVIRONMENT}"
    VECTOR_SEARCH_FUNCTION_NAME="${PROJECT_NAME}-vector-search-${ENVIRONMENT}"
    
    # 更新认证函数
    log_info "更新认证函数..."
    aws lambda update-function-code \
        --function-name "$AUTH_FUNCTION_NAME" \
        --zip-file fileb://dist/lambda_packages/auth.zip \
        --region "$AWS_REGION"
    
    # 更新聊天函数
    log_info "更新聊天函数..."
    aws lambda update-function-code \
        --function-name "$CHAT_FUNCTION_NAME" \
        --zip-file fileb://dist/lambda_packages/chat.zip \
        --region "$AWS_REGION"
    
    # 更新文档处理函数
    log_info "更新文档处理函数..."
    aws lambda update-function-code \
        --function-name "$DOC_PROCESSING_FUNCTION_NAME" \
        --zip-file fileb://dist/lambda_packages/document_processing.zip \
        --region "$AWS_REGION"
    
    # 更新向量搜索函数
    log_info "更新向量搜索函数..."
    aws lambda update-function-code \
        --function-name "$VECTOR_SEARCH_FUNCTION_NAME" \
        --zip-file fileb://dist/lambda_packages/vector_search.zip \
        --region "$AWS_REGION"
    
    log_info "Lambda函数更新完成"
}

# 获取部署输出
get_deployment_outputs() {
    log_info "获取部署信息..."
    
    OUTPUTS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs' \
        --output table)
    
    echo "$OUTPUTS"
    
    # 保存到配置文件
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
        --output text)
    
    # 创建环境配置文件
    cat > .env.${ENVIRONMENT} << EOF
# ${ENVIRONMENT}环境配置
AWS_REGION=$AWS_REGION
ENVIRONMENT=$ENVIRONMENT
API_GATEWAY_URL=$API_URL
OPENAI_API_KEY=$OPENAI_API_KEY

# DynamoDB表名
DYNAMODB_USERS_TABLE=${PROJECT_NAME}-users-${ENVIRONMENT}
DYNAMODB_CHAT_HISTORY_TABLE=${PROJECT_NAME}-chat-history-${ENVIRONMENT}
DYNAMODB_DOCUMENTS_TABLE=${PROJECT_NAME}-documents-${ENVIRONMENT}

# S3存储桶
S3_BUCKET_NAME=${PROJECT_NAME}-documents-${ENVIRONMENT}-$(aws sts get-caller-identity --query Account --output text)
EOF
    
    log_info "配置文件已保存到 .env.${ENVIRONMENT}"
    log_info "API Gateway URL: $API_URL"
}

# 清理临时文件
cleanup() {
    log_info "清理临时文件..."
    
    if [ ! -z "$DEPLOYMENT_BUCKET" ]; then
        aws s3 rb "s3://$DEPLOYMENT_BUCKET" --force 2>/dev/null || true
    fi
    
    rm -rf dist/lambda_packages
}

# 主部署流程
main() {
    log_info "开始部署Chainlit RAG知识库系统..."
    
    # 注册清理函数
    trap cleanup EXIT
    
    check_prerequisites
    get_user_input
    install_dependencies
    package_lambda_functions
    create_deployment_bucket
    deploy_cloudformation
    update_lambda_functions
    get_deployment_outputs
    
    log_info "部署完成！"
    log_info "API Gateway URL: $API_URL"
    log_info "环境配置文件: .env.${ENVIRONMENT}"
    log_info ""
    log_info "下一步："
    log_info "1. 配置Chainlit前端连接到API Gateway"
    log_info "2. 运行 'chainlit run frontend/app.py' 启动应用"
}

# 执行部署
main "$@"