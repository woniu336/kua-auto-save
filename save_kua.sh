#!/bin/bash
# save_kua.sh - 简化版应用管理脚本
# 用法: ./save_kua.sh [install|start|stop|status|restart|help]

set -e

# 配置
PROJECT_DIR="$HOME/kua-auto-save"
VENV_DIR="$PROJECT_DIR/venv"
PID_FILE="/tmp/save_kua.pid"
LOG_FILE="$PROJECT_DIR/app.log"
PORT="5000"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查命令是否存在
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓ $1 已安装${NC}"
        return 0
    else
        echo -e "${RED}✗ $1 未安装${NC}"
        return 1
    fi
}

# 安装系统包
install_system_package() {
    echo -e "${YELLOW}安装系统包: $1${NC}"
    sudo apt-get update && sudo apt-get install -y "$1"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1 安装成功${NC}"
        return 0
    else
        echo -e "${RED}✗ $1 安装失败${NC}"
        return 1
    fi
}

# 创建虚拟环境
setup_venv() {
    echo -e "${YELLOW}设置Python虚拟环境...${NC}"
    
    # 检查是否已存在虚拟环境
    if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
        echo -e "${GREEN}✓ 虚拟环境已存在${NC}"
        return 0
    fi
    
    # 检查并安装 python3-venv
    if ! dpkg -l | grep -q python3-venv; then
        echo "python3-venv 未安装，正在安装..."
        install_system_package "python3-venv"
    fi
    
    # 创建虚拟环境
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 虚拟环境创建成功${NC}"
        return 0
    else
        echo -e "${RED}✗ 虚拟环境创建失败${NC}"
        return 1
    fi
}

# 安装依赖到虚拟环境
install_requirements() {
    echo -e "${YELLOW}安装项目依赖...${NC}"
    
    # 激活虚拟环境
    source "$VENV_DIR/bin/activate"
    
    # 升级pip
    pip install --upgrade pip
    
    # 先安装 app.py 中发现的额外依赖
    echo "检查应用需要的额外依赖..."
    if [ -f "$PROJECT_DIR/app.py" ]; then
        # 检查常见的依赖
        if grep -q "import aiohttp\|from aiohttp" "$PROJECT_DIR/app.py"; then
            echo "安装: aiohttp"
            pip install aiohttp
        fi
        if grep -q "import requests\|from requests" "$PROJECT_DIR/app.py"; then
            echo "安装: requests"
            pip install requests
        fi
        if grep -q "import bs4\|from bs4\|beautifulsoup" "$PROJECT_DIR/app.py"; then
            echo "安装: beautifulsoup4"
            pip install beautifulsoup4
        fi
        if grep -q "import selenium\|from selenium" "$PROJECT_DIR/app.py"; then
            echo "安装: selenium"
            pip install selenium
        fi
    fi
    
    # 安装 requirements.txt 中的依赖
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        echo "从 requirements.txt 安装依赖..."
        pip install -r "$PROJECT_DIR/requirements.txt"
    else
        echo "安装默认 Flask 依赖..."
        pip install Flask==2.3.3 Werkzeug==2.3.7 Jinja2==3.1.2 itsdangerous==2.1.2 click==8.1.3
    fi
    
    deactivate
    
    echo -e "${GREEN}✓ 依赖安装完成${NC}"
    return 0
}

