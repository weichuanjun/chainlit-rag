#!/bin/bash

# Chainlit RAG 知识库系统 - 开发模式管理脚本
# 使用 docker-compose.dev.yml 配置文件，支持热重载

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# 检查Docker是否运行
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker未运行，请先启动Docker"
        exit 1
    fi
}

# 检查docker-compose文件
check_compose_file() {
    if [ ! -f "docker-compose.dev.yml" ]; then
        log_error "找不到 docker-compose.dev.yml 文件"
        exit 1
    fi
}

# 显示帮助信息
show_help() {
    echo "Chainlit RAG 知识库系统 - 开发模式管理脚本"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start     启动开发环境（支持热重载）"
    echo "  stop      停止开发环境"
    echo "  restart   重启开发环境"
    echo "  build     重新构建镜像"
    echo "  logs      查看日志"
    echo "  status    查看服务状态"
    echo "  clean     清理所有容器和数据"
    echo "  help      显示此帮助信息"
    echo ""
    echo "开发模式特性:"
    echo "  ✅ 源代码热重载"
    echo "  ✅ 实时日志查看"
    echo "  ✅ 快速重启"
    echo "  ✅ 数据持久化"
    echo ""
}

# 启动开发环境
start_dev() {
    log_info "🚀 启动开发环境..."
    check_docker
    check_compose_file
    
    # 检查环境变量
    if [ -z "$OPENAI_API_KEY" ]; then
        log_warn "未设置 OPENAI_API_KEY 环境变量"
        log_info "请在 .env 文件中设置或导出环境变量"
    fi
    
    # 启动服务
    docker-compose -f docker-compose.dev.yml up -d
    
    log_info "✅ 开发环境启动完成"
    show_status
    show_access_info
}

# 停止开发环境
stop_dev() {
    log_info "🛑 停止开发环境..."
    docker-compose -f docker-compose.dev.yml down
    log_info "✅ 开发环境已停止"
}

# 重启开发环境
restart_dev() {
    log_info "🔄 重启开发环境..."
    stop_dev
    sleep 2
    start_dev
}

# 重新构建镜像
build_dev() {
    log_info "🔨 重新构建开发镜像..."
    docker-compose -f docker-compose.dev.yml build --no-cache
    log_info "✅ 镜像构建完成"
}

# 查看日志
show_logs() {
    local service=${1:-app}
    log_info "📋 查看 $service 服务日志..."
    docker-compose -f docker-compose.dev.yml logs -f $service
}

# 查看服务状态
show_status() {
    log_info "📊 服务状态:"
    docker-compose -f docker-compose.dev.yml ps
    
    echo ""
    log_info "🔍 健康检查:"
    
    # 检查API服务
    if curl -s http://localhost:5001/health > /dev/null 2>&1; then
        log_info "✅ API服务正常"
    else
        log_warn "❌ API服务异常"
    fi
    
    # 检查数据库
    if docker-compose -f docker-compose.dev.yml exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
        log_info "✅ 数据库连接正常"
    else
        log_warn "❌ 数据库连接异常"
    fi
    
    # 检查Redis
    if docker-compose -f docker-compose.dev.yml exec -T redis redis-cli --raw incr ping > /dev/null 2>&1; then
        log_info "✅ Redis缓存正常"
    else
        log_warn "❌ Redis缓存异常"
    fi
}

# 显示访问信息
show_access_info() {
    echo ""
    log_info "🔗 访问地址:"
    log_info "🌐 Chainlit界面: http://localhost:8000"
    log_info "📡 API接口: http://localhost:5001"
    log_info "🔍 健康检查: http://localhost:5001/health"
    echo ""
    log_info "💡 开发模式特性:"
    log_info "  • 源代码修改后自动重载"
    log_info "  • 实时日志查看: $0 logs"
    log_info "  • 快速重启: $0 restart"
}

# 清理环境
clean_dev() {
    log_warn "🧹 清理开发环境..."
    log_warn "这将删除所有容器、网络和数据卷"
    
    read -p "确定要继续吗？(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f docker-compose.dev.yml down -v --remove-orphans
        docker system prune -f
        log_info "✅ 环境清理完成"
    else
        log_info "取消清理操作"
    fi
}

# 主函数
main() {
    case "${1:-help}" in
        start)
            start_dev
            ;;
        stop)
            stop_dev
            ;;
        restart)
            restart_dev
            ;;
        build)
            build_dev
            ;;
        logs)
            show_logs $2
            ;;
        status)
            show_status
            ;;
        clean)
            clean_dev
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 