# 设置管理员账户
setup_admin_account() {
    echo ""
    echo "========================================"
    echo "  设置管理员账户"
    echo "========================================"
    
    # 检查 app.py 是否存在
    if [ ! -f "$PROJECT_DIR/app.py" ]; then
        echo -e "${RED}错误: app.py 文件不存在${NC}"
        return 1
    fi
    
    # 显示当前配置（如果有）
    if grep -q "VALID_USERS = {" "$PROJECT_DIR/app.py"; then
        echo "当前配置的用户:"
        grep -A 2 "VALID_USERS = {" "$PROJECT_DIR/app.py" | grep -E '\".*\":' || echo "  未找到用户配置"
    fi
    
    # 询问是否要修改
    read -p "是否要设置新的管理员账户？ (y/N): " choice
    if [[ ! "$choice" =~ ^[Yy]$ ]]; then
        echo "保持现有配置不变"
        return 0
    fi
    
    # 读取用户名
    read -p "请输入用户名 (默认: admin): " username
    username=${username:-admin}
    
    # 简单的用户名验证
    if [[ -z "$username" || "$username" =~ [[:space:]] ]]; then
        echo -e "${RED}错误: 用户名不能为空或包含空格${NC}"
        return 1
    fi
    
    # 读取密码（不显示）
    while true; do
        read -sp "请输入密码 (至少6位): " password
        echo
        
        if [ ${#password} -lt 6 ]; then
            echo -e "${RED}错误: 密码长度至少需要6位${NC}"
            continue
        fi
        
        read -sp "请再次输入密码确认: " password_confirm
        echo
        
        if [ "$password" != "$password_confirm" ]; then
            echo -e "${RED}错误: 两次输入的密码不一致，请重新输入${NC}"
            continue
        fi
        
        break
    done
    
    # 备份原文件
    if [ ! -f "$PROJECT_DIR/app.py.backup" ]; then
        cp "$PROJECT_DIR/app.py" "$PROJECT_DIR/app.py.backup"
        echo -e "${GREEN}✓ 已备份原文件: app.py.backup${NC}"
    fi
    
    # 替换 app.py 中的用户名密码
    echo -e "${YELLOW}正在更新账户配置...${NC}"
    
    # 尝试多种替换方法
    success=false
    
    # 方法1: 替换完整的 VALID_USERS 字典
    if grep -q "VALID_USERS = {" "$PROJECT_DIR/app.py"; then
        # 使用临时文件确保格式正确
        temp_file=$(mktemp)
        python3 -c "
import re
with open('$PROJECT_DIR/app.py', 'r') as f:
    content = f.read()
    
# 匹配 VALID_USERS = { ... } 格式
pattern = r'VALID_USERS\s*=\s*\{[^}]*\}'
replacement = '''VALID_USERS = {
    \"$username\": \"$password\",
}'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
with open('$temp_file', 'w') as f:
    f.write(new_content)
" && cp "$temp_file" "$PROJECT_DIR/app.py" && rm "$temp_file"
        
        if grep -q "\"$username\": \"$password\"" "$PROJECT_DIR/app.py"; then
            success=true
        fi
    fi
    
    # 方法2: 如果方法1失败，尝试直接替换 admin:admin123
    if [ "$success" = false ] && grep -q '"admin": "admin123"' "$PROJECT_DIR/app.py"; then
        sed -i "s/\"admin\": \"admin123\"/\"$username\": \"$password\"/g" "$PROJECT_DIR/app.py"
        if grep -q "\"$username\": \"$password\"" "$PROJECT_DIR/app.py"; then
            success=true
        fi
    fi
    
    # 验证修改
    if [ "$success" = true ]; then
        echo -e "${GREEN}✓ 管理员账户设置成功${NC}"
        echo "用户名: $username"
    else
        echo -e "${RED}错误: 账户设置失败，请手动编辑 app.py${NC}"
        echo "请将以下内容添加到 app.py 的 VALID_USERS 中:"
        echo "    \"$username\": \"$password\","
        return 1
    fi
    
    echo "========================================"
    return 0
}

# 安装函数
install_app() {
    echo "=== 开始安装应用 ==="
    
    # 检查项目目录
    if [ ! -d "$PROJECT_DIR" ]; then
        echo -e "${RED}错误: 项目目录不存在: $PROJECT_DIR${NC}"
        echo "请先将项目代码放置在 $PROJECT_DIR"
        exit 1
    fi
    
    if [ ! -f "$PROJECT_DIR/app.py" ]; then
        echo -e "${RED}错误: 未找到 app.py${NC}"
        exit 1
    fi
    
    # 检查系统依赖
    check_command python3 || install_system_package "python3"
    check_command pip3 || install_system_package "python3-pip"
    
    # 设置虚拟环境
    setup_venv || exit 1
    
    # 安装依赖
    install_requirements || exit 1
    
    # 设置管理员账户
    setup_admin_account
    
    # 设置权限
    echo "设置执行权限..."
    chmod +x "$PROJECT_DIR/app.py"
    
    echo ""
    echo -e "${GREEN}=== 安装完成 ===${NC}"
    echo "项目路径: $PROJECT_DIR"
    echo "虚拟环境: $VENV_DIR"
    echo "访问地址: http://localhost:$PORT"
    echo "日志文件: $LOG_FILE"
    echo ""
    echo "手动测试命令:"
    echo "  cd $PROJECT_DIR"
    echo "  source venv/bin/activate"
    echo "  python app.py"
    echo ""
    echo -e "${YELLOW}请运行 '$0 start' 启动应用${NC}"
}

# 启动函数
start_app() {
    echo "启动应用程序..."
    
    # 检查是否已安装
    if [ ! -f "$PROJECT_DIR/app.py" ]; then
        echo -e "${RED}错误: app.py 不存在${NC}"
        echo "请先运行: $0 install"
        exit 1
    fi
    
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${RED}错误: 虚拟环境不存在${NC}"
        echo "请先运行: $0 install"
        exit 1
    fi
    
    # 检查是否已在运行
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo -e "${GREEN}应用已经在运行 (PID: $PID)${NC}"
            echo "访问地址: http://localhost:$PORT"
            exit 0
        else
            rm -f "$PID_FILE"
        fi
    fi
    
    # 启动
    echo "正在启动..."
    cd "$PROJECT_DIR"
    
    # 启动应用并记录PID
    source "$VENV_DIR/bin/activate"
    nohup python app.py > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    
    sleep 3
    
    # 检查是否启动成功
    if kill -0 $PID 2>/dev/null; then
        echo -e "${GREEN}✓ 启动成功!${NC}"
        echo "  PID: $PID"
        echo "  端口: $PORT"
        echo "  日志: $LOG_FILE"
        echo "  访问: http://localhost:$PORT"
    else
        echo -e "${RED}✗ 启动失败${NC}"
        echo "请查看日志文件: $LOG_FILE"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# 停止函数
stop_app() {
    echo "停止应用程序..."
    
    if [ ! -f "$PID_FILE" ]; then
        echo "应用未在运行"
        return 0
    fi
    
    PID=$(cat "$PID_FILE")
    
    if kill -0 $PID 2>/dev/null; then
        echo "正在停止进程 $PID..."
        kill $PID
        sleep 2
        
        if kill -0 $PID 2>/dev/null; then
            kill -9 $PID
        fi
        
        echo -e "${GREEN}✓ 已停止 (PID: $PID)${NC}"
    else
        echo "应用未在运行"
    fi
    
    rm -f "$PID_FILE"
}

# 状态函数
status_app() {
    echo "应用程序状态:"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo -e "${GREEN}✓ 正在运行${NC}"
            echo "  PID: $PID"
            echo "  端口: $PORT"
            echo "  日志: $LOG_FILE"
            echo "  访问: http://localhost:$PORT"
            return 0
        fi
    fi
    
    echo -e "${RED}✗ 未运行${NC}"
    return 1
}

# 重启函数
restart_app() {
    echo "重启应用程序..."
    stop_app
    sleep 2
    start_app
}

# 查看日志
view_log() {
    if [ -f "$LOG_FILE" ]; then
        echo "=== 应用日志 (最后50行) ==="
        tail -50 "$LOG_FILE"
    else
        echo "日志文件不存在: $LOG_FILE"
    fi
}

# 清理日志
clean_log() {
    echo "清理日志文件..."
    if [ -f "$LOG_FILE" ]; then
        > "$LOG_FILE"
        echo -e "${GREEN}✓ 日志已清理${NC}"
    else
        echo "日志文件不存在"
    fi
}

# 修复依赖
fix_deps() {
    echo "修复应用依赖..."
    if [ ! -d "$VENV_DIR" ]; then
        echo "虚拟环境不存在，重新安装..."
        install_app
    else
        install_requirements
        echo -e "${GREEN}✓ 依赖修复完成${NC}"
    fi
}

# 重置账户（新功能）
reset_account() {
    echo "重置管理员账户..."
    setup_admin_account
}

# 显示当前账户（新功能）
show_account() {
    echo "当前管理员账户配置:"
    
    if [ ! -f "$PROJECT_DIR/app.py" ]; then
        echo -e "${RED}错误: app.py 不存在${NC}"
        return 1
    fi
    
    if grep -q "VALID_USERS = {" "$PROJECT_DIR/app.py"; then
        echo -e "${GREEN}找到用户配置:${NC}"
        grep -A 5 "VALID_USERS = {" "$PROJECT_DIR/app.py" | grep -E '\".*\":' | sed 's/^/  /'
    else
        echo "未找到 VALID_USERS 配置"
    fi
}

# 帮助函数
show_help() {
    echo -e "${GREEN}save_kua.sh - 应用管理脚本${NC}"
    echo ""
    echo "用法:"
    echo "  $0 install    安装应用和所有依赖"
    echo "  $0 start      启动应用"
    echo "  $0 stop       停止应用"
    echo "  $0 status     查看应用状态"
    echo "  $0 restart    重启应用"
    echo "  $0 log        查看应用日志"
    echo "  $0 clean      清理日志文件"
    echo "  $0 fix        修复应用依赖"
    echo "  $0 account    显示当前账户"
    echo "  $0 reset      重置管理员账户"
    echo "  $0 help       显示帮助信息"
    echo ""
    echo "配置信息:"
    echo "  项目路径: $PROJECT_DIR"
    echo "  虚拟环境: $VENV_DIR"
    echo "  运行端口: $PORT"
    echo "  日志文件: $LOG_FILE"
    echo ""
    echo "快速开始:"
    echo "  ./save_kua.sh install   # 首次安装"
    echo "  ./save_kua.sh start     # 启动应用"
    echo "  ./save_kua.sh status    # 查看状态"
}

# 主逻辑
case "$1" in
    "install") install_app ;;
    "start")   start_app   ;;
    "stop")    stop_app    ;;
    "status")  status_app  ;;
    "restart") restart_app ;;
    "log")     view_log    ;;
    "clean")   clean_log   ;;
    "fix")     fix_deps    ;;
    "account") show_account ;;
    "reset")   reset_account ;;
    "help"|"--help"|"-h"|"")
        show_help ;;
    *)
        echo -e "${RED}错误: 未知命令 '$1'${NC}"
        echo "使用 '$0 help' 查看帮助"
        exit 1 ;;
esac
